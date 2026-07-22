"""Tests for the v3 Signal K projection (fastnet_decoder/signalk_map.py)."""

import math

from fastnet_decoder import signalk_map as sk
from fastnet_decoder.decode_fastnet import decode_frame
from fastnet_decoder.frame_buffer import FrameBuffer


def _frame(cid_hex, value, name="X", layout=None, command="Broadcast", display=None):
    """Build a minimal decoded-frame dict as decode_frame would produce."""
    return {
        "command": command,
        "values": {name: {"channel_id": cid_hex, "value": value,
                          "display_text": display, "layout": layout}},
    }


# ── conversions ───────────────────────────────────────────────────────────────
def test_knots_to_ms():
    out = sk.project(_frame("0x41", 10.0))
    assert math.isclose(out["navigation.speedThroughWater"], 10.0 * 0.514444)


def test_degrees_to_radians():
    out = sk.project(_frame("0x51", 90.0))
    assert math.isclose(out["environment.wind.angleApparent"], math.pi / 2)


def test_celsius_to_kelvin():
    out = sk.project(_frame("0x1F", 20.0))
    assert math.isclose(out["environment.water.temperature"], 293.15)


def test_nm_to_m():
    out = sk.project(_frame("0xCF", 2.0))
    assert math.isclose(out["navigation.trip.log"], 3704.0)


def test_pressure_hpa_to_pa():
    out = sk.project(_frame("0x87", 1013.0))
    assert math.isclose(out["environment.outside.pressure"], 101300.0)


def test_percent_to_ratio():
    out = sk.project(_frame("0x7C", 98.0))
    assert math.isclose(out["performance.polarSpeedRatio"], 0.98)


def test_native_ms_passthrough():
    out = sk.project(_frame("0x4F", 3.8))   # AWS already m/s
    assert out["environment.wind.speedApparent"] == 3.8


# ── depth fallback chain ──────────────────────────────────────────────────────
def test_depth_prefers_metres():
    f = {"command": "Broadcast", "values": {
        "m": {"channel_id": "0xC1", "value": 7.3, "layout": None, "display_text": None},
        "ft": {"channel_id": "0xC2", "value": 24.1, "layout": None, "display_text": None},
    }}
    out = sk.project(f)
    assert out["environment.depth.belowTransducer"] == 7.3


def test_depth_falls_back_to_feet():
    out = sk.project(_frame("0xC2", 24.0))
    assert math.isclose(out["environment.depth.belowTransducer"], 24.0 * 0.3048)


def test_depth_falls_back_to_fathoms():
    out = sk.project(_frame("0xC3", 4.0))
    assert math.isclose(out["environment.depth.belowTransducer"], 4.0 * 1.8288)


# ── layout-routed bearings ────────────────────────────────────────────────────
def test_heading_magnetic_by_layout():
    out = sk.project(_frame("0x49", 180.0, layout="°M"))
    assert "navigation.headingMagnetic" in out
    assert math.isclose(out["navigation.headingMagnetic"], math.pi)


def test_heading_true_by_layout():
    out = sk.project(_frame("0x49", 180.0, layout="°T"))
    assert "navigation.headingTrue" in out


def test_twd_defaults_magnetic():
    out = sk.project(_frame("0x6D", 90.0, layout="°M"))
    assert "environment.wind.directionMagnetic" in out


def test_tidal_set_defaults_magnetic():
    out = sk.project(_frame("0x84", 45.0, layout="°M"))
    assert "environment.current.setMagnetic" in out


# ── enums, position, battery, drop, None ──────────────────────────────────────
def test_autopilot_state_standby():
    out = sk.project(_frame("0xB5", float(0x5000)))
    assert out["steering.autopilot.state"] == "standby"


def test_autopilot_state_wind():
    out = sk.project(_frame("0xB5", float(0x5104)))
    assert out["steering.autopilot.state"] == "wind"


def test_battery_instance_injected():
    out = sk.project(_frame("0x8D", 12.6), battery_id="house")
    assert out["electrical.batteries.house.voltage"] == 12.6


def test_position_parse():
    f = {"command": "LatLon", "values": {"LatLon": {
        "channel_id": "0x47", "value": None, "layout": None,
        "display_text": "3352.450S15113.920E"}}}
    out = sk.project(f)
    pos = out["navigation.position"]
    assert math.isclose(pos["latitude"], -(33 + 52.450 / 60), rel_tol=1e-6)
    assert math.isclose(pos["longitude"], 151 + 13.920 / 60, rel_tol=1e-6)


def test_dropped_channel_omitted():
    assert sk.project(_frame("0x00", 1.0)) == {}       # Node Reset
    assert sk.project(_frame("0x36", 1.0)) == {}       # Depth Sounder Gain


def test_none_value_passthrough():
    out = sk.project(_frame("0x41", None))
    assert out["navigation.speedThroughWater"] is None


def test_vendor_path():
    out = sk.project(_frame("0x85", 5.0))              # Upwash
    assert "bandg.wind.upwash" in out


def test_unmapped_channel_emitted_as_unknown():
    out = sk.project(_frame("0x0C", 123.0))            # Linear 5 — in CHANNEL_LOOKUP, unmapped
    assert out == {"bandg.unknown.0x0C": 123.0}


def test_unknown_channel_id_emitted():
    out = sk.project(_frame("0xC4", 42.0))             # id not in CHANNEL_LOOKUP
    assert out == {"bandg.unknown.0xC4": 42.0}


def test_collapsed_channel_not_unknown():
    out = sk.project(_frame("0x1C", 70.0))             # Air Temp °F — collapsed, must be dropped
    assert out == {}


def test_unknown_skips_none_value():
    out = sk.project(_frame("0xC5", None))             # unmapped, no value → nothing
    assert out == {}


# ── end-to-end against a real decoded frame ───────────────────────────────────
def test_real_heel_frame_end_to_end():
    # Heel-to-port frame (value -20.4°) from tests/test_heel_trim.py
    frame = bytes.fromhex("ff051401e78d8105263b3101fa344700f300cc9b4700a000099b")
    decoded = decode_frame(frame)
    out = sk.project(decoded)
    assert math.isclose(out["navigation.attitude.roll"], math.radians(-20.4), rel_tol=1e-3)
    assert "navigation.attitude.pitch" in out          # Fore/Aft Trim in same frame


# ── cut-over: FrameBuffer emits the projection by default ─────────────────────
def test_framebuffer_emits_paths_by_default():
    fb = FrameBuffer()   # project=True
    fb.add_to_buffer(bytes.fromhex("ff051401e78d8105263b3101fa344700f300cc9b4700a000099b"))
    fb.get_complete_frames()
    fr = fb.frame_queue.get_nowait()
    assert "navigation.attitude.roll" in fr["values"]
    assert math.isclose(fr["values"]["navigation.attitude.roll"], math.radians(-20.4), rel_tol=1e-3)


def test_framebuffer_project_false_keeps_rich():
    fb = FrameBuffer(project=False)
    fb.add_to_buffer(bytes.fromhex("ff051401e78d8105263b3101fa344700f300cc9b4700a000099b"))
    fb.get_complete_frames()
    fr = fb.frame_queue.get_nowait()
    assert "Heel Angle" in fr["values"]                # rich, name-keyed
    assert "display_text" in fr["values"]["Heel Angle"]


def test_framebuffer_drops_backlight():
    fb = FrameBuffer()
    fb.add_to_buffer(bytes.fromhex("ff5001c9e704fc"))
    fb.get_complete_frames()
    assert fb.frame_queue.empty()                      # 0xC9 dropped from projection
