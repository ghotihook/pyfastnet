"""v3 projection: map a fully-decoded FastNet frame to ``{signalk_path: SI_value}``.

This is the v3 output layer. The decoder stays complete (value/display_text/layout);
``project()`` selects a canonical, SI-typed view over it — one entry per physical
quantity, keyed by Signal K path. See ``docs/v3_signalk_mapping.md`` for the full spec,
unit conventions, and the vendor ``bandg.*`` namespace.

Value types (mirror Signal K): ``float`` (SI) / ``str`` (enum) / ``dict`` (position) /
``None`` (unavailable). ``display_text`` and ``layout`` are never emitted here — they
stay inside the decoder.
"""

from math import pi

# ── SI conversions ────────────────────────────────────────────────────────────
KN_MS = 0.514444          # knots → m/s
NM_M = 1852.0             # nautical miles → m
FT_M = 0.3048             # feet → m
FATHOM_M = 1.8288         # fathom → m
DEG_RAD = pi / 180.0      # degrees → radians
HPA_PA = 100.0            # hPa/mbar → Pa


def _kn(v):  return v * KN_MS
def _nm(v):  return v * NM_M
def _deg(v): return v * DEG_RAD
def _c2k(v): return v + 273.15
def _hpa(v): return v * HPA_PA
def _pct(v): return v / 100.0
def _id(v):  return v          # already SI (m, m/s, s, V)


# ── Standard Signal K paths: channel_id → (path, transform) ───────────────────
# Layout-routed bearings (0x49/0x6D/0x84) are handled separately in _ROUTED below.
STANDARD = {
    # navigation.*
    0x41: ("navigation.speedThroughWater", _kn),
    0xEB: ("navigation.speedOverGround", _kn),
    0xE9: ("navigation.courseOverGroundTrue", _deg),
    0xEA: ("navigation.courseOverGroundMagnetic", _deg),
    0x44: ("navigation.rateOfTurn", _deg),
    0x34: ("navigation.attitude.roll", _deg),
    0x9B: ("navigation.attitude.pitch", _deg),
    0x82: ("navigation.leewayAngle", _deg),
    0xCD: ("navigation.log", _nm),
    0xCF: ("navigation.trip.log", _nm),
    0xE7: ("navigation.courseRhumbline.nextPoint.distance", _nm),
    0xE8: ("navigation.courseGreatCircle.nextPoint.distance", _nm),
    0xFA: ("navigation.courseGreatCircle.nextPoint.distance", _nm),   # TBC #1: vs 0xE8
    0xE3: ("navigation.courseRhumbline.nextPoint.bearingTrue", _deg),
    0xE4: ("navigation.courseRhumbline.nextPoint.bearingMagnetic", _deg),
    0xE5: ("navigation.courseGreatCircle.nextPoint.bearingTrue", _deg),
    0xE6: ("navigation.courseGreatCircle.nextPoint.bearingMagnetic", _deg),
    0xE0: ("navigation.courseGreatCircle.bearingTrackTrue", _deg),
    0xE1: ("navigation.courseGreatCircle.bearingTrackMagnetic", _deg),
    0xEC: ("navigation.courseGreatCircle.nextPoint.velocityMadeGood", _kn),
    0xED: ("navigation.courseGreatCircle.nextPoint.timeToGo", _id),
    0xEE: ("navigation.courseGreatCircle.crossTrackError", _nm),
    0xE2: ("navigation.racing.layline.distance", _nm),   # TBC #5: encoding unconfirmed
    0xFB: ("navigation.racing.layline.time", _id),        # TBC #5
    # environment.*
    0x1F: ("environment.water.temperature", _c2k),
    0x1D: ("environment.outside.temperature", _c2k),
    0x87: ("environment.outside.pressure", _hpa),
    0x4F: ("environment.wind.speedApparent", _id),       # native m/s
    0x51: ("environment.wind.angleApparent", _deg),
    0x56: ("environment.wind.speedTrue", _id),           # native m/s
    0x59: ("environment.wind.angleTrueWater", _deg),
    0x83: ("environment.current.drift", _kn),
    # steering.*
    0x0B: ("steering.rudderAngle", _deg),
    0xA6: ("steering.autopilot.target.headingMagnetic", _deg),
    # performance.*
    0x7F: ("performance.velocityMadeGood", _kn),
    0x7D: ("performance.targetSpeed", _kn),
    0x53: ("performance.targetAngle", _deg),
    0x7C: ("performance.polarSpeedRatio", _pct),
    0x9A: ("performance.tackMagnetic", _deg),
    # electrical.*  (instance id injected below)
    0x8D: ("electrical.batteries.{id}.voltage", _id),
}

# Depth fallback chain (metres → feet → fathoms), all → belowTransducer.
DEPTH = [(0xC1, _id), (0xC2, lambda v: v * FT_M), (0xC3, lambda v: v * FATHOM_M)]
DEPTH_PATH = "environment.depth.belowTransducer"

# Layout-routed bearings: channel_id → (magnetic_path, true_path), transform.
_ROUTED = {
    0x49: ("navigation.headingMagnetic", "navigation.headingTrue", _deg),
    0x6D: ("environment.wind.directionMagnetic", "environment.wind.directionTrue", _deg),
    0x84: ("environment.current.setMagnetic", "environment.current.setTrue", _deg),
}

# ── Vendor bandg.* : channel_id → (path, transform) ───────────────────────────
VENDOR = {
    0x57: ("bandg.wind.measuredSpeed", _kn),
    0x5A: ("bandg.wind.measuredAngle", _deg),
    0x85: ("bandg.wind.upwash", _deg),
    # Raw (pre-calibration) sensor values — identity, kept as the decoder produces
    # them so they can feed B&G proprietary raw PGNs (opaque counts, no SI unit).
    0x4E: ("bandg.wind.rawSpeedApparent", _id),
    0x52: ("bandg.wind.rawAngleApparent", _id),
    0x42: ("bandg.navigation.rawSpeedThroughWater", _id),
    0x4A: ("bandg.navigation.rawHeading", _id),
    0x9C: ("bandg.mast.rotation", _deg),
    0x9D: ("bandg.mast.windAngle", _deg),
    0x27: ("bandg.performance.headLiftTrend", _id),      # TBC #6: type
    0x32: ("bandg.performance.tacking", _pct),
    0x33: ("bandg.performance.reaching", _pct),
    0xF9: ("bandg.performance.courseToSail", _deg),
    0x35: ("bandg.performance.optimumWindAngle", _deg),
    0x6F: ("bandg.performance.nextLeg.angleApparent", _deg),
    0x71: ("bandg.performance.nextLeg.speedApparent", _kn),
    0x70: ("bandg.performance.nextLeg.targetSpeed", _kn),
    0x64: ("bandg.navigation.speedThroughWaterAverage", _kn),
    0x69: ("bandg.navigation.courseThroughWater", _deg),
    0x81: ("bandg.navigation.deadReckoning.distance", _nm),
    0xD3: ("bandg.navigation.deadReckoning.course", _deg),
    0x3C: ("bandg.motion.rate", _id),                    # TBC #6: unit
    0x9E: ("bandg.motion.pitchRate", _deg),
    0x29: ("bandg.steering.offCourse", _deg),
    0xAF: ("bandg.steering.autopilot.offCourse", _deg),
    0x46: ("bandg.steering.autopilot.fixedSpeed", _kn),
    0x86: ("bandg.environment.pressureTrend", _hpa),
    0xDC: ("bandg.time.local", _id),
    0x75: ("bandg.time.timer", _id),
}

# Layout byte → reference. Magnetic confirmed in data; °T value not yet known (TBC #7).
_MAGNETIC_LAYOUT = "°M"    # "°M" (0x66)
_TRUE_LAYOUT = "°T"        # "°T" — placeholder token; add its SEGMENT_A byte when captured

# Autopilot state (0xB5) → SK steering.autopilot.state enum.
_AP_MODE_BY_LOW = {0x01: "auto", 0x04: "wind", 0x13: "route", 0x02: "directControl"}

# Channels intentionally dropped (protocol/control/diagnostic).
DROP = {0x00, 0x50, 0x68, 0x6A, 0x36, 0x37, 0xC9}


# ── Per-path SI units (for display / introspection) ───────────────────────────
_UNIT_BY_TF = {_kn: "m/s", _nm: "m", _deg: "rad", _c2k: "K", _hpa: "Pa", _pct: "ratio"}
# _id is identity, so its unit depends on the quantity — resolve per path.
_ID_UNITS = {
    "environment.wind.speedApparent": "m/s",
    "environment.wind.speedTrue": "m/s",
    "environment.depth.belowTransducer": "m",
    "navigation.courseGreatCircle.nextPoint.timeToGo": "s",
    "navigation.racing.layline.time": "s",
    "bandg.time.local": "s",
    "bandg.time.timer": "s",
    "bandg.motion.rate": "?",
    "bandg.performance.headLiftTrend": "",
}


def _unit_for_tf(path, tf):
    return _ID_UNITS.get(path, "") if tf is _id else _UNIT_BY_TF.get(tf, "")


PATH_UNITS = {}
for _cid, (_p, _tf) in STANDARD.items():
    if "{id}" not in _p:               # battery path resolved at runtime — see unit_for()
        PATH_UNITS[_p] = _unit_for_tf(_p, _tf)
PATH_UNITS[DEPTH_PATH] = "m"
for _cid, (_m, _t, _tf) in _ROUTED.items():
    PATH_UNITS[_m] = PATH_UNITS[_t] = "rad"
for _cid, (_p, _tf) in VENDOR.items():
    PATH_UNITS[_p] = _unit_for_tf(_p, _tf)
PATH_UNITS["navigation.position"] = "deg"
PATH_UNITS["steering.autopilot.state"] = "enum"


def unit_for(path):
    """SI unit string for a Signal K path emitted by project(), or "" if unknown."""
    u = PATH_UNITS.get(path)
    if u is not None:
        return u
    if path.startswith("electrical.batteries.") and path.endswith(".voltage"):
        return "V"
    return ""


def _cid(entry):
    """Parse a decoded value's channel_id ('0xC1') to int, or None."""
    raw = entry.get("channel_id")
    if not raw:
        return None
    try:
        return int(raw, 16)
    except (ValueError, TypeError):
        return None


def _ap_state(value):
    """0xB5 composite → SK autopilot state string."""
    if value is None:
        return None
    raw = int(value)
    high, low = (raw >> 8) & 0xFF, raw & 0xFF
    if high == 0x50:
        return "standby"
    if high in (0x51, 0x59):
        return _AP_MODE_BY_LOW.get(low)
    return None


def parse_position(ascii_text):
    """Parse a FastNet LatLon fix ('3352.450S15113.920E') → {latitude, longitude} deg."""
    if not ascii_text:
        return None
    lat_i = max(ascii_text.find('N'), ascii_text.find('S'))
    lon_i = max(ascii_text.find('E'), ascii_text.find('W'))
    if lat_i == -1 or lon_i == -1:
        return None
    try:
        lat_p, lat_d = ascii_text[:lat_i], ascii_text[lat_i]
        lon_p, lon_d = ascii_text[lat_i + 1:lon_i], ascii_text[lon_i]
        lat = int(lat_p[:2]) + float(lat_p[2:]) / 60.0
        lon = int(lon_p[:3]) + float(lon_p[3:]) / 60.0
    except (ValueError, IndexError):
        return None
    if lat_d == 'S':
        lat = -lat
    if lon_d == 'W':
        lon = -lon
    return {"latitude": lat, "longitude": lon}


def project(decoded_frame, battery_id="house"):
    """Project a decoded frame (from decode_frame/ascii/light) → {signalk_path: value}.

    Returns SI floats / enum strings / position dicts / None. Unmapped or dropped
    channels are omitted. Layout-routed bearings pick Magnetic vs True from the
    decoded layout byte.
    """
    command = decoded_frame.get("command")
    values = decoded_frame.get("values", {})
    out = {}

    # LatLon: parse the ASCII fix (display_text) into a position object.
    if command == "LatLon":
        for entry in values.values():
            pos = parse_position(entry.get("display_text"))
            if pos is not None:
                out["navigation.position"] = pos
        return out

    depth_seen = {}
    for entry in values.values():
        cid = _cid(entry)
        value = entry.get("value")
        if cid is None or cid in DROP:
            continue

        # Depth fallback chain, resolved after the loop.
        if cid in (0xC1, 0xC2, 0xC3):
            depth_seen[cid] = value
            continue

        # Autopilot state enum.
        if cid == 0xB5:
            state = _ap_state(value)
            if state is not None:
                out["steering.autopilot.state"] = state
            continue

        # Layout-routed Magnetic/True bearings.
        if cid in _ROUTED:
            mag_path, true_path, tf = _ROUTED[cid]
            layout = entry.get("layout")
            path = true_path if layout == _TRUE_LAYOUT else mag_path
            out[path] = tf(value) if value is not None else None
            continue

        # Standard paths.
        if cid in STANDARD:
            path, tf = STANDARD[cid]
            path = path.format(id=battery_id)
            out[path] = tf(value) if value is not None else None
            continue

        # Vendor bandg.* paths.
        if cid in VENDOR:
            path, tf = VENDOR[cid]
            out[path] = tf(value) if value is not None else None

    # Resolve depth by priority: metres → feet → fathoms.
    for cid, tf in DEPTH:
        if cid in depth_seen and depth_seen[cid] is not None:
            out[DEPTH_PATH] = tf(depth_seen[cid])
            break

    return out
