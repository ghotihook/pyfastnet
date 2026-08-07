"""FastNet protocol decoder — reads fastnet_decoder/data/fastnet.json and decodes
raw FastNet bytes into Python values, using that file as the single source of
truth for the protocol.

Why almost no protocol facts are hardcoded in this file
---------------------------------------------------------
The FastNet wire format is regular: every reading on the bus arrives as a small
record of (channel_id, format_byte, data_bytes).

  - channel_id says WHAT physical quantity this is (boat speed, depth, wind
    angle, ...).
  - format_byte says HOW the data_bytes are laid out - how many bytes, signed
    or unsigned, whether there's an extra "layout" byte carrying a sign or
    display suffix, and so on.

There are only a handful of distinct byte layouts in the whole protocol - we
call each one a "format template", and this file implements the decoding logic
for each template exactly once, as a small generic function (see
decode_channel_value below). Everything that varies between individual
channels - names, which format template they use, what Signal K path and unit
they map to - lives as DATA in fastnet_decoder/data/fastnet.json, not as
Python code. See fastnet_decoder/data/README.md for a full explanation of that
file's structure.

The practical result: adding a newly-identified channel, or fixing a wrong
Signal K mapping, is a one-line edit to fastnet.json. It does NOT require
touching this file, unless the new channel needs a genuinely new byte layout
that none of the existing format templates cover (rare - see the "unsupported"
op below for what happens when that's the case).

A worked example, start to finish
------------------------------------
Say a Heading reading arrives with channel_id=0x49, format_byte=0x08, and
data_bytes=[0xCC, 0x29]:

  1. format_byte & 0x0F = 0x08, so fastnet.json's formatTemplates["0x08"]
     describes how to decode it (see the "layoutValue" branch below).
  2. That template pulls a 9-bit unsigned number out of the two bytes: 41.
  3. format_byte's top two bits select a divisor (here, 1), so value = 41.0.
  4. The template also pulls a 7-bit "layout" code out of byte 0: 0x66, which
     fastnet.json's segmentA lookup says means "°M" (magnetic bearing).
  5. decode_frame() looks up channel_id 0x49's name ("Heading") from
     fastnet.json's channels table, so the caller gets back:
       {"Heading": {"value": 41.0, "display_text": "41°M", "layout": "°M", ...}}
  6. If the caller then calls project() on that result, fastnet.json says
     channel 0x49 is a layout-routed bearing: layout "°M" means the value
     belongs at Signal K path "navigation.headingMagnetic", converted from
     degrees to radians.

Module layout
---------------
  - decode_channel_value() / decode_frame()      - turn raw bytes into readings
  - probe_frame()                                - debug-only speculative decode
  - decode_ascii_frame() / decode_light_frame()  - the two non-channel message types
  - project()                                    - turn readings into Signal K paths
  - channel_map()                                - a human-readable reference table
"""
import datetime
import json
import logging
from pathlib import Path

from .logger import logger

_DATA_PATH = Path(__file__).resolve().parent / "data" / "fastnet.json"
SCHEMA = json.loads(_DATA_PATH.read_text(encoding="utf-8"))


# ── Loading the schema into convenient Python lookups ──────────────────────────
#
# fastnet.json always writes byte values (channel ids, addresses, bitmasks...)
# as hex strings like "0x41", because that's how this protocol's own
# documentation and B&G's channel numbers are normally written. Python code
# needs plain integers to index bytes and do bit arithmetic, so the two
# helpers below are the one place that conversion happens.

def _parse_hex(hex_string: str) -> int:
    """Turn a hex string like '0x41' into the plain integer 65.

    Example:
        _parse_hex("0x41") -> 65
    """
    return int(hex_string, 16)


def _hex_keyed_dict_to_int_keyed_dict(hex_keyed_dict: dict) -> dict:
    """Convert a dict whose keys are hex strings ('0x41') into an equivalent
    dict keyed by the plain integer (65). Used for every *_LOOKUP table below.

    Example:
        _hex_keyed_dict_to_int_keyed_dict({"0x01": "Low", "0x02": "Medium"})
        -> {1: "Low", 2: "Medium"}
    """
    int_keyed_dict = {}
    for hex_key, value in hex_keyed_dict.items():
        int_keyed_dict[_parse_hex(hex_key)] = value
    return int_keyed_dict


_FORMAT_TEMPLATES = SCHEMA["formatTemplates"]   # kept keyed by hex string, e.g. "0x08"
_FORMAT_SIZE_MAP = _hex_keyed_dict_to_int_keyed_dict(SCHEMA["formatSizeMap"])

# format_byte's top two bits are a plain 2-bit number (0, 1, 2, or 3) that
# selects how much to divide the raw integer by, and how many decimal places
# to show when formatting it - e.g. top bits = 2 -> divide by 100, so raw
# integer 12345 on the wire means the value 123.45.
_DIVISOR_BY_TOP_TWO_BITS = {int(key): value for key, value in SCHEMA["scaling"]["divisorByTopTwoBits"].items()}
_DECIMAL_PLACES_BY_DIVISOR = {int(key): value for key, value in SCHEMA["scaling"]["decimalPlacesByDivisor"].items()}

_LOOKUPS = SCHEMA["lookups"]
ADDRESS_LOOKUP = _hex_keyed_dict_to_int_keyed_dict(_LOOKUPS["addresses"])
COMMAND_LOOKUP = _hex_keyed_dict_to_int_keyed_dict(_LOOKUPS["commands"])
IGNORED_COMMANDS = set(_LOOKUPS["ignoredCommands"])
CHANNEL_LOOKUP = _hex_keyed_dict_to_int_keyed_dict(_LOOKUPS["channelNames"])
BACKLIGHT_LEVELS = _hex_keyed_dict_to_int_keyed_dict(_LOOKUPS["backlightLevels"])
SEGMENT_A = _hex_keyed_dict_to_int_keyed_dict(_LOOKUPS["segmentA"])
SEGMENT_B = _hex_keyed_dict_to_int_keyed_dict(_LOOKUPS["segmentB"])
_LAYOUT_SIGN = _LOOKUPS["layoutSign"]          # keyed by layout token string, e.g. "H[data]"
_LAYOUT_DISPLAY = _LOOKUPS["layoutDisplay"]    # keyed by layout token string
_AUTOPILOT_STATE = _LOOKUPS["autopilotState"]  # keyed by hex string low-byte, e.g. "0x02"

# Kept keyed by hex string, e.g. "0x41" - every lookup against this table below
# builds that hex string from a channel_id int as needed (f"0x{channel_id:02X}").
_CHANNELS = SCHEMA["channels"]

# Note: fastnet.json also has a "messages" section describing the LatLon and
# Light Intensity frame layouts. It is reference documentation only - this
# file does not read it. Those two message types are simple enough (one ASCII
# field, one single byte) that decode_ascii_frame() and decode_light_frame()
# below just implement them directly, rather than through a generic
# schema-driven mechanism the way channel records are.


def _lookup_or_unknown(lookup_table: dict, key: int) -> str:
    """Look up key in lookup_table; if it isn't there, return a readable
    "Unknown (0x..)" placeholder instead of raising an error.

    Used everywhere this file looks up an address, command, or channel name -
    none of those tables are guaranteed to be complete, since this protocol is
    still being reverse-engineered, so every lookup needs a graceful fallback.

    Example:
        _lookup_or_unknown({0x01: "Broadcast"}, 0x01) -> "Broadcast"
        _lookup_or_unknown({0x01: "Broadcast"}, 0x99) -> "Unknown (0x99)"
    """
    name = lookup_table.get(key)
    if name is not None:
        return name
    return f"Unknown (0x{key:02X})"


def extract_bits(data_bytes: bytes, pieces) -> int:
    """Pull an unsigned integer out of one or more bit-fields spread across
    data_bytes, then combine them into a single number.

    Each item in `pieces` describes one bit-field: which byte it lives in, a
    bitmask selecting which bits of that byte belong to this piece, and how
    far left to shift those bits once extracted (so a piece covering the
    "high" bits of a multi-byte number can be moved into its correct place
    before being combined with the other pieces).

    Worked example - format 0x08 (used by Heading) packs a 9-bit unsigned
    value across two bytes: the low bit of byte 0 is the value's high bit, and
    all of byte 1 is the value's low 8 bits:

        pieces = [
            {"byte": 0, "mask": "0x01", "shiftLeft": 8},  # 1 bit,  becomes bit 8
            {"byte": 1, "mask": "0xFF", "shiftLeft": 0},   # 8 bits, become bits 0-7
        ]

    For data_bytes = [0xCC, 0x29]:
        piece 1: (0xCC & 0x01) << 8  =  0  << 8  =  0
        piece 2: (0x29 & 0xFF) << 0  =  41 << 0  =  41
        combined (the two pieces OR'd together)   =  41

    Example:
        extract_bits(
            bytes([0xCC, 0x29]),
            [{"byte": 0, "mask": "0x01", "shiftLeft": 8},
             {"byte": 1, "mask": "0xFF", "shiftLeft": 0}],
        ) -> 41
    """
    combined_value = 0
    for piece in pieces:
        byte_value = data_bytes[piece["byte"]]
        mask = _parse_hex(piece["mask"])
        masked_bits = byte_value & mask
        shift_amount = piece.get("shiftLeft", 0)
        combined_value = combined_value | (masked_bits << shift_amount)
    return combined_value


def _layout_for(segment_code: int) -> str:
    """Look up a "layout" token (e.g. '°M', 'H[data]') from a SEGMENT_A byte
    code. Returns "TBC" ("to be confirmed") for any code not yet identified -
    this matches the original hand-written decoder's behaviour. None is
    reserved for the two confirmed-blank codes (0x00, 0x80), which really do
    mean "no indicator shown", not "unidentified".

    Example:
        _layout_for(0x66) -> "°M"
        _layout_for(0x93) -> "TBC"   # not in SEGMENT_A - unidentified so far
    """
    return SEGMENT_A.get(segment_code, "TBC")


def _sign_for(layout: str) -> int:
    """Return -1 if this layout token means the value should be negative,
    otherwise 1. Only a handful of tokens carry a negative sign (see
    fastnet.json's lookups.layoutSign) - everything else, including "TBC"
    and None, is treated as positive.

    Example:
        _sign_for("H[data]") -> -1
        _sign_for("°M") -> 1
    """
    return _LAYOUT_SIGN.get(layout, 1)


def _render_display(layout, formatted_number: str) -> str:
    """Wrap a formatted number string with whatever prefix/suffix its layout
    token calls for - e.g. "41" with layout "°M" becomes "41°M".

    fastnet.json's lookups.layoutDisplay describes this per layout token, as
    one of:
      - nothing at all (most tokens, and also "TBC"/None) - the number comes
        back unchanged.
      - a suffix, e.g. "°M" -> "41°M".
      - a prefix, e.g. "L[data]" -> "L-2.0".
      - a prefix AND "stripSign": true, e.g. "H[data]" -> the leading "-" is
        removed from the number first, because the H prefix already tells the
        reader the value is negative (so "H[data]" renders "-20.4" as
        "H20.4", not "H-20.4"). This is why "H[data]" and "L[data]" render
        differently even though both mean "negative value" - it comes
        straight from how the original B&G displays show it, not from any
        general rule.

    Example:
        _render_display("°M", "41") -> "41°M"
        _render_display("H[data]", "-20.4") -> "H20.4"
        _render_display("L[data]", "-2.0") -> "L-2.0"
    """
    if layout is None:
        return formatted_number

    display_rule = _LAYOUT_DISPLAY.get(layout)
    if display_rule is None:
        # No display rule for this token - e.g. "TBC", or a token whose sign
        # is already baked into the number with no extra decoration needed.
        return formatted_number

    text = formatted_number
    if display_rule.get("stripSign"):
        text = text.lstrip("-")
    if "prefix" in display_rule:
        text = display_rule["prefix"] + text
    if "suffix" in display_rule:
        text = text + display_rule["suffix"]
    return text


# ── channel 0xB5 (Autopilot Mode): the one documented escape hatch ─────────────
#
# Every other channel is decoded purely from its format template - the
# channel_id only matters for looking up its name. Channel 0xB5 is the sole
# exception: its 16-bit value is a composite of two separate pieces of
# information (engagement state + selected mode), not a plain scaled number,
# so it needs its own decoding function rather than a generic template.

def _split_autopilot_composite(raw: int):
    """Split Autopilot Mode's raw 16-bit number into its high byte
    (engagement state) and low byte (selected mode). Both
    _override_autopilot_mode (below) and _autopilot_signalk_state (further
    down, used by project()) need to split the same number the same way, so
    this is shared between them rather than duplicated.

    Example:
        _split_autopilot_composite(0x5102) -> (0x51, 0x02)   # engaged, Power mode
    """
    high_byte = (raw >> 8) & 0xFF
    low_byte = raw & 0xFF
    return high_byte, low_byte


def _override_autopilot_mode(data_bytes: bytes):
    """Decode channel 0xB5's raw bytes as engagement-state + mode, instead of
    as a plain scaled number. Returns (value, display_text, layout) - the same
    three pieces decode_channel_value returns for every other channel, so the
    caller can treat this result the same way as any other.

    Example (raw 16-bit number 0x5102 - engaged, Power mode selected):
        _override_autopilot_mode(bytes([0x51, 0x02])) -> (20738.0, "Power", None)
    """
    raw = int.from_bytes(data_bytes, byteorder="big", signed=True)
    value = float(raw)
    high_byte, low_byte = _split_autopilot_composite(raw)

    if high_byte == 0x50:
        display_text = "Standby"
    elif high_byte in (0x51, 0x59):
        mode_entry = _AUTOPILOT_STATE.get(f"0x{low_byte:02X}")
        if mode_entry is not None:
            display_text = mode_entry["displayText"]
        else:
            display_text = f"Unknown ({raw})"
    else:
        display_text = f"Unknown ({raw})"

    layout = None  # this channel has no segment-display layout byte
    return value, display_text, layout


_OVERRIDES = {
    # Maps an override name (as referenced by a channel's "overrides" entry in
    # fastnet.json) to the Python function that implements it. This dict is
    # the ONLY place in the whole decoder where a specific channel_id gets
    # special-cased instead of going through a generic format template.
    "autopilotMode": _override_autopilot_mode,
}


def decode_channel_value(channel_id: int, format_byte: int, data_bytes: bytes):
    """Decode one channel record's data bytes into a
    {"channel_id", "value", "display_text", "layout"} dict, or return None if
    this record cannot be decoded (the format isn't recognised, or there were
    no data bytes at all).

    format_byte encodes two independent things, in different bits:
      - the low 4 bits (format_byte & 0x0F) select which format TEMPLATE
        describes the byte layout (see fastnet.json's formatTemplates).
      - the top 2 bits (format_byte >> 6) select a DIVISOR, used to turn the
        raw integer pulled out of the bytes into a properly-scaled value.
    These two things don't depend on the channel_id - the same format
    template is shared by many different channels.

    Example (a real captured Boatspeed (Knots) reading, channel 0x41):
        decode_channel_value(0x41, 0x92, bytes([0xF9, 0xDD]))
        -> {"channel_id": "0x41", "value": 4.77, "display_text": "4.77", "layout": None}

    Example (Heading, channel 0x49, from this module's worked example above):
        decode_channel_value(0x49, 0x08, bytes([0xCC, 0x29]))
        -> {"channel_id": "0x49", "value": 41.0, "display_text": "41°M", "layout": "°M"}
    """
    try:
        if len(data_bytes) == 0:
            return None

        format_bits = format_byte & 0x0F
        top_two_bits = (format_byte >> 6) & 0b11
        divisor = _DIVISOR_BY_TOP_TWO_BITS[top_two_bits]
        decimal_places = _DECIMAL_PLACES_BY_DIVISOR[divisor]

        channel_id_hex = f"0x{channel_id:02X}"
        format_bits_hex = f"0x{format_bits:02X}"

        # Check for a channel-specific override before falling back to the
        # generic format template (see the section above for why 0xB5 needs
        # this).
        channel_info = _CHANNELS.get(channel_id_hex, {})
        channel_overrides = channel_info.get("overrides", {})
        override_name = channel_overrides.get(format_bits_hex)
        if override_name is not None:
            override_function = _OVERRIDES[override_name]
            value, display_text, layout = override_function(data_bytes)
            return {
                "channel_id": channel_id_hex,
                "value": value,
                "display_text": display_text,
                "layout": layout,
            }

        template = _FORMAT_TEMPLATES.get(format_bits_hex)
        if template is None or template["op"] == "unsupported":
            # This format nibble has no known byte layout yet - e.g. 0x09 has
            # never been observed in captured data. Nothing can be decoded.
            logger.debug(f"       unsupported format {format_bits_hex}")
            return None

        op = template["op"]
        layout = None  # most format templates have no layout byte at all

        if op == "scaledInt":
            # A plain N-byte signed or unsigned integer, scaled by the
            # divisor. Used by most numeric channels, e.g. Boatspeed.
            start, end = template["valueBytes"]
            raw_integer = int.from_bytes(data_bytes[start:end], byteorder="big", signed=template["signed"])
            value = raw_integer / divisor
            display_text = f"{value:.{decimal_places}f}"

        elif op == "scaledBitfield":
            # Like scaledInt, but the integer is packed across specific bits
            # of specific bytes rather than being one contiguous N-byte
            # integer - see extract_bits() above.
            raw_integer = extract_bits(data_bytes, template["pieces"])
            value = raw_integer / divisor
            display_text = f"{value:.{decimal_places}f}"

        elif op == "signedLayoutValue":
            # One byte in the record is a "layout" code that gives both the
            # sign of the value and how to decorate its display text - e.g.
            # Rudder Angle uses this.
            layout_byte_value = data_bytes[template["layoutByte"]]
            layout = _layout_for(layout_byte_value)

            if "pieces" in template:
                unsigned_integer = extract_bits(data_bytes, template["pieces"])
            else:
                start, end = template["valueBytes"]
                unsigned_integer = int.from_bytes(data_bytes[start:end], byteorder="big", signed=False)

            sign = _sign_for(layout)
            value = sign * unsigned_integer / divisor
            display_text = _render_display(layout, f"{value:.{decimal_places}f}")

        elif op == "layoutValue":
            # Also has a layout byte, but here it only affects the DISPLAY
            # text, not the sign of the value (unlike signedLayoutValue
            # above). Used by Heading - see this module's worked example.
            layout_bits_spec = template["layoutBits"]
            byte_to_read = data_bytes[layout_bits_spec["byte"]]
            mask = _parse_hex(layout_bits_spec["mask"])
            masked_bits = byte_to_read & mask
            layout_code = masked_bits >> layout_bits_spec["shiftRight"]
            layout = _layout_for(layout_code)

            unsigned_integer = extract_bits(data_bytes, template["pieces"])
            value = unsigned_integer / divisor
            display_text = _render_display(layout, f"{value:.{decimal_places}f}")

        elif op == "durationHMS":
            # Three bytes are hours, minutes, seconds (a fourth "status" byte
            # is ignored) - used by the Timer channel. value is stored as
            # total seconds; display_text is a human-readable "H:MM:SS"
            # string.
            hours = data_bytes[template["hByte"]]
            minutes = data_bytes[template["mByte"]]
            seconds = data_bytes[template["sByte"]]
            value = float(hours * 3600 + minutes * 60 + seconds)
            display_text = str(datetime.timedelta(hours=hours, minutes=minutes, seconds=seconds))

        elif op == "segmentDisplay":
            # This channel is only ever broadcast as raw 7-segment-display
            # glyphs, with no separate numeric value - by protocol design,
            # value is always None here. Each data byte maps independently to
            # one glyph via SEGMENT_B.
            value = None
            glyphs = []
            for data_byte in data_bytes:
                glyphs.append(SEGMENT_B.get(data_byte, "TBC"))
            display_text = "".join(glyphs)

        elif op == "pairedScaledInt":
            # Two independent signed integers packed into one record, e.g.
            # Boatspeed (Raw) / Heading (Raw). Only the first is returned as
            # "value" - both appear in display_text as "first / second".
            first_start, first_end = template["firstBytes"]
            second_start, second_end = template["secondBytes"]
            first = int.from_bytes(data_bytes[first_start:first_end], byteorder="big", signed=template["signed"])
            second = int.from_bytes(data_bytes[second_start:second_end], byteorder="big", signed=template["signed"])
            first = first / divisor
            second = second / divisor
            value = first
            display_text = f"{first:.{decimal_places}f} / {second:.{decimal_places}f}"

        else:
            # A format template exists but names an op this file doesn't
            # implement. Shouldn't happen with a well-formed fastnet.json,
            # but fail safely rather than raising.
            logger.debug(f"       unhandled op {op!r} for format {format_bits_hex}")
            return None

        return {
            "channel_id": channel_id_hex,
            "value": value,
            "display_text": display_text,
            "layout": layout,
        }

    except Exception as e:
        logger.error(f"Error decoding channel 0x{channel_id:02X}: {e}")
        return None


# ── frame-level decoders (envelope walking) ─────────────────────────────────
#
# A Broadcast frame's body is a sequence of channel records, back to back:
# [channel_id, format_byte, data_bytes..., channel_id, format_byte, data_bytes..., ...]
# decode_frame() below walks that sequence, decoding one record at a time.

def decode_frame(frame: bytes) -> dict:
    """Decode a complete Broadcast-command frame (header + body + checksums
    already validated by FrameBuffer) into
    {"to_address", "from_address", "command", "values": {channel_name: {...}}}.
    Returns {"error": "..."} if the frame's body doesn't parse cleanly.

    Example (a real captured frame carrying Boatspeed (Knots) and Boatspeed (Raw)):
        decode_frame(bytes.fromhex("ff010a01f54192f9dd420a01ec082cea"))
        -> {"to_address": "Entire System",
            "from_address": "Normal CPU (Depth Board in H2000)",
            "command": "Broadcast",
            "values": {
                "Boatspeed (Knots)": {"channel_id": "0x41", "value": 4.77,
                                       "display_text": "4.77", "layout": None},
                "Boatspeed (Raw)":   {"channel_id": "0x42", "value": 492.0,
                                       "display_text": "492 / 2092", "layout": None},
            }}
    """
    try:
        to_address = frame[0]
        from_address = frame[1]
        body_size = frame[2]
        command = frame[3]
        # frame[4] is the header checksum - FrameBuffer already validated it
        # before calling this function.
        body = frame[5:-1]

        if len(body) < 2 or len(body) != body_size:
            logger.debug(f"FRAME discard  body-size  expected={body_size}  actual={len(body)}")
            return {"error": "Invalid body size"}

        decoded_data = {
            "to_address": _lookup_or_unknown(ADDRESS_LOOKUP, to_address),
            "from_address": _lookup_or_unknown(ADDRESS_LOOKUP, from_address),
            "command": _lookup_or_unknown(COMMAND_LOOKUP, command),
            "values": {},
        }

        index = 0
        while index < len(body):
            if index + 1 >= len(body):
                logger.debug(f"  CH  incomplete header at index={index}")
                return {"error": "Insufficient bytes for channel header"}

            channel_id = body[index]
            format_byte = body[index + 1]
            channel_name = _lookup_or_unknown(CHANNEL_LOOKUP, channel_id)
            index += 2

            format_bits = format_byte & 0x0F
            data_length = _FORMAT_SIZE_MAP.get(format_bits, 0)
            if index + data_length > len(body):
                logger.debug(
                    f"  CH  0x{channel_id:02X} {channel_name}  "
                    f"incomplete  need={data_length}B  have={len(body) - index}B"
                )
                return {"error": f"Incomplete data for channel 0x{channel_id:02X}"}

            data_bytes = body[index:index + data_length]
            index += data_length

            decoded_value = decode_channel_value(channel_id, format_byte, data_bytes)
            decoded_data["values"][channel_name] = decoded_value

            if decoded_value:
                logger.debug(
                    f"  CH  0x{channel_id:02X} {channel_name}  "
                    f"fmt=0x{format_byte:02X}  data=[{data_bytes.hex()}]  "
                    f"value={decoded_value['value']}  "
                    f"display='{decoded_value['display_text']}'  "
                    f"layout={decoded_value['layout']}"
                )
            else:
                logger.debug(
                    f"  CH  0x{channel_id:02X} {channel_name}  "
                    f"fmt=0x{format_byte:02X}  data=[{data_bytes.hex()}]  (no decode)"
                )

        return decoded_data

    except Exception as e:
        logger.error(f"Unexpected error decoding frame: {e}  [{frame.hex()}]")
        return {"error": "Decoding failure"}


def probe_frame(frame: bytes) -> None:
    """Speculatively unpack a non-Broadcast frame using the same channel-record
    layout as decode_frame(), for reverse-engineering only.

    The body layout of non-Broadcast commands (pilot messages, NMEA-sourced
    data, etc.) is NOT known to actually match the Broadcast channel-record
    format, so everything logged here is a guess: results are logged at DEBUG
    and are never queued or returned to any caller. The point is purely to let
    a human eyeball, in the logs, whether the same (channel_id, format_byte,
    data...) structure seems to hold for these frames too.

    This function has no return value - its only output is DEBUG log lines,
    e.g. calling it on a Keep Alive frame might log something like:
        PROBE cmd=Keep Alive  All FFDs←Normal CPU (Depth Board in H2000)  body=[...]
    """
    if not logger.isEnabledFor(logging.DEBUG):
        return  # skip all the work below if nobody would see the output anyway
    try:
        to_address = frame[0]
        from_address = frame[1]
        command = frame[3]
        body = frame[5:-1]

        to_name = _lookup_or_unknown(ADDRESS_LOOKUP, to_address)
        from_name = _lookup_or_unknown(ADDRESS_LOOKUP, from_address)
        cmd_name = _lookup_or_unknown(COMMAND_LOOKUP, command)
        logger.debug(f"  PROBE cmd={cmd_name}  {to_name}←{from_name}  body=[{body.hex()}]")

        index = 0
        while index < len(body):
            if index + 1 >= len(body):
                logger.debug(f"    PROBE trailing byte  [{body[index:].hex()}]")
                break

            channel_id = body[index]
            format_byte = body[index + 1]
            channel_name = _lookup_or_unknown(CHANNEL_LOOKUP, channel_id)
            index += 2

            format_bits = format_byte & 0x0F
            data_length = _FORMAT_SIZE_MAP.get(format_bits, 0)

            if data_length == 0:
                logger.debug(
                    f"    PROBE 0x{channel_id:02X} {channel_name}  "
                    f"fmt=0x{format_byte:02X}  unknown format, stop  "
                    f"remaining=[{body[index:].hex()}]"
                )
                break
            if index + data_length > len(body):
                logger.debug(
                    f"    PROBE 0x{channel_id:02X} {channel_name}  "
                    f"fmt=0x{format_byte:02X}  incomplete  need={data_length}B  "
                    f"have={len(body) - index}B  remaining=[{body[index:].hex()}]"
                )
                break

            data_bytes = body[index:index + data_length]
            index += data_length

            decoded = decode_channel_value(channel_id, format_byte, data_bytes)
            if decoded:
                logger.debug(
                    f"    PROBE 0x{channel_id:02X} {channel_name}  "
                    f"fmt=0x{format_byte:02X}  data=[{data_bytes.hex()}]  "
                    f"value={decoded['value']}  display='{decoded['display_text']}'  "
                    f"layout={decoded['layout']}"
                )
            else:
                logger.debug(
                    f"    PROBE 0x{channel_id:02X} {channel_name}  "
                    f"fmt=0x{format_byte:02X}  data=[{data_bytes.hex()}]  (no decode)"
                )

    except Exception as e:
        logger.debug(f"  PROBE error: {e}  [{frame.hex()}]")


def decode_ascii_frame(frame: bytes) -> dict:
    """Decode a LatLon-command frame. Its body is not a channel record at all -
    it's a single ASCII position-fix string, so it's handled directly here
    rather than through decode_channel_value.

    Example (a real captured position fix, 33°52.450'S 151°13.920'E):
        decode_ascii_frame(bytes.fromhex(
            "ff601503894e50333335322e3435305331353131332e3932304572"))
        -> {"to_address": "Entire System",
            "from_address": "External Compass (NMEA FFD 60)",
            "command": "LatLon",
            "values": {"LatLon": {"channel_id": "0x4E", "value": None,
                                   "display_text": "3352.450S15113.920E",
                                   "layout": None}}}
    """
    try:
        to_address = frame[0]
        from_address = frame[1]
        command = frame[3]
        # Deliberately no length check on body here (unlike decode_frame /
        # decode_light_frame): a too-short body raises IndexError below and is
        # caught by the except block, same end result as an explicit check.
        body = frame[5:-1]

        channel_id = body[0]
        # body[0] is NOT a generic channel id - it's a marker byte that varies
        # by GPS unit (0x47, 0x4E, ...). This function is only ever called for
        # LatLon frames, so the entry below is named from the command
        # ("LatLon"), not from this byte. Looking it up in CHANNEL_LOOKUP
        # previously produced nonsense names like "Apparent Wind Speed (Raw)".
        # The raw byte is kept as channel_id in the returned dict purely for
        # diagnostics.
        # body[1] is a format byte, unused for ASCII frames.
        data_bytes = body[2:]

        cmd_name = _lookup_or_unknown(COMMAND_LOOKUP, command)

        try:
            ascii_text = data_bytes.decode("ascii").strip()
        except UnicodeDecodeError as e:
            logger.warning(f"  CH  0x{channel_id:02X} {cmd_name}  ASCII decode failed: {e}")
            return {"error": "ASCII decode failed"}

        return {
            "to_address": _lookup_or_unknown(ADDRESS_LOOKUP, to_address),
            "from_address": _lookup_or_unknown(ADDRESS_LOOKUP, from_address),
            "command": cmd_name,
            "values": {
                cmd_name: {
                    "channel_id": f"0x{channel_id:02X}",
                    "value": None,
                    "display_text": ascii_text,
                    "layout": None,
                }
            },
        }

    except Exception as e:
        logger.error(f"Error decoding ASCII frame: {e}")
        return {"error": str(e)}


def decode_light_frame(frame: bytes) -> dict:
    """Decode a Light Intensity (0xC9) command into the system backlight
    level. Broadcast from a Pilot FFD to the whole system; the body is a
    single byte giving the level (Off/Low/Medium/High). Surfaced as a
    synthetic "Backlight" channel so it queues like other channel data, even
    though it isn't a real FastNet channel record.

    Example (a real captured "set to Low" frame):
        decode_light_frame(bytes.fromhex("ff5001c9e701ff"))
        -> {"to_address": "Entire System",
            "from_address": "Pilot FFD (50)",
            "command": "Light Intensity",
            "values": {"Backlight": {"channel_id": None, "value": 1.0,
                                      "display_text": "Low", "layout": None}}}
    """
    try:
        to_address = frame[0]
        from_address = frame[1]
        command = frame[3]
        body = frame[5:-1]

        if len(body) < 1:
            return {"error": "Invalid body size"}

        level = body[0]
        cmd_name = _lookup_or_unknown(COMMAND_LOOKUP, command)
        display_text = BACKLIGHT_LEVELS.get(level, f"Unknown ({level})")
        logger.debug(f"  CH  Backlight  level={level}  display='{display_text}'")

        return {
            "to_address": _lookup_or_unknown(ADDRESS_LOOKUP, to_address),
            "from_address": _lookup_or_unknown(ADDRESS_LOOKUP, from_address),
            "command": cmd_name,
            "values": {
                "Backlight": {
                    "channel_id": None,  # not a real channel id - synthetic entry
                    "value": float(level),
                    "display_text": display_text,
                    "layout": None,
                }
            },
        }

    except Exception as e:
        logger.error(f"Error decoding Light Intensity frame: {e}")
        return {"error": str(e)}


# ── SignalK projection ──────────────────────────────────────────────────────
#
# project() turns a decoded frame's rich {"value", "display_text", "layout"}
# readings into the canonical {signalk_path: SI_value} view that most callers
# actually want. Everything it needs to know about each channel - its Signal K
# path, unit, and how to convert the raw value - comes from that channel's
# "signalk" entry in fastnet.json.

def _channel_id_from_entry(decoded_entry: dict):
    """Parse a decoded value's channel_id string ('0xC1') back into a plain
    integer, or return None if there isn't one (e.g. the synthetic
    "Backlight" entry from decode_light_frame has channel_id=None, since it
    isn't a real FastNet channel).

    Example:
        _channel_id_from_entry({"channel_id": "0xC1", "value": 7.3}) -> 193   # 0xC1
        _channel_id_from_entry({"channel_id": None, "value": 1.0}) -> None
    """
    channel_id_hex = decoded_entry.get("channel_id")
    if not channel_id_hex:
        return None
    try:
        return int(channel_id_hex, 16)
    except (ValueError, TypeError):
        return None


def _apply_transform(value, transform: dict):
    """Convert a raw decoded value into its Signal K (SI-unit) equivalent,
    using one of the small set of transform types fastnet.json can describe:
      - "identity": value is already in SI units, return it unchanged.
      - "scale":    multiply by a fixed factor (e.g. knots -> m/s).
      - "affine":   multiply by a scale AND add an offset (e.g. °C -> K).
    "overrideEnum" transforms (channel 0xB5) are handled separately by
    _autopilot_signalk_state, not by this function.

    Example:
        _apply_transform(10.0, {"type": "scale", "factor": 0.514444}) -> 5.14444   # knots -> m/s
        _apply_transform(20.0, {"type": "affine", "scale": 1, "offset": 273.15}) -> 293.15   # °C -> K
    """
    transform_type = transform["type"]
    if transform_type == "identity":
        return value
    if transform_type == "scale":
        return value * transform["factor"]
    if transform_type == "affine":
        return value * transform.get("scale", 1) + transform.get("offset", 0)
    # An unrecognised transform type means fastnet.json is malformed - fail
    # loudly rather than silently returning the wrong value.
    raise ValueError(f"unhandled transform type {transform_type!r}")


def _autopilot_signalk_state(value):
    """Channel 0xB5's Signal K projection: the same composite-byte decoding as
    _override_autopilot_mode above, but returning the Signal K enum string
    (e.g. "directControl") instead of the human display text (e.g. "Power").

    Example (same 0x5102 - engaged, Power mode - as _override_autopilot_mode's example):
        _autopilot_signalk_state(20738.0) -> "directControl"
    """
    if value is None:
        return None
    raw = int(value)
    high_byte, low_byte = _split_autopilot_composite(raw)
    if high_byte == 0x50:
        return "standby"
    if high_byte in (0x51, 0x59):
        mode_entry = _AUTOPILOT_STATE.get(f"0x{low_byte:02X}")
        if mode_entry is not None:
            return mode_entry["signalk"]
        return None
    return None


def parse_position(ascii_text):
    """Parse a FastNet LatLon fix string, e.g. '3352.450S15113.920E', into
    {"latitude": ..., "longitude": ...} in decimal degrees. The format is
    DDMM.MMM<N|S> followed by DDDMM.MMM<E|W> (degrees, then minutes with a
    decimal fraction). Returns None if the text doesn't look like a fix.

    Example:
        parse_position("3352.450S15113.920E")
        -> {"latitude": -33.874166666666667, "longitude": 151.232}
    """
    if not ascii_text:
        return None

    # Find the compass-direction letters first - they mark where latitude
    # ends and where longitude ends.
    lat_end = max(ascii_text.find("N"), ascii_text.find("S"))
    lon_end = max(ascii_text.find("E"), ascii_text.find("W"))
    if lat_end == -1 or lon_end == -1:
        return None

    try:
        latitude_digits = ascii_text[:lat_end]
        latitude_direction = ascii_text[lat_end]
        longitude_digits = ascii_text[lat_end + 1:lon_end]
        longitude_direction = ascii_text[lon_end]

        # First 2 digits are whole degrees, the rest (with its decimal point)
        # is minutes - divide minutes by 60 to fold them into the degrees.
        latitude = int(latitude_digits[:2]) + float(latitude_digits[2:]) / 60.0
        # Longitude degrees are 3 digits wide (up to 180°), not 2.
        longitude = int(longitude_digits[:3]) + float(longitude_digits[3:]) / 60.0
    except (ValueError, IndexError):
        return None

    if latitude_direction == "S":
        latitude = -latitude
    if longitude_direction == "W":
        longitude = -longitude

    return {"latitude": latitude, "longitude": longitude}


def unit_for(path: str) -> str:
    """Return the SI unit string for a Signal K path emitted by project(), or
    "" if the path isn't recognised. Scans every channel's schema entry for a
    matching path - there are only around 100 channels, and this function
    isn't called in a hot loop, so a simple scan is both clear and fast
    enough; there's no need for a precomputed lookup table.

    Example:
        unit_for("navigation.speedThroughWater") -> "m/s"
        unit_for("nonexistent.path") -> ""
    """
    for channel_info in _CHANNELS.values():
        signalk_info = channel_info.get("signalk")
        if not signalk_info:
            continue

        if signalk_info.get("path") == path and "pathParam" not in signalk_info:
            return signalk_info.get("unit") or ""

        if "routes" in signalk_info:
            for route in signalk_info["routes"].values():
                if route["path"] == path:
                    return signalk_info.get("unit") or ""

    # A few paths aren't tied to any single channel's schema entry.
    if path == "navigation.position":
        return "deg"
    if path == "steering.autopilot.state":
        return "enum"
    if path.startswith("electrical.batteries.") and path.endswith(".voltage"):
        return "V"
    return ""


def _pick_lowest_priority_reading(candidates):
    """Given a list of (fallback_priority, value, signalk_info) tuples, return
    the converted (SI-unit) value of whichever candidate has the lowest
    priority number AND an actual (non-None) value - or None if none of them
    have a value.

    Used by project() to resolve the depth fallback chain: metres (priority
    0) wins over feet (priority 1), which wins over fathoms (priority 2), but
    only among whichever of those channels actually showed up in this
    particular frame.

    Example (both metres and feet present - metres wins, since it has the
    lower priority number, even though it's listed second here):
        _pick_lowest_priority_reading([
            (1, 24.0, {"transform": {"type": "scale", "factor": 0.3048}}),  # feet
            (0, 7.3, {"transform": {"type": "identity"}}),                   # metres
        ]) -> 7.3
    """
    def priority_of(candidate):
        priority, value, signalk_info = candidate
        return priority

    candidates_by_priority = sorted(candidates, key=priority_of)
    for priority, value, signalk_info in candidates_by_priority:
        if value is not None:
            return _apply_transform(value, signalk_info["transform"])
    return None


def project(decoded_frame: dict, battery_id: str = "house") -> dict:
    """Turn a decoded frame (from decode_frame/decode_ascii_frame/
    decode_light_frame) into a {signalk_path: value} dict - the canonical,
    SI-unit view of the data.

    Every channel is looked up in fastnet.json's "channels" table to find out
    where it belongs in Signal K and how to convert its raw value. A channel
    with no Signal K mapping in the schema still gets emitted, under a
    generic "bandg.unknown.0x.." path, so that decodable data is never
    silently lost just because nobody has mapped it to a proper Signal K path
    yet.

    Example (a real captured frame carrying Heel Angle, Fore/Aft Trim, Battery
    Volts, and one still-unmapped channel, 0x3B):
        project(decode_frame(bytes.fromhex(
            "ff051401e78d8105263b3101fa344700f300cc9b4700a000099b")))
        -> {"electrical.batteries.house.voltage": 13.18,
            "navigation.attitude.roll": -0.3560471674068432,
            "navigation.attitude.pitch": -0.015707963267948967,
            "bandg.unknown.0x3B": 506.0}
    """
    command = decoded_frame.get("command")
    decoded_values = decoded_frame.get("values", {})
    result = {}

    if command == "LatLon":
        # LatLon frames carry a position fix as ASCII text, not a channel
        # record - handle that separately and return early.
        for entry in decoded_values.values():
            position = parse_position(entry.get("display_text"))
            if position is not None:
                result["navigation.position"] = position
        return result

    # Depth can arrive on up to three different channels (metres, feet,
    # fathoms), depending on how the instrument is configured. We want
    # whichever one is actually present in THIS frame, preferring metres,
    # then feet, then fathoms - collect every depth reading seen during the
    # main loop below, and resolve the winner afterwards.
    depth_candidates = []   # list of (fallback_priority, value, signalk_info)
    depth_path = None

    for entry in decoded_values.values():
        channel_id = _channel_id_from_entry(entry)
        if channel_id is None:
            continue
        value = entry.get("value")

        channel_id_hex = f"0x{channel_id:02X}"
        channel_info = _CHANNELS.get(channel_id_hex, {})
        signalk_info = channel_info.get("signalk")

        if signalk_info is None:
            # No Signal K mapping exists for this channel yet (it may not
            # even be a named channel at all) - keep the raw value under a
            # generic path rather than dropping it silently.
            if value is not None:
                result[f"bandg.unknown.0x{channel_id:02X}"] = value
            continue

        if signalk_info.get("drop"):
            continue  # deliberately excluded (protocol/control channel)

        if "collapsedInto" in signalk_info:
            continue  # a redundant unit-variant of another channel - skip it

        if "fallbackGroup" in signalk_info:
            depth_candidates.append((signalk_info["fallbackPriority"], value, signalk_info))
            depth_path = signalk_info["path"]
            continue

        transform = signalk_info["transform"]

        if transform["type"] == "overrideEnum":
            # Channel 0xB5 (Autopilot Mode): value is a composite byte pair,
            # not a plain number, so it needs its own conversion function
            # rather than the generic transforms _apply_transform handles.
            state = _autopilot_signalk_state(value)
            if state is not None:
                result[signalk_info["path"]] = state
            continue

        if "routedBy" in signalk_info:
            # A bearing whose Signal K path depends on which layout this
            # particular reading arrived with - e.g. Heading routes to
            # headingMagnetic or headingTrue depending on that byte.
            layout = entry.get("layout")
            if layout == "°T":
                route = signalk_info["routes"]["°T"]
            else:
                route = signalk_info["routes"]["°M"]  # default when layout is None/unrecognised
            if value is None:
                result[route["path"]] = None
            else:
                result[route["path"]] = _apply_transform(value, transform)
            continue

        # The common case: a plain channel with one fixed Signal K path.
        path = signalk_info["path"]
        if "pathParam" in signalk_info:
            # e.g. "electrical.batteries.{id}.voltage" - fill in which
            # battery this reading belongs to.
            path = path.format(id=battery_id)

        if value is None:
            result[path] = None
        else:
            result[path] = _apply_transform(value, transform)

    if depth_candidates:
        winning_depth = _pick_lowest_priority_reading(depth_candidates)
        if winning_depth is not None:
            result[depth_path] = winning_depth

    return result


# ── master reference table ──────────────────────────────────────────────────

def _strip_suffix(text: str, suffix: str) -> str:
    """Return text with suffix removed from the end, if present; otherwise
    return text unchanged. (Python's built-in str.removesuffix() would do
    this in one call, but this project supports Python 3.7+, which predates
    that method.)

    Example:
        _strip_suffix("navigation.headingMagnetic", "Magnetic") -> "navigation.heading"
        _strip_suffix("navigation.speedThroughWater", "Magnetic") -> "navigation.speedThroughWater"
    """
    if text.endswith(suffix):
        return text[:-len(suffix)]
    return text


def channel_map() -> dict:
    """Build a human-readable reference table: for every known channel id,
    its B&G name, Signal K path, unit, and a "kind" describing how it's
    handled (standard / vendor / routed / depth fallback / collapsed / drop /
    unknown). Used to generate docs/channel_map.md - see
    docs/generate_channel_map.py.

    Example (one row of each kind):
        channel_map()[0x41]
        -> {"name": "Boatspeed (Knots)", "path": "navigation.speedThroughWater",
            "unit": "m/s", "kind": "standard"}
        channel_map()[0x49]
        -> {"name": "Heading", "path": "navigation.heading{Magnetic,True}",
            "unit": "rad", "kind": "routed(M/T)"}
        channel_map()[0x00]
        -> {"name": "Node Reset", "path": "—", "unit": "", "kind": "drop"}
        channel_map()[0x0C]
        -> {"name": "Linear 5", "path": "bandg.unknown.0x0C", "unit": "", "kind": "unknown"}
    """
    result = {}
    for channel_id, name in sorted(CHANNEL_LOOKUP.items()):
        channel_id_hex = f"0x{channel_id:02X}"
        channel_info = _CHANNELS.get(channel_id_hex, {})
        signalk_info = channel_info.get("signalk")

        if signalk_info is None:
            path = f"bandg.unknown.0x{channel_id:02X}"
            unit = ""
            kind = "unknown"

        elif signalk_info.get("drop"):
            path = "—"
            unit = ""
            kind = "drop"

        elif "collapsedInto" in signalk_info:
            path = f"→ {signalk_info['collapsedInto']}"
            unit = ""
            kind = "collapsed"

        elif "fallbackGroup" in signalk_info:
            path = signalk_info["path"]
            unit = signalk_info.get("unit", "")
            kind = "standard(depth fallback)"

        elif signalk_info["transform"]["type"] == "overrideEnum":
            path = signalk_info["path"]
            unit = signalk_info.get("unit", "")
            kind = "standard"

        elif "routedBy" in signalk_info:
            magnetic_path = signalk_info["routes"]["°M"]["path"]
            # e.g. "navigation.headingMagnetic" -> "navigation.heading", so
            # the reference table can show one row covering both the
            # Magnetic and True variants: "navigation.heading{Magnetic,True}".
            path_stem = _strip_suffix(magnetic_path, "Magnetic")
            path = f"{path_stem}{{Magnetic,True}}"
            unit = signalk_info.get("unit", "")
            kind = "routed(M/T)"

        elif signalk_info["path"].startswith("bandg."):
            path = signalk_info["path"]
            unit = signalk_info.get("unit", "")
            kind = "vendor"

        else:
            path = signalk_info["path"]
            unit = signalk_info.get("unit", "")
            kind = "standard"

        result[channel_id] = {"name": name, "path": path, "unit": unit, "kind": kind}

    return result
