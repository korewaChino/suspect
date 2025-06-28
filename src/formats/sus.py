from abc import ABC, abstractmethod
from enum import Enum
from collections import defaultdict

SUS_TICKS_PER_MEASURE = 480 * 4


class TapNoteType(Enum):
    TAP = 1
    EXTAP = 2
    FLICK = 3
    HELL = 4
    RESERVED1 = 5
    RESERVED2 = 6


class AirNoteType(Enum):
    UP = 1
    DOWN = 2
    UP_LEFT = 3
    UP_RIGHT = 4
    DOWN_LEFT = 5
    DOWN_RIGHT = 6


class LongNoteType(Enum):
    START = 1
    END = 2
    STEP = 3
    CONTROL = 4
    INVISIBLE = 5


class LongNoteKind(Enum):
    HOLD = 2
    SLIDE = 3
    AIR_HOLD = 4


class SusContext:
    active_attribute = None
    active_speed = None
    base_measure = 0
    ticks_per_measure = SUS_TICKS_PER_MEASURE

    bpm_definitions = {}
    attribute_definitions = {}
    speed_definitions = {}

    channels = {}

    def fix_channels(self):
        for key in self.channels:
            channel = self.channels[key]
            for i in range(len(channel) - 1):

                if (
                    channel[i].note_kind != channel[i + 1].note_kind
                    and channel[i].note_type != LongNoteType["END"]
                ):
                    print(
                        "Replaced %s:%s with END at index %s on channel %s (next note was %s:%s)"
                        % (
                            channel[i].note_kind,
                            channel[i].note_type,
                            i,
                            key,
                            channel[i + 1].note_kind,
                            channel[i + 1].note_type,
                        )
                    )
                    channel[i].note_type = LongNoteType["END"]

                if (
                    channel[i].note_type != LongNoteType["END"]
                    and channel[i + 1].note_type == LongNoteType["START"]
                ):
                    print(
                        "Replaced %s:%s with END at index %s on channel %s (next note was %s:%s)"
                        % (
                            channel[i].note_kind,
                            channel[i].note_type,
                            i,
                            key,
                            channel[i + 1].note_kind,
                            channel[i + 1].note_type,
                        )
                    )
                    channel[i].note_type = LongNoteType["END"]

            if channel[-1].note_type != LongNoteType["END"]:
                channel[-1].note_type = LongNoteType["END"]
                print("Fixed last note of channel %s that was not an END" % key)


class SusObject(ABC):
    attribute = None
    speed = None


class BarLength(SusObject):
    measure = 0
    length = 0


class BpmDefinition(SusObject):
    identifier = 0
    tempo = 0.0


class BpmChange(SusObject):
    measure = 0
    definition = None


class AttributeDefinition(SusObject):
    identifier = 0
    roll_speed = None
    height = None
    priority = None


class SpeedDefinition(SusObject):
    identifier = 0
    speeds = []

    def add_speed(self, measure, tick, speed):
        self.speeds.append((measure, tick, speed))


class ShortNote(SusObject):
    measure = 0
    tick = 0
    lane = 0
    width = 0
    note_type = TapNoteType(1)


class LongNote(SusObject):
    measure = 0
    tick = 0
    lane = 0
    width = 0
    note_kind = LongNoteKind(2)
    note_type = LongNoteType(1)
    linked = []
    channel = None  # Channel identifier for grouping long notes


def from_string(sus_string: str, context: SusContext):
    if sus_string[0] != "#":
        print("Ignoring line that doesn't start with #")
        return []

    sus_string = sus_string[1:]
    split = sus_string.split(":", 2)
    header = split[0]
    # Speed regions
    if header.startswith("HISPEED"):
        context.active_speed = context.speed_definitions[header.split()[1].strip()]
        print("Speed region start")
        return []
    if header.startswith("NOSPEED"):
        context.active_speed = None
        print("Speed region end")
        return []

    # Attribute regions
    if header.startswith("ATTRIBUTE"):
        context.active_attribute = context.attribute_definitions[
            header.split()[1].strip()
        ]
        print("Attribute region start")
        return []
    if header.startswith("NOATTRIBUTE"):
        context.active_attribute = None
        print("Attribute region end")
        return []

    # Set base measure
    if header.startswith("MEASUREBS"):
        context.base_measure = int(header.split()[1])
        print("Base measure number updated")
        return []

    # Bar speed changes unsupported for now

    if len(split) != 1:
        data = split[1].strip()
        measure = header[:3]

        if measure == "BPM":
            # BPM definition. The header contains the ID, and the data payload is a float specifying the BPM to use from now on.
            obj = BpmDefinition()
            obj.identifier = header[3:5]
            obj.tempo = float(data)
            context.bpm_definitions[obj.identifier] = obj

            print("Registered BPM definition")

            return []
        if measure == "ATR":
            # Attribute definition. Parse attribute string.
            obj = AttributeDefinition()
            obj.identifier = header[3:5]
            defstring = data.replace('"', "").split(",")
            for definition in defstring:
                try:
                    (attr, val) = definition.split(":")
                    if attr == "rh":
                        obj.roll_speed = float(val)
                    if attr == "h":
                        obj.height = float(val)
                    if attr == "pr":
                        obj.priority = float(val)
                except:
                    continue

            context.attribute_definitions[obj.identifier] = obj
            print("Registered attribute definition")

            return []
        if measure == "TIL":
            # Speed change definition. Parse speed change string.
            obj = SpeedDefinition()
            obj.identifier = header[3:5]
            defstring = data.replace('"', "").replace("'", ":").split(",")
            for definition in defstring:
                try:
                    (bar, tick, speed) = definition.split(":")
                    obj.add_speed(int(bar), int(tick), float(speed))
                except:
                    continue

            context.speed_definitions[obj.identifier] = obj

            print("Registered speed definition")

            return []
        else:
            # Check if this is a 3-digit or 5-digit measure format
            if len(header) >= 6 and header[0:5].isdigit():
                # 5-digit format: mmmmm (5 chars for measure)
                measure = header[:5]
                # Make sure we have enough characters for note_type
                if len(header) > 5:
                    note_type = header[5]
                    measure_value = int(measure) + context.base_measure

                    if note_type == "0" and len(header) > 6:  # BPM or bar length change
                        change_type = header[6]
                        if change_type == "2":
                            # Bar length change
                            obj = BarLength()
                            obj.measure = measure_value
                            obj.length = int(data)
                            print("Applying bar length change")
                            return [obj]
                        if change_type == "8":
                            # BPM change
                            obj = BpmChange()
                            obj.measure = measure_value
                            obj.definition = context.bpm_definitions[data]
                            print("Applying BPM change")
                            return [obj]

                # Handle other 5-digit format notes here
                # Remove whitespace from data
                data = "".join(data.split())

                # Handle potentially empty data
                if not data:
                    print("Warning: Empty data for note, skipping")
                    return []

                tick_subdivision = context.ticks_per_measure // (len(data) // 2)
                parsed_data = [
                    (
                        tick_subdivision * (i // 2),
                        int(data[i], 36),
                        int(data[i + 1], 36),
                    )
                    for i in range(0, len(data), 2)
                    if i + 1 < len(data)
                ]

                if len(header) > 6 and (
                    note_type == "1" or note_type == "5"
                ):  # Tap or air note
                    lane = int(header[6], 36)  # Use base-36 for lanes
                    objects = []
                    for tick, tap_type, width in parsed_data:
                        if tap_type == 0:
                            # Skip 0 entries
                            continue

                        obj = ShortNote()
                        obj.lane = lane
                        obj.measure = measure_value
                        obj.tick = tick
                        if note_type == "1":
                            obj.note_type = TapNoteType(tap_type)
                        else:
                            obj.note_type = AirNoteType(tap_type)
                        obj.width = width
                        obj.speed = context.active_speed
                        obj.attribute = context.active_attribute
                        objects.append(obj)

                    print(f"Found {len(objects)} short notes")
                    return objects

                if len(header) > 7 and (
                    note_type == "2" or note_type == "3" or note_type == "4"
                ):  # Hold, slide, or air hold note
                    lane = int(header[6], 36)  # Use base-36 for lanes
                    channel = header[7]

                    objects = []
                    for tick, long_type, width in parsed_data:
                        if long_type == 0:
                            # Skip 0 entries
                            continue

                        obj = LongNote()
                        obj.note_kind = LongNoteKind(
                            int(note_type)
                        )  # Hold, slide, or air hold
                        obj.note_type = LongNoteType(
                            long_type
                        )  # Start, tick, curve point, end, etc
                        obj.lane = lane
                        obj.measure = measure_value
                        obj.tick = tick
                        obj.width = width
                        obj.speed = context.active_speed
                        obj.attribute = context.active_attribute
                        obj.channel = channel  # Set the channel for linking notes

                        if not channel in context.channels.keys():
                            context.channels[channel] = []

                        # Add the object to its channel, and link it to the other objects in the same channel
                        obj.linked = context.channels[channel]
                        context.channels[channel].append(obj)

                        # Sort the channel by time
                        context.channels[channel].sort(
                            key=lambda item: item.measure
                            + item.tick / context.ticks_per_measure
                        )

                        objects.append(obj)
                    print(f"Found {len(objects)} long notes")
                    return objects

            else:
                # Standard 3-digit format
                if len(header) > 3:
                    note_type = header[3]
                    if note_type == "0" and len(header) > 4:  # BPM or bar length change
                        measure_value = int(measure) + context.base_measure
                        change_type = header[4]
                        if change_type == "2":
                            # Bar length change. The data payload is an integer specifying the bar length in beats.
                            obj = BarLength()
                            obj.measure = measure_value
                            obj.length = int(data)
                            print("Applying bar length change")
                            return [obj]
                        if change_type == "8":
                            # BPM change. The data payload is an in integer referencing the BPM definition to use.
                            obj = BpmChange()
                            obj.measure = measure_value
                            obj.definition = context.bpm_definitions[data]
                            print("Applying BPM change")
                            return [obj]

                # Every other note type requires parsing the data payload as a set of pairs of digits
                # Remove whitespace from data
                data = "".join(data.split())

                # Handle potentially empty data
                if not data:
                    print("Warning: Empty data for note, skipping")
                    return []

                tick_subdivision = context.ticks_per_measure // (len(data) // 2)
                parsed_data = [
                    (
                        tick_subdivision * (i // 2),
                        int(data[i], 36),
                        int(data[i + 1], 36),
                    )
                    for i in range(0, len(data), 2)
                    if i + 1 < len(data)
                ]

                if len(header) > 4 and (
                    note_type == "1" or note_type == "5"
                ):  # Tap or air note
                    measure_value = int(measure) + context.base_measure
                    lane = int(header[4], 36)  # Use base-36 for lanes
                    objects = []
                    for tick, tap_type, width in parsed_data:
                        if tap_type == 0:
                            # Skip 0 entries
                            continue

                        obj = ShortNote()
                        obj.lane = lane
                        obj.measure = measure_value
                        obj.tick = tick
                        if note_type == "1":
                            obj.note_type = TapNoteType(tap_type)
                        else:
                            obj.note_type = AirNoteType(tap_type)
                        obj.width = width
                        obj.speed = context.active_speed
                        obj.attribute = context.active_attribute
                        objects.append(obj)

                    print(f"Found {len(objects)} short notes")
                    return objects

                if len(header) > 5 and (
                    note_type == "2" or note_type == "3" or note_type == "4"
                ):  # Hold, slide, or air hold note
                    measure_value = int(measure) + context.base_measure
                    lane = int(header[4], 36)  # Use base-36 for lanes

                    if len(header) <= 5:
                        print(
                            f"Warning: Long note header too short ({header}), skipping"
                        )
                        return []

                    channel = header[5]

                    objects = []
                    for tick, long_type, width in parsed_data:
                        if long_type == 0:
                            # Skip 0 entries
                            continue

                        obj = LongNote()
                        obj.note_kind = LongNoteKind(
                            int(note_type)
                        )  # Hold, slide, or air hold
                        obj.note_type = LongNoteType(
                            long_type
                        )  # Start, tick, curve point, end, etc
                        obj.lane = lane
                        obj.measure = measure_value
                        obj.tick = tick
                        obj.width = width
                        obj.speed = context.active_speed
                        obj.attribute = context.active_attribute
                        obj.channel = channel  # Set the channel for linking notes

                        if not channel in context.channels.keys():
                            context.channels[channel] = []

                        # Add the object to its channel, and link it to the other objects in the same channel
                        obj.linked = context.channels[channel]
                        context.channels[channel].append(obj)

                        # Sort the channel by time
                        context.channels[channel].sort(
                            key=lambda item: item.measure
                            + item.tick / context.ticks_per_measure
                        )

                        objects.append(obj)
                    print(f"Found {len(objects)} long notes")
                    return objects

    print(f"Skipped unsupported statement\n{sus_string}")
    return []


def create_file(sus_objects):
    """
    Create a SUS file from a list of SUS objects.

    Args:
        sus_objects: List of SUS objects

    Returns:
        String representation of the SUS file
    """
    # Basic header information
    output = []
    output.append('#TITLE "Generated by Suspect"')
    output.append('#ARTIST ""')
    output.append('#DESIGNER ""')
    output.append("#DIFFICULTY 2")
    output.append("#PLAYLEVEL 0")
    output.append('#SONGID "0"')
    output.append('#WAVE ""')
    output.append("#WAVEOFFSET 0")
    output.append('#JACKET ""')
    output.append("")
    output.append('#REQUEST "ticks_per_beat 480"')
    output.append("")

    # Process BPM definitions
    bpm_defs = {}
    for obj in sus_objects:
        if isinstance(obj, BpmDefinition):
            bpm_defs[obj.identifier] = obj
            output.append(f"#BPM{obj.identifier}: {obj.tempo}")

    # Create a map of note timing to measure size to handle odd time signatures
    measure_sizes = {}
    for obj in sus_objects:
        if isinstance(obj, BarLength):
            measure_sizes[obj.measure] = obj.length

    # Default bar length (4/4)
    output.append("#00002: 4")
    output.append("")

    # BPM changes and other definitions
    for obj in sus_objects:
        if isinstance(obj, BpmChange):
            # Find the BPM definition ID for this change
            bpm_id = None
            for bid, bdef in bpm_defs.items():
                if bdef == obj.definition:
                    bpm_id = bid
                    break

            if bpm_id:
                measure_str = f"{obj.measure:03d}"
                output.append(f"#{measure_str}08: {bpm_id}")

        elif (
            isinstance(obj, BarLength) and obj.measure != 0
        ):  # Skip default at measure 0
            measure_str = f"{obj.measure:03d}"
            output.append(f"#{measure_str}02: {obj.length}")

    output.append("")

    # Group notes by measure and type for better organization
    short_notes = defaultdict(list)
    long_notes = defaultdict(list)

    # Collect short notes by measure, type, and lane
    for obj in sus_objects:
        if isinstance(obj, ShortNote):
            measure = obj.measure
            tick = obj.tick
            lane = obj.lane
            width = obj.width

            # Determine the note type code for SUS format
            if hasattr(obj, "note_type"):
                if obj.note_type in TapNoteType:
                    type_code = "1"  # TAP notes
                elif obj.note_type in AirNoteType:
                    type_code = "5"  # AIR notes
                else:
                    type_code = "1"  # Default to TAP
            else:
                type_code = "1"  # Default to TAP

            key = (measure, type_code, lane)
            short_notes[key].append((tick, obj))

        elif isinstance(obj, LongNote):
            if not hasattr(obj, "channel"):
                # Skip notes without a channel
                continue

            measure = obj.measure
            tick = obj.tick
            lane = obj.lane
            width = obj.width
            note_kind = obj.note_kind
            note_type = obj.note_type
            channel = obj.channel

            key = (measure, str(note_kind.value), lane, channel)
            long_notes[key].append((tick, obj))

    # Determine best resolution for output
    # Use a reasonable resolution that balances precision with file size
    # For original SUS compatibility, let's use a common subdivision
    resolution = 16  # Standard resolution that matches most SUS files

    # Process short notes and convert to SUS format
    for (measure, type_code, lane), notes in sorted(short_notes.items()):
        # Format the measure and lane for SUS format
        measure_str = f"{measure:03d}"
        lane_str = f"{lane:x}"

        # First, determine the actual required positions
        note_positions = {}
        for tick, note in notes:
            # Calculate position in the measure
            position = int((tick / SUS_TICKS_PER_MEASURE) * resolution)
            if position >= resolution:
                position = resolution - 1  # Limit to valid range

            # Get note type value - use the actual SUS note type encoding
            if hasattr(note, "note_type"):
                # For SUS format, we need the proper note type number
                if note.note_type == TapNoteType.TAP:
                    note_value = 1
                elif note.note_type == TapNoteType.EXTAP:
                    note_value = 2
                elif note.note_type == TapNoteType.FLICK:
                    note_value = 3
                elif note.note_type == TapNoteType.HELL:
                    note_value = 4
                elif note.note_type in AirNoteType:
                    note_value = note.note_type.value  # Air notes use their enum value
                else:
                    note_value = 1  # Default to TAP
            else:
                note_value = 1  # Default

            # Format width in base-36 properly (1-9, then a-z for 10-35)
            width_val = note.width
            if width_val <= 9:
                width_char = str(width_val)
            elif width_val <= 35:
                width_char = chr(ord("a") + width_val - 10)
            else:
                width_char = "1"  # Fallback to width 1

            # Format as a 2-character string (note_type + width)
            note_positions[position] = f"{note_value}{width_char}"

        # Now build the data string, only including necessary positions
        max_pos = max(note_positions.keys()) if note_positions else 0
        data_parts = ["00"] * (max_pos + 1)

        # Fill in actual note data
        for position, value in note_positions.items():
            data_parts[position] = value

        # Join data parts into a single string
        data = "".join(data_parts)

        # Remove trailing zeros to keep the file compact
        if data.endswith("00"):
            data = data.rstrip("0")

        # Output the SUS line
        output.append(f"#{measure_str}{type_code}{lane_str}: {data}")

    # Process long notes with same approach
    for (measure, note_kind, lane, channel), notes in sorted(long_notes.items()):
        # Format the measure, lane and channel for SUS format
        measure_str = f"{measure:03d}"
        lane_str = f"{lane:x}"

        # First, determine the actual required positions
        note_positions = {}
        for tick, note in notes:
            # Calculate position in the measure
            position = int((tick / SUS_TICKS_PER_MEASURE) * resolution)
            if position >= resolution:
                position = resolution - 1  # Limit to valid range

            # Get note type value - use proper SUS long note type encoding
            if hasattr(note, "note_type"):
                note_value = (
                    note.note_type.value
                )  # Long note types: START=1, END=2, STEP=3, etc.
            else:
                note_value = 1  # Default

            # Format width in base-36 properly (1-9, then a-z for 10-35)
            width_val = note.width
            if width_val <= 9:
                width_char = str(width_val)
            elif width_val <= 35:
                width_char = chr(ord("a") + width_val - 10)
            else:
                width_char = "1"  # Fallback to width 1

            # Format as a 2-character string (note_type + width)
            note_positions[position] = f"{note_value}{width_char}"

        # Now build the data string, only including necessary positions
        max_pos = max(note_positions.keys()) if note_positions else 0
        data_parts = ["00"] * (max_pos + 1)

        # Fill in actual note data
        for position, value in note_positions.items():
            data_parts[position] = value

        # Join data parts into a single string
        data = "".join(data_parts)

        # Remove trailing zeros to keep the file compact
        if data.endswith("00"):
            data = data.rstrip("0")

        # Output the SUS line
        output.append(f"#{measure_str}{note_kind}{lane_str}{channel}: {data}")

    return "\n".join(output)
