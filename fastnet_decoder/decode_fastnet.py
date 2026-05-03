import datetime
from .mappings import ADDRESS_LOOKUP, COMMAND_LOOKUP, CHANNEL_LOOKUP, FORMAT_SIZE_MAP
from .mappings import SEGMENT_A, SEGMENT_B, AUTOPILOT_MODES
from .logger import logger


_DIVISOR_MAP = {0b00: 1, 0b01: 10, 0b10: 100, 0b11: 1000}
_DECIMAL_PLACES_MAP = {1: 0, 10: 1, 100: 2, 1000: 3}

# Layout strings describe how the display reads around the numeric value.
# "[data]" is a placeholder for the number. Examples:
#   "[data]-"  →  value is positive, trailing minus means port/starboard convention
#   "-[data]"  →  value is negative (subtract sign)
#   "=[data]"  →  value is negative (equals sign variant)
#   "H[data]"  →  "H" prefix, e.g. H045 for a heading
#   "°M"       →  magnetic bearing, suffix added after value

def _sign_from_layout(layout: str) -> int:
    return -1 if layout in ("-[data]", "=[data]") else 1


def _display_from_layout(layout: str, formatted: str) -> str:
    if layout == "°M":      return f"{formatted}°M"
    if layout == "H[data]": return f"H{formatted}"
    if layout == "[data]H": return f"{formatted}H"
    if layout == "[data]=": return f"{formatted}="
    if layout == "[data]-": return f"{formatted}-"
    return formatted


def decode_frame(frame: bytes) -> dict:
    try:
        to_address   = frame[0]
        from_address = frame[1]
        body_size    = frame[2]
        command      = frame[3]
        # frame[4] is the header checksum — already validated by FrameBuffer before this is called
        body         = frame[5:-1]

        if len(body) < 2 or len(body) != body_size:
            logger.debug(f"FRAME discard  body-size  expected={body_size}  actual={len(body)}")
            return {"error": "Invalid body size"}

        to_name   = ADDRESS_LOOKUP.get(to_address)
        from_name = ADDRESS_LOOKUP.get(from_address)
        cmd_name  = COMMAND_LOOKUP.get(command)

        decoded_data = {
            "to_address":   to_name   if to_name   is not None else f"Unknown (0x{to_address:02X})",
            "from_address": from_name if from_name is not None else f"Unknown (0x{from_address:02X})",
            "command":      cmd_name  if cmd_name  is not None else f"Unknown (0x{command:02X})",
            "values":       {}
        }

        index = 0
        while index < len(body):
            if index + 1 >= len(body):
                logger.debug(f"  CH  incomplete header at index={index}")
                return {"error": "Insufficient bytes for channel header"}

            channel_id   = body[index]
            format_byte  = body[index + 1]
            channel_name = CHANNEL_LOOKUP.get(channel_id)
            if channel_name is None:
                channel_name = f"Unknown (0x{channel_id:02X})"
            index += 2

            data_length = FORMAT_SIZE_MAP.get(format_byte & 0x0F, 0)
            if index + data_length > len(body):
                logger.debug(
                    f"  CH  0x{channel_id:02X} {channel_name}  "
                    f"incomplete  need={data_length}B  have={len(body) - index}B"
                )
                return {"error": f"Incomplete data for channel 0x{channel_id:02X}"}

            data_bytes = body[index:index + data_length]
            index     += data_length

            decoded_value = decode_format_and_data(channel_id, format_byte, data_bytes)
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


def decode_ascii_frame(frame: bytes) -> dict:
    try:
        to_address   = frame[0]
        from_address = frame[1]
        command      = frame[3]
        body         = frame[5:-1]

        channel_id   = body[0]
        # body[1] is a format byte — not used for ASCII frames
        data_bytes   = body[2:]
        channel_name = CHANNEL_LOOKUP.get(channel_id)
        if channel_name is None:
            channel_name = f"Unknown (0x{channel_id:02X})"

        try:
            ascii_text = data_bytes.decode("ascii").strip()
        except UnicodeDecodeError as e:
            logger.warning(f"  CH  0x{channel_id:02X} {channel_name}  ASCII decode failed: {e}")
            return {"error": "ASCII decode failed"}

        logger.debug(f"  CH  0x{channel_id:02X} {channel_name}  ascii='{ascii_text}'")

        to_name   = ADDRESS_LOOKUP.get(to_address)
        from_name = ADDRESS_LOOKUP.get(from_address)
        cmd_name  = COMMAND_LOOKUP.get(command)

        return {
            "to_address":   to_name   if to_name   is not None else f"Unknown (0x{to_address:02X})",
            "from_address": from_name if from_name is not None else f"Unknown (0x{from_address:02X})",
            "command":      cmd_name  if cmd_name  is not None else f"Unknown (0x{command:02X})",
            "values": {
                channel_name: {
                    "channel_id":   f"0x{channel_id:02X}",
                    "value":        None,
                    "display_text": ascii_text,
                    "layout":       None,
                }
            }
        }

    except Exception as e:
        logger.error(f"Error decoding ASCII frame: {e}")
        return {"error": str(e)}


def decode_format_and_data(channel_id, format_byte, data_bytes):
    try:
        divisor        = _DIVISOR_MAP[(format_byte >> 6) & 0b11]
        decimal_places = _DECIMAL_PLACES_MAP[divisor]
        format_bits    = format_byte & 0b1111

        if len(data_bytes) == 0:
            return None

        layout = None

        if format_bits == 0x01:
            if len(data_bytes) != 2:
                return None
            raw = int.from_bytes(data_bytes, byteorder="big", signed=True)
            if channel_id == 0xB5:
                value        = float(raw)
                display_text = AUTOPILOT_MODES.get(raw, f"Unknown ({raw})")
            else:
                value        = raw / divisor
                display_text = f"{value:.{decimal_places}f}"

        elif format_bits == 0x02:
            if len(data_bytes) != 2:
                return None
            unsigned = ((data_bytes[0] & 0b11) << 8) | data_bytes[1]
            value        = unsigned / divisor
            display_text = f"{value:.{decimal_places}f}"

        elif format_bits == 0x03:
            if len(data_bytes) != 2:
                return None
            layout   = SEGMENT_A.get(data_bytes[0], "?")
            unsigned = data_bytes[1]
            value    = _sign_from_layout(layout) * unsigned / divisor
            display_text = _display_from_layout(layout, f"{value:.{decimal_places}f}")

        elif format_bits == 0x04:
            if len(data_bytes) != 4:
                return None
            # data_bytes[0] is a status/flag byte, not part of the value
            unsigned     = int.from_bytes(data_bytes[1:], byteorder="big", signed=False)
            value        = unsigned / divisor
            display_text = f"{value:.{decimal_places}f}"

        elif format_bits == 0x05:
            if len(data_bytes) != 4:
                return None
            # data_bytes[0] is a status/flag byte; bytes 1-3 are h, m, s
            h, m, s  = data_bytes[1], data_bytes[2], data_bytes[3]
            value    = float(h * 3600 + m * 60 + s)
            display_text = str(datetime.timedelta(hours=h, minutes=m, seconds=s))

        elif format_bits == 0x06:
            if len(data_bytes) != 4:
                return None
            value        = None
            display_text = "".join(SEGMENT_B.get(b, "?") for b in data_bytes)

        elif format_bits == 0x07:
            if len(data_bytes) != 4:
                return None
            # data_bytes[0] is a status/flag byte; byte 1 is the segment/layout code
            layout   = SEGMENT_A.get(data_bytes[1], "?")
            msb      = data_bytes[2] & 0b01111111
            unsigned = (msb << 8) | data_bytes[3]
            value    = _sign_from_layout(layout) * unsigned / divisor
            display_text = _display_from_layout(layout, f"{value:.{decimal_places}f}")

        elif format_bits == 0x08:
            if len(data_bytes) != 2:
                return None
            segment_code = (data_bytes[0] >> 1) & 0b01111111
            layout       = SEGMENT_A.get(segment_code, "?")
            unsigned     = ((data_bytes[0] & 0b1) << 8) | data_bytes[1]
            value        = unsigned / divisor
            display_text = _display_from_layout(layout, f"{value:.{decimal_places}f}")

        elif format_bits == 0x0A:
            if len(data_bytes) != 4:
                return None
            first  = int.from_bytes(data_bytes[:2], byteorder="big", signed=True) / divisor
            second = int.from_bytes(data_bytes[2:], byteorder="big", signed=True) / divisor
            value        = first
            display_text = f"{first:.{decimal_places}f} / {second:.{decimal_places}f}"

        else:
            # format 0x09 has not been observed in captured data
            logger.debug(f"       unsupported format 0x{format_bits:02X}")
            return None

        return {
            "channel_id":   f"0x{channel_id:02X}",
            "value":        value,
            "display_text": display_text,
            "layout":       layout,
        }

    except Exception as e:
        logger.error(f"Error decoding channel 0x{channel_id:02X}: {e}")
        return None
