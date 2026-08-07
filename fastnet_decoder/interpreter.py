"""Generic, schema-driven FastNet decode engine.

Reads fastnet_decoder/data/fastnet.json once at import time and decodes any
frame from it — no channel names or per-format branches are hardcoded here.
Adding a channel that fits an existing formatTemplates op requires no change
to this file, only a data.json edit.

Stage 2 (this module): built and validated for parity against the real,
hand-written decoder (mappings.py/decode_fastnet.py/signalk_map.py) via
tests/test_interpreter_parity.py, but not yet wired into __init__.py.
"""
import datetime
import json
import logging
from pathlib import Path

from .logger import logger

_DATA_PATH = Path(__file__).resolve().parent / "data" / "fastnet.json"
SCHEMA = json.loads(_DATA_PATH.read_text(encoding="utf-8"))

_FORMAT_TEMPLATES = SCHEMA["formatTemplates"]
_FORMAT_SIZE_MAP = {int(k, 16): v for k, v in SCHEMA["formatSizeMap"].items()}
_DIVISOR_MAP = {int(k[2:], 2): v for k, v in SCHEMA["scaling"]["divisorByTopBits"].items()}
_DECIMAL_PLACES_MAP = {int(k): v for k, v in SCHEMA["scaling"]["decimalPlacesByDivisor"].items()}

_LK = SCHEMA["lookups"]
ADDRESS_LOOKUP = {int(k, 16): v for k, v in _LK["addresses"].items()}
COMMAND_LOOKUP = {int(k, 16): v for k, v in _LK["commands"].items()}
IGNORED_COMMANDS = set(_LK["ignoredCommands"])
CHANNEL_LOOKUP = {int(k, 16): v for k, v in _LK["channelNames"].items()}
BACKLIGHT_LEVELS = {int(k, 16): v for k, v in _LK["backlightLevels"].items()}
SEGMENT_A = {int(k, 16): v for k, v in _LK["segmentA"].items()}
SEGMENT_B = {int(k, 16): v for k, v in _LK["segmentB"].items()}
_LAYOUT_SIGN = _LK["layoutSign"]
_LAYOUT_DISPLAY = _LK["layoutDisplay"]
_AUTOPILOT_STATE = _LK["autopilotState"]

_CHANNELS = SCHEMA["channels"]
_MESSAGES = SCHEMA["messages"]


def _mask(hex_str: str) -> int:
    return int(hex_str, 16)


def extract_bits(data_bytes: bytes, pieces) -> int:
    value = 0
    for p in pieces:
        value |= (data_bytes[p["byte"]] & _mask(p["mask"])) << p.get("shiftLeft", 0)
    return value


def _layout_for(byte: int) -> str:
    return SEGMENT_A.get(byte, "TBC")


def _sign_for(layout) -> int:
    return _LAYOUT_SIGN.get(layout, 1)


def _render_display(layout, formatted: str) -> str:
    entry = _LAYOUT_DISPLAY.get(layout) if layout is not None else None
    if entry is None:
        return formatted
    text = formatted
    if entry.get("stripSign"):
        text = text.lstrip("-")
    if "prefix" in entry:
        text = entry["prefix"] + text
    if "suffix" in entry:
        text = text + entry["suffix"]
    return text


# ── channel override handlers (named escape hatch, keyed by name in the schema) ─

def _override_autopilot_mode(data_bytes: bytes):
    raw = int.from_bytes(data_bytes, byteorder="big", signed=True)
    value = float(raw)
    high, low = (raw >> 8) & 0xFF, raw & 0xFF
    if high == 0x50:
        display_text = "Standby"
    elif high in (0x51, 0x59):
        entry = _AUTOPILOT_STATE.get(f"0x{low:02X}")
        display_text = entry["displayText"] if entry else f"Unknown ({raw})"
    else:
        display_text = f"Unknown ({raw})"
    return value, display_text, None


_OVERRIDES = {"autopilotMode": _override_autopilot_mode}


def decode_channel_value(channel_id: int, format_byte: int, data_bytes: bytes):
    try:
        if len(data_bytes) == 0:
            return None

        format_bits = format_byte & 0x0F
        divisor = _DIVISOR_MAP[(format_byte >> 6) & 0b11]
        decimal_places = _DECIMAL_PLACES_MAP[divisor]

        channel = _CHANNELS.get(f"0x{channel_id:02X}", {})
        override_name = channel.get("overrides", {}).get(f"0x{format_bits:02X}")
        if override_name:
            value, display_text, layout = _OVERRIDES[override_name](data_bytes)
            return {"channel_id": f"0x{channel_id:02X}", "value": value,
                    "display_text": display_text, "layout": layout}

        template = _FORMAT_TEMPLATES.get(f"0x{format_bits:02X}")
        if template is None or template["op"] == "unsupported":
            logger.debug(f"       unsupported format 0x{format_bits:02X}")
            return None

        op = template["op"]
        layout = None

        if op == "scaledInt":
            lo, hi = template["valueBytes"]
            raw = int.from_bytes(data_bytes[lo:hi], byteorder="big", signed=template["signed"])
            value = raw / divisor
            display_text = f"{value:.{decimal_places}f}"

        elif op == "scaledBitfield":
            unsigned = extract_bits(data_bytes, template["pieces"])
            value = unsigned / divisor
            display_text = f"{value:.{decimal_places}f}"

        elif op == "signedLayoutValue":
            layout_byte = data_bytes[template["layoutByte"]]
            layout = _layout_for(layout_byte)
            if "pieces" in template:
                unsigned = extract_bits(data_bytes, template["pieces"])
            else:
                lo, hi = template["valueBytes"]
                unsigned = int.from_bytes(data_bytes[lo:hi], byteorder="big", signed=False)
            value = _sign_for(layout) * unsigned / divisor
            display_text = _render_display(layout, f"{value:.{decimal_places}f}")

        elif op == "layoutValue":
            lb = template["layoutBits"]
            layout_code = (data_bytes[lb["byte"]] & _mask(lb["mask"])) >> lb["shiftRight"]
            layout = _layout_for(layout_code)
            unsigned = extract_bits(data_bytes, template["pieces"])
            value = unsigned / divisor
            display_text = _render_display(layout, f"{value:.{decimal_places}f}")

        elif op == "durationHMS":
            h, m, s = data_bytes[template["hByte"]], data_bytes[template["mByte"]], data_bytes[template["sByte"]]
            value = float(h * 3600 + m * 60 + s)
            display_text = str(datetime.timedelta(hours=h, minutes=m, seconds=s))

        elif op == "segmentDisplay":
            value = None
            display_text = "".join(SEGMENT_B.get(b, "TBC") for b in data_bytes)

        elif op == "pairedScaledInt":
            a0, a1 = template["firstBytes"]
            b0, b1 = template["secondBytes"]
            first = int.from_bytes(data_bytes[a0:a1], byteorder="big", signed=template["signed"]) / divisor
            second = int.from_bytes(data_bytes[b0:b1], byteorder="big", signed=template["signed"]) / divisor
            value = first
            display_text = f"{first:.{decimal_places}f} / {second:.{decimal_places}f}"

        else:
            logger.debug(f"       unhandled op {op!r} for format 0x{format_bits:02X}")
            return None

        return {"channel_id": f"0x{channel_id:02X}", "value": value,
                "display_text": display_text, "layout": layout}

    except Exception as e:
        logger.error(f"Error decoding channel 0x{channel_id:02X}: {e}")
        return None


# ── frame-level decoders (envelope walking - same shape as decode_fastnet.py) ──

def decode_frame(frame: bytes) -> dict:
    try:
        to_address = frame[0]
        from_address = frame[1]
        body_size = frame[2]
        command = frame[3]
        body = frame[5:-1]

        if len(body) < 2 or len(body) != body_size:
            logger.debug(f"FRAME discard  body-size  expected={body_size}  actual={len(body)}")
            return {"error": "Invalid body size"}

        decoded_data = {
            "to_address": ADDRESS_LOOKUP.get(to_address, f"Unknown (0x{to_address:02X})"),
            "from_address": ADDRESS_LOOKUP.get(from_address, f"Unknown (0x{from_address:02X})"),
            "command": COMMAND_LOOKUP.get(command, f"Unknown (0x{command:02X})"),
            "values": {},
        }

        index = 0
        while index < len(body):
            if index + 1 >= len(body):
                logger.debug(f"  CH  incomplete header at index={index}")
                return {"error": "Insufficient bytes for channel header"}

            channel_id = body[index]
            format_byte = body[index + 1]
            channel_name = CHANNEL_LOOKUP.get(channel_id, f"Unknown (0x{channel_id:02X})")
            index += 2

            data_length = _FORMAT_SIZE_MAP.get(format_byte & 0x0F, 0)
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

        return decoded_data

    except Exception as e:
        logger.error(f"Unexpected error decoding frame: {e}  [{frame.hex()}]")
        return {"error": "Decoding failure"}


def probe_frame(frame: bytes) -> None:
    """Speculative RE-only unpack of non-Broadcast frames. See decode_fastnet.py's
    original docstring - never queued, DEBUG-only, best-effort."""
    if not logger.isEnabledFor(logging.DEBUG):
        return
    try:
        to_address = frame[0]
        from_address = frame[1]
        command = frame[3]
        body = frame[5:-1]

        to_name = ADDRESS_LOOKUP.get(to_address, f"Unknown (0x{to_address:02X})")
        from_name = ADDRESS_LOOKUP.get(from_address, f"Unknown (0x{from_address:02X})")
        cmd_name = COMMAND_LOOKUP.get(command, f"Unknown (0x{command:02X})")
        logger.debug(f"  PROBE cmd={cmd_name}  {to_name}←{from_name}  body=[{body.hex()}]")

        index = 0
        while index < len(body):
            if index + 1 >= len(body):
                logger.debug(f"    PROBE trailing byte  [{body[index:].hex()}]")
                break
            channel_id = body[index]
            format_byte = body[index + 1]
            index += 2
            data_length = _FORMAT_SIZE_MAP.get(format_byte & 0x0F, 0)
            if data_length == 0 or index + data_length > len(body):
                break
            data_bytes = body[index:index + data_length]
            index += data_length
            decode_channel_value(channel_id, format_byte, data_bytes)

    except Exception as e:
        logger.debug(f"  PROBE error: {e}  [{frame.hex()}]")


def decode_ascii_frame(frame: bytes) -> dict:
    try:
        to_address = frame[0]
        from_address = frame[1]
        command = frame[3]
        body = frame[5:-1]

        channel_id = body[0]
        data_bytes = body[2:]
        cmd_name = COMMAND_LOOKUP.get(command)
        channel_name = cmd_name if cmd_name is not None else f"Unknown (0x{command:02X})"

        try:
            ascii_text = data_bytes.decode("ascii").strip()
        except UnicodeDecodeError as e:
            logger.warning(f"  CH  0x{channel_id:02X} {channel_name}  ASCII decode failed: {e}")
            return {"error": "ASCII decode failed"}

        return {
            "to_address": ADDRESS_LOOKUP.get(to_address, f"Unknown (0x{to_address:02X})"),
            "from_address": ADDRESS_LOOKUP.get(from_address, f"Unknown (0x{from_address:02X})"),
            "command": cmd_name if cmd_name is not None else f"Unknown (0x{command:02X})",
            "values": {
                channel_name: {
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
    try:
        to_address = frame[0]
        from_address = frame[1]
        command = frame[3]
        body = frame[5:-1]

        if len(body) < 1:
            return {"error": "Invalid body size"}

        level = body[0]
        cmd_name = COMMAND_LOOKUP.get(command)
        display_text = BACKLIGHT_LEVELS.get(level, f"Unknown ({level})")

        return {
            "to_address": ADDRESS_LOOKUP.get(to_address, f"Unknown (0x{to_address:02X})"),
            "from_address": ADDRESS_LOOKUP.get(from_address, f"Unknown (0x{from_address:02X})"),
            "command": cmd_name if cmd_name is not None else f"Unknown (0x{command:02X})",
            "values": {
                "Backlight": {
                    "channel_id": None,
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

def _cid(entry) -> int:
    raw = entry.get("channel_id")
    if not raw:
        return None
    try:
        return int(raw, 16)
    except (ValueError, TypeError):
        return None


def _apply_transform(value, transform):
    t = transform["type"]
    if t == "identity":
        return value
    if t == "scale":
        return value * transform["factor"]
    if t == "affine":
        return value * transform.get("scale", 1) + transform.get("offset", 0)
    raise ValueError(f"unhandled transform type {t!r}")


def _ap_state(value):
    if value is None:
        return None
    raw = int(value)
    high, low = (raw >> 8) & 0xFF, raw & 0xFF
    if high == 0x50:
        return "standby"
    if high in (0x51, 0x59):
        entry = _AUTOPILOT_STATE.get(f"0x{low:02X}")
        return entry["signalk"] if entry else None
    return None


def parse_position(ascii_text):
    if not ascii_text:
        return None
    lat_i = max(ascii_text.find("N"), ascii_text.find("S"))
    lon_i = max(ascii_text.find("E"), ascii_text.find("W"))
    if lat_i == -1 or lon_i == -1:
        return None
    try:
        lat_p, lat_d = ascii_text[:lat_i], ascii_text[lat_i]
        lon_p, lon_d = ascii_text[lat_i + 1:lon_i], ascii_text[lon_i]
        lat = int(lat_p[:2]) + float(lat_p[2:]) / 60.0
        lon = int(lon_p[:3]) + float(lon_p[3:]) / 60.0
    except (ValueError, IndexError):
        return None
    if lat_d == "S":
        lat = -lat
    if lon_d == "W":
        lon = -lon
    return {"latitude": lat, "longitude": lon}


def unit_for(path: str) -> str:
    for cid, ch in _CHANNELS.items():
        sk = ch.get("signalk")
        if not sk:
            continue
        if sk.get("path") == path and "pathParam" not in sk:
            return sk.get("unit") or ""
        if "routes" in sk and any(r["path"] == path for r in sk["routes"].values()):
            return sk.get("unit") or ""
    if path == "navigation.position":
        return "deg"
    if path == "steering.autopilot.state":
        return "enum"
    if path.startswith("electrical.batteries.") and path.endswith(".voltage"):
        return "V"
    return ""


def project(decoded_frame: dict, battery_id: str = "house") -> dict:
    command = decoded_frame.get("command")
    values = decoded_frame.get("values", {})
    out = {}

    if command == "LatLon":
        for entry in values.values():
            pos = parse_position(entry.get("display_text"))
            if pos is not None:
                out["navigation.position"] = pos
        return out

    depth_seen = {}
    depth_path = None
    for entry in values.values():
        cid = _cid(entry)
        if cid is None:
            continue
        value = entry.get("value")

        channel = _CHANNELS.get(f"0x{cid:02X}", {})
        sk = channel.get("signalk")

        if sk is None:
            if value is not None:
                out[f"bandg.unknown.0x{cid:02X}"] = value
            continue

        if sk.get("drop") or "collapsedInto" in sk:
            continue

        if "fallbackGroup" in sk:
            depth_seen[cid] = (sk["fallbackPriority"], value, sk)
            depth_path = sk["path"]
            continue

        transform = sk["transform"]
        if transform["type"] == "overrideEnum":
            state = _ap_state(value)
            if state is not None:
                out[sk["path"]] = state
            continue

        if "routedBy" in sk:
            layout = entry.get("layout")
            route = sk["routes"]["°T"] if layout == "°T" else sk["routes"]["°M"]
            out[route["path"]] = _apply_transform(value, transform) if value is not None else None
            continue

        path = sk["path"]
        if "pathParam" in sk:
            path = path.format(id=battery_id)
        out[path] = _apply_transform(value, transform) if value is not None else None

    if depth_seen:
        for priority, value, sk in sorted(depth_seen.values(), key=lambda t: t[0]):
            if value is not None:
                out[depth_path] = _apply_transform(value, sk["transform"])
                break

    return out


# ── master reference table ──────────────────────────────────────────────────

def channel_map() -> dict:
    out = {}
    for cid, name in sorted(CHANNEL_LOOKUP.items()):
        ch = _CHANNELS.get(f"0x{cid:02X}", {})
        sk = ch.get("signalk")
        if sk is None:
            path, unit, kind = f"bandg.unknown.0x{cid:02X}", "", "unknown"
        elif sk.get("drop"):
            path, unit, kind = "—", "", "drop"
        elif "collapsedInto" in sk:
            path, unit, kind = f"→ {sk['collapsedInto']}", "", "collapsed"
        elif "fallbackGroup" in sk:
            path, unit, kind = sk["path"], sk.get("unit", ""), "standard(depth fallback)"
        elif sk["transform"]["type"] == "overrideEnum":
            path, unit, kind = sk["path"], sk.get("unit", ""), "standard"
        elif "routedBy" in sk:
            m = sk["routes"]["°M"]["path"]
            stem = m[:-len("Magnetic")] if m.endswith("Magnetic") else m
            path, unit, kind = f"{stem}{{Magnetic,True}}", sk.get("unit", ""), "routed(M/T)"
        elif sk["path"].startswith("bandg."):
            path, unit, kind = sk["path"], sk.get("unit", ""), "vendor"
        else:
            path, unit, kind = sk["path"], sk.get("unit", ""), "standard"
        out[cid] = {"name": name, "path": path, "unit": unit, "kind": kind}
    return out
