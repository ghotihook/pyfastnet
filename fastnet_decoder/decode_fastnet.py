import datetime
from .utils import calculate_checksum
from .mappings import ADDRESS_LOOKUP, COMMAND_LOOKUP, CHANNEL_LOOKUP, FORMAT_SIZE_MAP
from .mappings import SEGMENT_A, SEGMENT_B, AUTOPILOT_MODES
from .logger import logger


_DIVISOR_MAP = {0b00: 1, 0b01: 10, 0b10: 100, 0b11: 1000}
_DP_MAP = {1: 0, 10: 1, 100: 2, 1000: 3}


def _sign_from_layout(layout: str) -> int:
    return -1 if layout in ("-[data]", "=[data]") else 1


def _display_from_layout(layout: str, formatted: str) -> str:
    if layout == "°M":        return f"{formatted}°M"
    if layout == "H[data]":   return f"H{formatted}"
    if layout == "[data]H":   return f"{formatted}H"
    if layout in ("[data]=", "[data]-"):
        return f"{formatted}{layout[-1]}"
    return formatted


def decode_frame(frame: bytes) -> dict:
    try:
        logger.debug(f"Starting frame decoding. Frame length: {len(frame)}, Frame contents: {frame.hex()}")

        to_address      = frame[0]
        from_address    = frame[1]
        body_size       = frame[2]
        command         = frame[3]
        header_checksum = frame[4]
        body            = frame[5:-1]
        body_checksum   = frame[-1]

        logger.debug(
            f"Parsed header: to_address=0x{to_address:02X}, from_address=0x{from_address:02X}, "
            f"body_size={body_size}, command=0x{command:02X}, header_checksum=0x{header_checksum:02X}"
        )

        if calculate_checksum(frame[:4]) != header_checksum:
            logger.debug(f"Header checksum mismatch. Frame dropped: {frame.hex()}")
            return {"error": "Header checksum mismatch"}

        if calculate_checksum(body) != body_checksum:
            logger.debug(f"Body checksum mismatch. Frame dropped: {frame.hex()}")
            return {"error": "Body checksum mismatch"}

        if len(body) < 2 or len(body) != body_size:
            logger.debug(f"Invalid body size: Expected {body_size}, Actual {len(body)}. Frame: {frame.hex()}")
            return {"error": "Invalid body size"}

        logger.debug("Header and body checksums are valid.")

        decoded_data = {
            "to_address":  ADDRESS_LOOKUP.get(to_address,   f"Unknown (0x{to_address:02X})"),
            "from_address": ADDRESS_LOOKUP.get(from_address, f"Unknown (0x{from_address:02X})"),
            "command":     COMMAND_LOOKUP.get(command,       f"Unknown (0x{command:02X})"),
            "values":      {}
        }

        index = 0
        while index < len(body):
            if index + 1 >= len(body):
                logger.debug(
                    f"Insufficient bytes to decode channel ID and format byte at index {index}. "
                    f"Remaining length: {len(body) - index}"
                )
                return {"error": "Insufficient bytes for channel header"}

            channel_id  = body[index]
            format_byte = body[index + 1]
            index      += 2

            data_length = FORMAT_SIZE_MAP.get(format_byte & 0x0F, 0)
            if index + data_length > len(body):
                logger.debug(
                    f"Incomplete data for channel 0x{channel_id:02X}. "
                    f"Expected length: {data_length}, Available: {len(body) - index}"
                )
                return {"error": f"Incomplete data for channel 0x{channel_id:02X}"}

            data_bytes = body[index:index + data_length]
            index     += data_length

            decoded_value = decode_format_and_data(channel_id, format_byte, data_bytes)
            channel_name  = CHANNEL_LOOKUP.get(channel_id, f"Unknown (0x{channel_id:02X})")

            decoded_data["values"][channel_name] = decoded_value
            logger.debug(f"Decoded value for channel {channel_name}: {decoded_value}")

        return decoded_data

    except Exception as e:
        logger.error(f"Unexpected error during frame decoding: {e}. Frame contents: {frame.hex()}")
        return {"error": "Decoding failure"}


def decode_ascii_frame(frame: bytes) -> dict:
    try:
        to_address      = frame[0]
        from_address    = frame[1]
        command         = frame[3]
        header_checksum = frame[4]
        body            = frame[5:-1]

        channel_id   = body[0]
        data_bytes   = body[2:]
        channel_name = CHANNEL_LOOKUP.get(channel_id, f"Unknown (0x{channel_id:02X})")

        try:
            ascii_text = data_bytes.decode("ascii").strip()
        except UnicodeDecodeError as e:
            logger.warning(f"Failed to decode ASCII text: {e}")
            return {"error": "ASCII decode failed"}

        return {
            "to_address":  ADDRESS_LOOKUP.get(to_address,   f"Unknown (0x{to_address:02X})"),
            "from_address": ADDRESS_LOOKUP.get(from_address, f"Unknown (0x{from_address:02X})"),
            "command":     COMMAND_LOOKUP.get(command,       f"Unknown (0x{command:02X})"),
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
        logger.debug(f"Decoding channel ID: 0x{channel_id:02X}, format byte: 0x{format_byte:02X}, data: {data_bytes.hex()}")

        divisor     = _DIVISOR_MAP[(format_byte >> 6) & 0b11]
        dp          = _DP_MAP[divisor]
        format_bits = format_byte & 0b1111

        if len(data_bytes) == 0:
            logger.debug("decode_format_and_data: Empty data bytes; cannot decode.")
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
                display_text = f"{value:.{dp}f}"

        elif format_bits == 0x02:
            if len(data_bytes) != 2:
                return None
            unsigned = ((data_bytes[0] & 0b11) << 8) | data_bytes[1]
            value        = unsigned / divisor
            display_text = f"{value:.{dp}f}"

        elif format_bits == 0x03:
            if len(data_bytes) != 2:
                return None
            layout   = SEGMENT_A.get(data_bytes[0], "?")
            unsigned = data_bytes[1]
            value    = _sign_from_layout(layout) * unsigned / divisor
            display_text = _display_from_layout(layout, f"{value:.{dp}f}")

        elif format_bits == 0x04:
            if len(data_bytes) != 4:
                return None
            unsigned     = int.from_bytes(data_bytes[1:], byteorder="big", signed=False)
            value        = unsigned / divisor
            display_text = f"{value:.{dp}f}"

        elif format_bits == 0x05:
            if len(data_bytes) != 4:
                return None
            h, m, s  = data_bytes[1], data_bytes[2], data_bytes[3]
            value    = float(h * 3600 + m * 60 + s)
            display_text = str(datetime.timedelta(hours=h, minutes=m, seconds=s))

        elif format_bits == 0x06:
            if len(data_bytes) != 4:
                return None
            value        = None
            display_text = "".join(SEGMENT_B.get(b, "?") for b in data_bytes)
            logger.debug(f"Decoded 7-segment text: {display_text}")

        elif format_bits == 0x07:
            if len(data_bytes) != 4:
                return None
            layout   = SEGMENT_A.get(data_bytes[1], "?")
            msb      = data_bytes[2] & 0b01111111
            unsigned = (msb << 8) | data_bytes[3]
            value    = _sign_from_layout(layout) * unsigned / divisor
            display_text = _display_from_layout(layout, f"{value:.{dp}f}")

        elif format_bits == 0x08:
            if len(data_bytes) != 2:
                return None
            segment_code = (data_bytes[0] >> 1) & 0b01111111
            layout       = SEGMENT_A.get(segment_code, "?")
            unsigned     = ((data_bytes[0] & 0b1) << 8) | data_bytes[1]
            value        = unsigned / divisor
            display_text = _display_from_layout(layout, f"{value:.{dp}f}")

        elif format_bits == 0x0A:
            if len(data_bytes) != 4:
                return None
            first  = int.from_bytes(data_bytes[:2], byteorder="big", signed=True) / divisor
            second = int.from_bytes(data_bytes[2:], byteorder="big", signed=True) / divisor
            value        = first
            display_text = f"{first:.{dp}f} / {second:.{dp}f}"

        else:
            logger.debug(f"Unsupported format: 0x{format_bits:02X}.")
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
