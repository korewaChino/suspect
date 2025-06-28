from . import c2s
from . import sus


def sus_to_c2s(
    sus_objects,
    sus_ticks_per_measure=sus.SUS_TICKS_PER_MEASURE,
    c2s_ticks_per_measure=c2s.C2S_TICKS_PER_MEASURE,
):

    c2s_definitions = []
    c2s_notes = []

    def sus_to_c2s_ticks(sus_ticks):
        """Convert SUS ticks to C2S ticks with proper scaling"""
        # SUS uses 1920 ticks per measure (480 ticks per beat * 4 beats)
        # C2S uses 384 ticks per measure
        # Scale proportionally: c2s_ticks = sus_ticks * (384 / 1920) = sus_ticks * 0.2
        scaled_ticks = int((sus_ticks * c2s_ticks_per_measure) / sus_ticks_per_measure)
        return scaled_ticks

    for obj in sus_objects:
        if isinstance(obj, sus.ShortNote):
            if obj.note_type == sus.TapNoteType["TAP"]:
                note = c2s.TapNote()
            if obj.note_type == sus.TapNoteType["EXTAP"]:
                note = c2s.ChargeNote()
            if obj.note_type == sus.TapNoteType["FLICK"]:
                note = c2s.FlickNote()
            if obj.note_type == sus.TapNoteType["HELL"]:
                note = c2s.MineNote()
            if obj.note_type == sus.AirNoteType["UP"]:
                note = c2s.AirNote()
                note.isUp = True
                note.direction = 0
            if obj.note_type == sus.AirNoteType["UP_LEFT"]:
                note = c2s.AirNote()
                note.isUp = True
                note.direction = -1
            if obj.note_type == sus.AirNoteType["UP_RIGHT"]:
                note = c2s.AirNote()
                note.isUp = True
                note.direction = 1
            if obj.note_type == sus.AirNoteType["DOWN"]:
                note = c2s.AirNote()
                note.isUp = False
                note.direction = 0
            if obj.note_type == sus.AirNoteType["DOWN_LEFT"]:
                note = c2s.AirNote()
                note.isUp = False
                note.direction = -1
            if obj.note_type == sus.AirNoteType["DOWN_RIGHT"]:
                note = c2s.AirNote()
                note.isUp = False
                note.direction = 1

            note.lane = obj.lane
            note.width = obj.width
            note.measure = obj.measure
            note.tick = sus_to_c2s_ticks(obj.tick)

            c2s_notes.append(note)

        if isinstance(obj, sus.LongNote):
            if obj.note_type == sus.LongNoteType["END"]:
                # Ignore end notes, they're handled differently in c2s
                continue

            next_idx = obj.linked.index(obj) + 1
            if next_idx == len(obj.linked):
                print(
                    "WARNING: Channel ends with a non-END note, assuming intended END"
                )
                continue

            next_obj = obj.linked[next_idx]
            if next_obj.note_kind != obj.note_kind:
                print(
                    "WARNING: Channel switches note kinds (goes from %s:%s to %s:%s at index %s) - Assuming intended END"
                    % (
                        obj.note_kind,
                        obj.note_type,
                        next_obj.note_kind,
                        next_obj.note_type,
                        next_idx,
                    )
                )
                continue

            start_measure = obj.measure
            start_ticks = sus_to_c2s_ticks(obj.tick)
            end_measure = next_obj.measure
            end_ticks = sus_to_c2s_ticks(next_obj.tick)

            diff_ticks = ((end_measure - start_measure) * c2s_ticks_per_measure) + (
                end_ticks - start_ticks
            )

            if obj.note_kind == sus.LongNoteKind["SLIDE"]:
                note = c2s.SlideNote()
                note.end_lane = next_obj.lane
                note.end_width = next_obj.width
                note.is_curve = (
                    obj.note_type == sus.LongNoteType["CONTROL"]
                    or obj.note_type == sus.LongNoteType["INVISIBLE"]
                )
            elif obj.note_kind == sus.LongNoteKind["HOLD"]:
                note = c2s.HoldNote()
            elif obj.note_kind == sus.LongNoteKind["AIR_HOLD"]:
                note = c2s.AirHold()

            note.measure = start_measure
            note.tick = start_ticks
            note.lane = obj.lane
            note.width = obj.width
            note.length = diff_ticks

            c2s_notes.append(note)

        if isinstance(obj, sus.BpmChange):
            definition = c2s.BpmSetting()
            definition.measure = obj.measure
            definition.tick = 0  # BPM changes typically happen at the start of measures
            definition.bpm = obj.definition.tempo
            c2s_definitions.append(definition)

        if isinstance(obj, sus.BarLength):
            definition = c2s.MeterSetting()
            definition.measure = obj.measure
            definition.tick = (
                0  # Bar length changes typically happen at the start of measures
            )
            definition.signature = (int(obj.length), 4)  # Convert to integer tuple
            c2s_definitions.append(definition)

    c2s_notes.sort(key=lambda note: note.measure + note.tick / c2s_ticks_per_measure)
    return (c2s_definitions, c2s_notes)


def c2s_to_sus(
    c2s_objects,
    c2s_ticks_per_measure=c2s.C2S_TICKS_PER_MEASURE,
    sus_ticks_per_measure=sus.SUS_TICKS_PER_MEASURE,
):
    """
    Convert a list of C2S objects to a list of SUS objects.

    Args:
        c2s_objects: List of C2S objects (definitions and notes)
        c2s_ticks_per_measure: Ticks per measure in C2S format
        sus_ticks_per_measure: Ticks per measure in SUS format

    Returns:
        List of SUS objects
    """
    sus_objects = []

    # Helper function to convert ticks
    def c2s_to_sus_ticks(c2s_ticks):
        """Convert C2S ticks to SUS ticks with proper scaling"""
        # C2S uses 384 ticks per measure
        # SUS uses 1920 ticks per measure (480 ticks per beat * 4 beats)
        # Scale proportionally: sus_ticks = c2s_ticks * (1920 / 384) = c2s_ticks * 5
        scaled_ticks = int((c2s_ticks * sus_ticks_per_measure) / c2s_ticks_per_measure)
        return scaled_ticks

    # Sort by measure and tick for consistent processing
    c2s_objects.sort(
        key=lambda obj: getattr(obj, "measure", 0)
        + getattr(obj, "tick", 0) / c2s_ticks_per_measure
    )

    # Keep track of BPM definitions to avoid duplicates
    bpm_defs = {}
    channels = {}  # Track channels for long notes
    channel_counter = 0

    # Process C2S objects
    for obj in c2s_objects:
        if isinstance(obj, c2s.BpmSetting):
            # Check if we've already seen this BPM value
            bpm_key = str(obj.bpm)
            if bpm_key not in bpm_defs:
                # Create BPM definition
                bpm_def = sus.BpmDefinition()
                bpm_def.identifier = (
                    f"{len(bpm_defs) + 1:02d}"  # Generate a unique identifier
                )
                bpm_def.tempo = obj.bpm
                bpm_defs[bpm_key] = bpm_def
                sus_objects.append(bpm_def)
            else:
                bpm_def = bpm_defs[bpm_key]

            # Create BPM change
            bpm_change = sus.BpmChange()
            bpm_change.measure = obj.measure
            bpm_change.definition = bpm_def

            sus_objects.append(bpm_change)

        elif isinstance(obj, c2s.MeterSetting):
            # Create bar length
            bar_length = sus.BarLength()
            bar_length.measure = obj.measure
            bar_length.length = obj.signature[0]  # Numerator of time signature

            sus_objects.append(bar_length)

        elif isinstance(obj, c2s.TapNote):
            note = sus.ShortNote()
            note.measure = obj.measure
            note.tick = c2s_to_sus_ticks(obj.tick)
            note.lane = obj.lane
            note.width = obj.width
            note.note_type = sus.TapNoteType.TAP

            sus_objects.append(note)

        elif isinstance(obj, c2s.ChargeNote):
            note = sus.ShortNote()
            note.measure = obj.measure
            note.tick = c2s_to_sus_ticks(obj.tick)
            note.lane = obj.lane
            note.width = obj.width
            note.note_type = sus.TapNoteType.EXTAP

            sus_objects.append(note)

        elif isinstance(obj, c2s.FlickNote):
            note = sus.ShortNote()
            note.measure = obj.measure
            note.tick = c2s_to_sus_ticks(obj.tick)
            note.lane = obj.lane
            note.width = obj.width
            note.note_type = sus.TapNoteType.FLICK

            sus_objects.append(note)

        elif isinstance(obj, c2s.MineNote):
            note = sus.ShortNote()
            note.measure = obj.measure
            note.tick = c2s_to_sus_ticks(obj.tick)
            note.lane = obj.lane
            note.width = obj.width
            note.note_type = sus.TapNoteType.HELL

            sus_objects.append(note)

        elif isinstance(obj, c2s.AirNote):
            note = sus.ShortNote()
            note.measure = obj.measure
            note.tick = c2s_to_sus_ticks(obj.tick)
            note.lane = obj.lane
            note.width = obj.width

            # Determine air note type based on direction and orientation
            if obj.isUp:
                if obj.direction > 0:
                    note.note_type = sus.AirNoteType.UP_RIGHT
                elif obj.direction < 0:
                    note.note_type = sus.AirNoteType.UP_LEFT
                else:
                    note.note_type = sus.AirNoteType.UP
            else:
                if obj.direction > 0:
                    note.note_type = sus.AirNoteType.DOWN_RIGHT
                elif obj.direction < 0:
                    note.note_type = sus.AirNoteType.DOWN_LEFT
                else:
                    note.note_type = sus.AirNoteType.DOWN

            sus_objects.append(note)

        elif isinstance(obj, c2s.HoldNote):
            # Generate a unique channel for this hold
            channel_id = f"{obj.measure}_{obj.tick}_{obj.lane}_{obj.width}"
            if channel_id not in channels:
                channel = chr(97 + (channel_counter % 26))  # a-z
                channels[channel_id] = channel
                channel_counter += 1
            else:
                channel = channels[channel_id]

            # Create start note
            start_note = sus.LongNote()
            start_note.measure = obj.measure
            start_note.tick = c2s_to_sus_ticks(obj.tick)
            start_note.lane = obj.lane
            start_note.width = obj.width
            start_note.note_kind = sus.LongNoteKind.HOLD
            start_note.note_type = sus.LongNoteType.START
            start_note.channel = channel

            # Calculate end note position
            end_ticks = obj.tick + obj.length
            end_measure = obj.measure + (end_ticks // c2s_ticks_per_measure)
            end_tick = end_ticks % c2s_ticks_per_measure

            # Create end note
            end_note = sus.LongNote()
            end_note.measure = end_measure
            end_note.tick = c2s_to_sus_ticks(end_tick)
            end_note.lane = obj.lane
            end_note.width = obj.width
            end_note.note_kind = sus.LongNoteKind.HOLD
            end_note.note_type = sus.LongNoteType.END
            end_note.channel = channel

            # Link the notes
            start_note.linked = [start_note, end_note]
            end_note.linked = [start_note, end_note]

            sus_objects.append(start_note)
            sus_objects.append(end_note)

        elif isinstance(obj, c2s.AirHold):
            # Generate a unique channel for this air hold
            channel_id = f"{obj.measure}_{obj.tick}_{obj.lane}_{obj.width}_air"
            if channel_id not in channels:
                channel = chr(97 + (channel_counter % 26))  # a-z
                channels[channel_id] = channel
                channel_counter += 1
            else:
                channel = channels[channel_id]

            # Create start note
            start_note = sus.LongNote()
            start_note.measure = obj.measure
            start_note.tick = c2s_to_sus_ticks(obj.tick)
            start_note.lane = obj.lane
            start_note.width = obj.width
            start_note.note_kind = sus.LongNoteKind.AIR_HOLD
            start_note.note_type = sus.LongNoteType.START
            start_note.channel = channel

            # Calculate end note position
            end_ticks = obj.tick + obj.length
            end_measure = obj.measure + (end_ticks // c2s_ticks_per_measure)
            end_tick = end_ticks % c2s_ticks_per_measure

            # Create end note
            end_note = sus.LongNote()
            end_note.measure = end_measure
            end_note.tick = c2s_to_sus_ticks(end_tick)
            end_note.lane = obj.lane
            end_note.width = obj.width
            end_note.note_kind = sus.LongNoteKind.AIR_HOLD
            end_note.note_type = sus.LongNoteType.END
            end_note.channel = channel

            # Link the notes
            start_note.linked = [start_note, end_note]
            end_note.linked = [start_note, end_note]

            sus_objects.append(start_note)
            sus_objects.append(end_note)

        elif isinstance(obj, c2s.SlideNote):
            # Generate a unique channel for this slide
            channel_id = f"{obj.measure}_{obj.tick}_{obj.lane}_{obj.width}_slide"
            if channel_id not in channels:
                channel = chr(97 + (channel_counter % 26))  # a-z
                channels[channel_id] = channel
                channel_counter += 1
            else:
                channel = channels[channel_id]

            # Create start note
            start_note = sus.LongNote()
            start_note.measure = obj.measure
            start_note.tick = c2s_to_sus_ticks(obj.tick)
            start_note.lane = obj.lane
            start_note.width = obj.width
            start_note.note_kind = sus.LongNoteKind.SLIDE
            start_note.channel = channel

            # Set note type based on if it's a curve
            if obj.is_curve:
                start_note.note_type = sus.LongNoteType.CONTROL
            else:
                start_note.note_type = sus.LongNoteType.START

            # Calculate end note position
            end_ticks = obj.tick + obj.length
            end_measure = obj.measure + (end_ticks // c2s_ticks_per_measure)
            end_tick = end_ticks % c2s_ticks_per_measure

            # Create end note
            end_note = sus.LongNote()
            end_note.measure = end_measure
            end_note.tick = c2s_to_sus_ticks(end_tick)
            end_note.lane = obj.end_lane
            end_note.width = obj.end_width
            end_note.note_kind = sus.LongNoteKind.SLIDE
            end_note.note_type = sus.LongNoteType.END
            end_note.channel = channel

            # Link the notes
            start_note.linked = [start_note, end_note]
            end_note.linked = [start_note, end_note]

            sus_objects.append(start_note)
            sus_objects.append(end_note)

    return sus_objects
