#!/usr/bin/env python3
"""Bootstrap fastnet_decoder/data/fastnet.json from the current hand-written decoder.

One-time (Stage 1) migration tool: mechanically mirrors ADDRESS_LOOKUP, COMMAND_LOOKUP,
CHANNEL_LOOKUP, SEGMENT_A, SEGMENT_B, and the signalk_map.py projection tables
(STANDARD/VENDOR/_ROUTED/DEPTH/COLLAPSED/DROP) into the schema. The 8 format-byte
templates and the layout sign/display-formatting rules are not mechanically
extractable from decode_format_and_data's control flow, so they're transcribed by
hand below (verified against fastnet_decoder/decode_fastnet.py).

Not a permanent tool: after Stage 3's cutover, mappings.py/decode_fastnet.py/
signalk_map.py are deleted and data/fastnet.json becomes the only source of truth,
so there is nothing left to extract from on a second run.
"""
import json
from pathlib import Path

from fastnet_decoder import mappings
from fastnet_decoder import signalk_map as sk

OUT_PATH = Path(__file__).resolve().parent.parent / "fastnet_decoder" / "data" / "fastnet.json"


def hx(n: int) -> str:
    return f"0x{n:02X}"


# ── Scaling: format_byte bits 6-7 -> divisor -> decimal places ────────────────
# Mirrors decode_fastnet.py's _DIVISOR_MAP / _DECIMAL_PLACES_MAP.
SCALING = {
    "divisorByTopBits": {"0b00": 1, "0b01": 10, "0b10": 100, "0b11": 1000},
    "decimalPlacesByDivisor": {"1": 0, "10": 1, "100": 2, "1000": 3},
}

# ── Format byte low-nibble -> record byte length ───────────────────────────────
# Mirrors mappings.FORMAT_SIZE_MAP exactly (used by the frame walker to size each
# channel record, independent of whether that nibble has a decode template below).
FORMAT_SIZE_MAP = {hx(k): v for k, v in mappings.FORMAT_SIZE_MAP.items()}

# ── Format templates: hand-transcribed from decode_format_and_data's branches ──
# op vocabulary: scaledInt, scaledBitfield, signedLayoutValue, layoutValue,
# durationHMS, segmentDisplay, pairedScaledInt, unsupported.
FORMAT_TEMPLATES = {
    "0x00": {"op": "unsupported", "_comment": "sized (4B) but no decode branch exists in decode_format_and_data"},
    "0x01": {"op": "scaledInt", "signed": True, "valueBytes": [0, 2]},
    "0x02": {"op": "scaledBitfield", "signed": False,
             "pieces": [{"byte": 0, "mask": "0x03", "shiftLeft": 8}, {"byte": 1, "mask": "0xFF", "shiftLeft": 0}]},
    "0x03": {"op": "signedLayoutValue", "layoutByte": 0, "valueBytes": [1, 2]},
    "0x04": {"op": "scaledInt", "signed": False, "statusByte": 0, "valueBytes": [1, 4],
              "_comment": "data_bytes[0] is a status/flag byte, dropped"},
    "0x05": {"op": "durationHMS", "statusByte": 0, "hByte": 1, "mByte": 2, "sByte": 3,
              "_comment": "data_bytes[0] is a status/flag byte, dropped"},
    "0x06": {"op": "segmentDisplay", "lookup": "segmentB",
              "_comment": "value is always null by protocol design - display-only channel"},
    "0x07": {"op": "signedLayoutValue", "statusByte": 0, "layoutByte": 1,
             "pieces": [{"byte": 2, "mask": "0x7F", "shiftLeft": 8}, {"byte": 3, "mask": "0xFF", "shiftLeft": 0}],
             "_comment": "data_bytes[0] is a status/flag byte, dropped; MSB masked to 7 bits"},
    "0x08": {"op": "layoutValue", "layoutBits": {"byte": 0, "mask": "0xFE", "shiftRight": 1},
             "pieces": [{"byte": 0, "mask": "0x01", "shiftLeft": 8}, {"byte": 1, "mask": "0xFF", "shiftLeft": 0}],
             "_comment": "unlike signedLayoutValue, layout does NOT flip sign here - display-only"},
    "0x0A": {"op": "pairedScaledInt", "signed": True, "firstBytes": [0, 2], "secondBytes": [2, 4],
             "_comment": "value is 'first'; display_text shows 'first / second'"},
    "0x09": {"op": "unsupported", "_comment": "never observed in captured data"},
}

# ── Layout-token rules (keyed by the SEGMENT_A string value, not the byte code) ─
# Multiple byte codes can share a token (e.g. 0x28 and 0x0c both -> "[data]=").
# Sign: mirrors decode_fastnet._sign_from_layout exactly.
LAYOUT_SIGN = {"-[data]": -1, "=[data]": -1, "L[data]": -1, "H[data]": -1}

# Display: mirrors decode_fastnet._display_from_layout exactly, including its
# real quirks - "H[data]" strips the value's leading '-' before prefixing (since
# the sign is carried by the H itself), but "L[data]" does NOT (renders "L-2.0");
# "-[data]"/"=[data]" (leading forms) have NO explicit branch in the original code
# and fall through unchanged - the negative sign is already baked into the value,
# no extra prefix character is added. Only the trailing forms ("[data]-"/"[data]=")
# add a decorative suffix character.
LAYOUT_DISPLAY = {
    "°M":       {"suffix": "°M"},
    "H[data]":  {"prefix": "H", "stripSign": True},
    "[data]H":  {"suffix": "H"},
    "[data]=":  {"suffix": "="},
    "[data]-":  {"suffix": "-"},
    "[data]°C": {"suffix": "°C"},
    "[data]°F": {"suffix": "°F"},
    "[data]L":  {"suffix": "L"},
    "L[data]":  {"prefix": "L"},
    "[data]z":  {"suffix": "z"},
    "z[data]":  {"prefix": "z"},
    "u[data]":  {"prefix": "u"},
    "d[data]":  {"prefix": "d"},
}


def build_lookups():
    addresses = {hx(k): v for k, v in mappings.ADDRESS_LOOKUP.items()}
    commands = {hx(k): v for k, v in mappings.COMMAND_LOOKUP.items()}
    channel_names = {hx(k): v for k, v in mappings.CHANNEL_LOOKUP.items()}
    segment_a = {hx(k): v for k, v in mappings.SEGMENT_A.items()}
    segment_b = {hx(k): v for k, v in mappings.SEGMENT_B.items()}
    backlight_levels = {hx(k): v for k, v in mappings.BACKLIGHT_LEVELS.items()}

    # Unify the two independently-maintained autopilot tables. Their string
    # values are expected to differ (AUTOPILOT_MODE_BY_LOW holds human display
    # text, _AP_MODE_BY_LOW holds the SignalK enum for the same low byte) - this
    # isn't a bug, but merging them removes the risk of the two tables getting a
    # low byte added to one and not the other in future edits.
    autopilot_state = {}
    all_low_bytes = set(mappings.AUTOPILOT_MODE_BY_LOW) | set(sk._AP_MODE_BY_LOW)
    missing = all_low_bytes - (set(mappings.AUTOPILOT_MODE_BY_LOW) & set(sk._AP_MODE_BY_LOW))
    if missing:
        print(f"  WARNING: low byte(s) present in only one autopilot table: {[hx(b) for b in sorted(missing)]}")
    for low in sorted(all_low_bytes):
        autopilot_state[hx(low)] = {
            "displayText": mappings.AUTOPILOT_MODE_BY_LOW.get(low),
            "signalk": sk._AP_MODE_BY_LOW.get(low),
        }

    return {
        "addresses": addresses,
        "commands": commands,
        "ignoredCommands": sorted(mappings.IGNORED_COMMANDS),
        "backlightLevels": backlight_levels,
        "channelNames": channel_names,
        "segmentA": segment_a,
        "segmentB": segment_b,
        "layoutSign": LAYOUT_SIGN,
        "layoutDisplay": LAYOUT_DISPLAY,
        "autopilotState": autopilot_state,
    }


# Reverse-lookup: SI transform function object (from signalk_map) -> declarative form.
TRANSFORM_BY_FUNC = {
    sk._kn:  {"type": "scale", "factor": sk.KN_MS},
    sk._nm:  {"type": "scale", "factor": sk.NM_M},
    sk._deg: {"type": "scale", "factor": sk.DEG_RAD},
    sk._c2k: {"type": "affine", "scale": 1, "offset": 273.15},
    sk._hpa: {"type": "scale", "factor": sk.HPA_PA},
    sk._pct: {"type": "scale", "factor": 0.01},
    sk._id:  {"type": "identity"},
}


def transform_for(tf):
    found = TRANSFORM_BY_FUNC.get(tf)
    if found is None:
        raise ValueError(f"no declarative transform mapping for function {tf!r} - extend TRANSFORM_BY_FUNC")
    return found


def build_channels():
    channels = {}

    # 0xB5 Autopilot Mode: not in STANDARD - handled by a dedicated branch in both
    # decode_fastnet.py (value decode) and signalk_map.py (projection). Modeled as
    # a channel-level override keyed by the format nibble it's observed under.
    channels[hx(0xB5)] = {
        "overrides": {"0x01": "autopilotMode"},
        "signalk": {"path": "steering.autopilot.state", "unit": "enum",
                    "transform": {"type": "overrideEnum", "ref": "autopilotState"}},
    }

    depth_cids = {cid for cid, _tf in sk.DEPTH}
    routed_cids = set(sk._ROUTED)
    standard_cids = set(sk.STANDARD)
    vendor_cids = set(sk.VENDOR)
    collapsed_cids = set(sk.COLLAPSED)
    drop_cids = set(sk.DROP)

    for cid, name in sorted(mappings.CHANNEL_LOOKUP.items()):
        if cid == 0xB5:
            channels[hx(cid)]["name"] = name
            continue

        entry = {"name": name}

        if cid in depth_cids:
            priority = {c: i for i, (c, _tf) in enumerate(sk.DEPTH)}[cid]
            tf = dict(sk.DEPTH)[cid]
            # DEPTH's non-0xC1 transforms are inline lambdas, not the named
            # functions in TRANSFORM_BY_FUNC - resolve their scale factor directly.
            if cid == 0xC1:
                transform = {"type": "identity"}
            elif cid == 0xC2:
                transform = {"type": "scale", "factor": sk.FT_M}
            elif cid == 0xC3:
                transform = {"type": "scale", "factor": sk.FATHOM_M}
            else:
                raise ValueError(f"unexpected depth channel 0x{cid:02X}")
            entry["signalk"] = {"path": sk.DEPTH_PATH, "unit": "m", "transform": transform,
                                 "fallbackGroup": "depth", "fallbackPriority": priority}

        elif cid in routed_cids:
            mag_path, true_path, tf = sk._ROUTED[cid]
            entry["signalk"] = {
                "routedBy": "layout",
                "routes": {"°M": {"path": mag_path}, "°T": {"path": true_path}},
                "unit": "rad", "transform": transform_for(tf),
            }

        elif cid in standard_cids:
            path, tf = sk.STANDARD[cid]
            signalk = {"path": path, "unit": sk.unit_for(path.format(id="house")) or None,
                       "transform": transform_for(tf)}
            if "{id}" in path:
                signalk["pathParam"] = "id"
                signalk["unit"] = "V"
            entry["signalk"] = signalk

        elif cid in vendor_cids:
            path, tf = sk.VENDOR[cid]
            entry["signalk"] = {"path": path, "unit": sk.unit_for(path), "transform": transform_for(tf)}

        elif cid in collapsed_cids:
            entry["signalk"] = {"collapsedInto": sk.COLLAPSED[cid]}

        elif cid in drop_cids:
            entry["signalk"] = {"drop": True}

        # else: no explicit disposition - channel is decodable but unmapped;
        # interpreter's project() falls back to bandg.unknown.0x<id>, same as
        # signalk_map.project()'s existing behaviour for cids matching none of
        # the above (kind == "unknown" in channel_map()).

        channels[hx(cid)] = entry

    return channels


def build_messages():
    return {
        "LatLon": {
            "command": hx(0x03),
            "bodyLayout": [
                {"name": "sourceMarker", "bytes": 1,
                 "_comment": "GPS-unit-dependent marker byte, NOT a CHANNEL_LOOKUP id - diagnostic only"},
                {"name": "formatByte", "bytes": 1, "_comment": "present but unused for ASCII frames"},
                {"name": "asciiFix", "bytes": "remaining", "encoding": "ascii", "strip": True},
            ],
            "parse": {"op": "latLonFix", "signalk": {"path": "navigation.position", "unit": "deg"}},
        },
        "LightIntensity": {
            "command": hx(0xC9),
            "bodyLayout": [{"name": "level", "bytes": 1, "lookup": "backlightLevels"}],
            "syntheticChannelName": "Backlight",
        },
    }


def main():
    schema = {
        "scaling": SCALING,
        "formatSizeMap": FORMAT_SIZE_MAP,
        "formatTemplates": FORMAT_TEMPLATES,
        "lookups": build_lookups(),
        "channels": build_channels(),
        "messages": build_messages(),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")
    print(f"  addresses={len(schema['lookups']['addresses'])} "
          f"channels={len(schema['channels'])} "
          f"segmentA={len(schema['lookups']['segmentA'])} "
          f"segmentB={len(schema['lookups']['segmentB'])}")


if __name__ == "__main__":
    main()
