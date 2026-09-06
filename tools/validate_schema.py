#!/usr/bin/env python3
"""Proofread fastnet.json — is it a well-formed description of the protocol?

`interpreter.py` trusts this schema completely: it looks things up by key and
assumes what comes back is shaped the way it expects. A malformed edit is
therefore invisible until a boat actually sends the frame that touches it,
and then it surfaces as a KeyError or ValueError deep inside project() — in a
library other applications depend on, possibly months later, at sea.

This script reads the schema on its own and answers one question: does it say
something the interpreter could actually carry out? It checks structure and
internal consistency only.

It deliberately does NOT check whether the protocol facts are *correct*. That
a scale factor is 0.514444, or that heel-to-port is negative, are questions
about boats, answerable against a real instrument — they belong in the test
suite, where real captured frames live.

Run it directly:

    python tools/validate_schema.py          # exit 0 = clean, 1 = errors found

`tests/test_schema_valid.py` runs the same checks, so a malformed edit fails
the normal test run rather than waiting for a boat.
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "fastnet_decoder" / "data" / "fastnet.json"

# ── what the interpreter requires of each format template ─────────────────────
#
# Keyed by the "op" name a template can declare. "required" fields must be
# present; "byte_fields" name fields holding a single byte index, and
# "range_fields" name fields holding a [start, end] byte slice - both are
# checked against the record size that formatSizeMap declares for that nibble,
# so a template can never reach past the end of its own record.
#
# If you add a new op to interpreter.py, add it here too - an unknown op is
# reported as an error rather than passing silently.
OP_SPECS = {
    "scaledInt":         {"required": ["signed"], "range_fields": ["valueBytes"],
                          "byte_fields": ["statusByte"]},
    "scaledBitfield":    {"required": ["signed", "pieces"]},
    "signedLayoutValue": {"required": ["layoutByte"], "byte_fields": ["layoutByte", "statusByte"],
                          "range_fields": ["valueBytes"],
                          "one_of": ["pieces", "valueBytes"]},
    "layoutValue":       {"required": ["layoutBits", "pieces"]},
    "durationHMS":       {"required": ["hByte", "mByte", "sByte"],
                          "byte_fields": ["hByte", "mByte", "sByte", "statusByte"]},
    "segmentDisplay":    {"required": ["lookup"]},
    "pairedScaledInt":   {"required": ["signed", "firstBytes", "secondBytes"],
                          "range_fields": ["firstBytes", "secondBytes"]},
    "unsupported":       {"required": []},
}

# Transform types _apply_transform() implements, and the fields each one reads.
TRANSFORM_SPECS = {
    "identity":     [],
    "scale":        ["factor"],
    "affine":       ["scale", "offset"],
    "overrideEnum": ["ref"],
}

CHANNEL_KEYS = {"name", "signalk", "overrides", "_comment"}
SIGNALK_KEYS = {"path", "unit", "transform", "routedBy", "routes", "drop",
                "collapsedInto", "fallbackGroup", "fallbackPriority", "pathParam",
                "_comment"}
REQUIRED_LOOKUPS = ["addresses", "commands", "ignoredCommands", "backlightLevels",
                    "channelNames", "segmentA", "segmentB", "layoutSign",
                    "layoutDisplay", "autopilotState"]


CANONICAL_HEX = re.compile(r"^0x[0-9A-F]{2}$")


def _is_hex_key(key):
    """True if `key` is a byte code written the one canonical way: '0x' plus
    two UPPERCASE hex digits, e.g. '0x4A'.

    This is stricter than "parses as hex" on purpose. interpreter.py finds
    channels, format templates and autopilot states by building the string
    f"0x{value:02X}" and matching it against these keys, so a key written
    '0x4a' (or '4A', or '0x4') never matches. Nothing errors - the channel
    just silently loses its name and Signal K mapping and falls through to
    bandg.unknown, which is far harder to notice than a crash.
    """
    return isinstance(key, str) and bool(CANONICAL_HEX.match(key))


def _is_hex_number(text):
    """True if `text` is a hex literal interpreter.py can parse with
    int(text, 16) - used for bitmasks, where any hex spelling works."""
    try:
        int(text, 16)
        return True
    except (ValueError, TypeError):
        return False


def _implemented_override_names():
    """The override functions interpreter.py actually implements.

    Imported rather than hardcoded so this can never drift from the code -
    a channel referencing an override that was never written is an error.
    """
    from fastnet_decoder.interpreter import _OVERRIDES
    return set(_OVERRIDES)


def validate(schema):
    """Check `schema` and return (errors, warnings) as two lists of strings.

    An error means the interpreter could hit it and fail. A warning means the
    schema is self-consistent but describes something unreachable - usually a
    gap in what's been reverse-engineered so far, not a mistake.
    """
    errors = []
    warnings = []

    def err(msg):
        errors.append(msg)

    def warn(msg):
        warnings.append(msg)

    # ── top-level sections ────────────────────────────────────────────────────
    for section in ("scaling", "formatSizeMap", "formatTemplates", "lookups", "channels"):
        if section not in schema:
            err(f"missing top-level section {section!r}")
    if errors:
        return errors, warnings  # nothing below can be checked meaningfully

    size_map = schema["formatSizeMap"]
    templates = schema["formatTemplates"]
    lookups = schema["lookups"]
    channels = schema["channels"]

    # ── scaling ───────────────────────────────────────────────────────────────
    divisors = schema["scaling"].get("divisorByTopTwoBits", {})
    decimals = schema["scaling"].get("decimalPlacesByDivisor", {})
    for bits in ("0", "1", "2", "3"):
        if bits not in divisors:
            err(f"scaling.divisorByTopTwoBits missing entry for top-two-bits {bits}")
    for divisor in divisors.values():
        if str(divisor) not in decimals:
            err(f"scaling.decimalPlacesByDivisor has no entry for divisor {divisor}")

    # ── formatSizeMap ─────────────────────────────────────────────────────────
    for key, size in size_map.items():
        if not _is_hex_key(key):
            err(f"formatSizeMap key {key!r} is not a canonical byte code like '0x08' (need '0x' + two UPPERCASE hex digits)")
        if not isinstance(size, int) or size <= 0:
            err(f"formatSizeMap[{key}] must be a positive integer, got {size!r}")
        if key not in templates:
            err(f"formatSizeMap[{key}] has no matching formatTemplates entry")

    # ── formatTemplates ───────────────────────────────────────────────────────
    for key, template in templates.items():
        where = f"formatTemplates[{key}]"
        if not _is_hex_key(key):
            err(f"{where} key is not a canonical byte code like '0x08' (need '0x' + two UPPERCASE hex digits)")
        if not isinstance(template, dict) or "op" not in template:
            err(f"{where} has no 'op' field")
            continue

        op = template["op"]
        spec = OP_SPECS.get(op)
        if spec is None:
            err(f"{where} names unknown op {op!r} — "
                f"interpreter.py implements {sorted(OP_SPECS)}")
            continue

        if op == "unsupported":
            # Legitimately undecodable, but the frame walker still needs a size
            # to step over the record; without one it consumes zero data bytes
            # and reads the rest of the frame misaligned.
            if key not in size_map:
                warn(f"{where} is 'unsupported' and has no formatSizeMap entry — "
                     f"if a {key} record ever appears, the frame walker cannot "
                     f"skip it and will misread the rest of the frame")
            continue

        if key not in size_map:
            err(f"{where} declares op {op!r} but formatSizeMap has no size for {key}")
            continue
        size = size_map[key]

        for field in spec.get("required", []):
            if field not in template:
                err(f"{where} (op {op!r}) is missing required field {field!r}")

        one_of = spec.get("one_of")
        if one_of and not any(field in template for field in one_of):
            err(f"{where} (op {op!r}) must have one of {one_of}")

        for field in spec.get("byte_fields", []):
            if field in template:
                index = template[field]
                if not isinstance(index, int) or not (0 <= index < size):
                    err(f"{where}.{field} = {index!r} is outside this record's "
                        f"{size} data bytes")

        for field in spec.get("range_fields", []):
            if field in template:
                span = template[field]
                if (not isinstance(span, list) or len(span) != 2
                        or not all(isinstance(n, int) for n in span)):
                    err(f"{where}.{field} must be a [start, end] pair, got {span!r}")
                elif not (0 <= span[0] < span[1] <= size):
                    err(f"{where}.{field} = {span} is outside this record's "
                        f"{size} data bytes")

        if "pieces" in template:
            _check_pieces(template["pieces"], size, f"{where}.pieces", err)

        if "layoutBits" in template:
            bits = template["layoutBits"]
            if not isinstance(bits, dict):
                err(f"{where}.layoutBits must be an object")
            else:
                for field in ("byte", "mask", "shiftRight"):
                    if field not in bits:
                        err(f"{where}.layoutBits is missing {field!r}")
                if isinstance(bits.get("byte"), int) and not (0 <= bits["byte"] < size):
                    err(f"{where}.layoutBits.byte = {bits['byte']} is outside this "
                        f"record's {size} data bytes")
                if "mask" in bits and not _is_hex_number(bits["mask"]):
                    err(f"{where}.layoutBits.mask = {bits['mask']!r} is not a hex number")

        if op == "segmentDisplay":
            referenced = template.get("lookup")
            if referenced is not None and referenced not in lookups:
                err(f"{where}.lookup names {referenced!r}, which is not in lookups")

    # ── lookups ───────────────────────────────────────────────────────────────
    for name in REQUIRED_LOOKUPS:
        if name not in lookups:
            err(f"lookups is missing required table {name!r}")

    for name in ("addresses", "commands", "backlightLevels", "channelNames",
                 "segmentA", "segmentB", "autopilotState"):
        for key in lookups.get(name, {}):
            if key != "_comment" and not _is_hex_key(key):
                err(f"lookups.{name} key {key!r} is not a canonical byte code like '0x41' (need '0x' + two UPPERCASE hex digits)")

    for code, value in lookups.get("segmentA", {}).items():
        if code == "_comment":
            continue
        if value is not None and not isinstance(value, str):
            err(f"lookups.segmentA[{code}] must be a layout-token string or null, "
                f"got {value!r}")

    for token, sign in lookups.get("layoutSign", {}).items():
        if token == "_comment":
            continue
        if sign not in (-1, 1):
            err(f"lookups.layoutSign[{token!r}] must be -1 or 1, got {sign!r}")

    for code, entry in lookups.get("autopilotState", {}).items():
        if code == "_comment":
            continue
        if not isinstance(entry, dict) or "displayText" not in entry or "signalk" not in entry:
            err(f"lookups.autopilotState[{code}] must have 'displayText' and 'signalk'")

    # Every layout token the sign/display tables mention must be one that some
    # segmentA code can actually produce - otherwise the rule is dead.
    producible_tokens = {value for value in lookups.get("segmentA", {}).values()
                         if isinstance(value, str)}
    for table in ("layoutSign", "layoutDisplay"):
        for token in lookups.get(table, {}):
            if token == "_comment":
                continue
            if token not in producible_tokens:
                warn(f"lookups.{table} has a rule for layout token {token!r}, but no "
                     f"segmentA code produces that token — the rule is unreachable")

    # ── channels ──────────────────────────────────────────────────────────────
    channel_names = {k: v for k, v in lookups.get("channelNames", {}).items()
                     if k != "_comment"}
    missing_from_names = set(channels) - set(channel_names)
    missing_from_channels = set(channel_names) - set(channels)
    for cid in sorted(missing_from_names):
        err(f"channel {cid} is in 'channels' but missing from lookups.channelNames")
    for cid in sorted(missing_from_channels):
        err(f"channel {cid} is in lookups.channelNames but missing from 'channels'")

    override_names = _implemented_override_names()
    emitted_paths = _collect_emitted_paths(channels)
    fallback_groups = {}

    for cid, info in channels.items():
        where = f"channels[{cid}]"
        if not _is_hex_key(cid):
            err(f"{where} key is not a canonical byte code like '0x41' (need '0x' + two UPPERCASE hex digits)")
        if not isinstance(info, dict):
            err(f"{where} must be an object")
            continue

        unknown = set(info) - CHANNEL_KEYS
        if unknown:
            err(f"{where} has unrecognised key(s) {sorted(unknown)} — "
                f"expected any of {sorted(CHANNEL_KEYS)}")

        name = info.get("name")
        if not isinstance(name, str) or not name:
            err(f"{where} is missing a non-empty 'name'")
        elif cid in channel_names and channel_names[cid] != name:
            err(f"{where}.name is {name!r} but lookups.channelNames[{cid}] is "
                f"{channel_names[cid]!r} — the two must agree")

        for format_key, override in (info.get("overrides") or {}).items():
            if not _is_hex_key(format_key):
                err(f"{where}.overrides key {format_key!r} is not a canonical byte code like '0x01'")
            if override not in override_names:
                err(f"{where}.overrides[{format_key}] names {override!r}, which is not "
                    f"implemented in interpreter.py's _OVERRIDES "
                    f"(has {sorted(override_names)})")

        signalk = info.get("signalk")
        if signalk is None:
            continue
        if not isinstance(signalk, dict):
            err(f"{where}.signalk must be an object")
            continue

        unknown = set(signalk) - SIGNALK_KEYS
        if unknown:
            err(f"{where}.signalk has unrecognised key(s) {sorted(unknown)} — "
                f"expected any of {sorted(SIGNALK_KEYS)}")

        if signalk.get("drop") or "collapsedInto" in signalk:
            target = signalk.get("collapsedInto")
            if target is not None and target not in emitted_paths:
                err(f"{where}.signalk.collapsedInto is {target!r}, but no channel "
                    f"emits that path")
            continue

        if "routes" in signalk:
            if signalk.get("routedBy") != "layout":
                err(f"{where}.signalk has 'routes' but routedBy is "
                    f"{signalk.get('routedBy')!r} (expected 'layout')")
            if not signalk["routes"]:
                err(f"{where}.signalk.routes is empty")
            for token, route in signalk["routes"].items():
                if not isinstance(route, dict) or "path" not in route:
                    err(f"{where}.signalk.routes[{token!r}] must have a 'path'")
                if token not in producible_tokens:
                    warn(f"{where}.signalk routes on layout token {token!r}, but no "
                         f"segmentA code produces it — that route can never be "
                         f"taken from real frames "
                         f"(path {route.get('path') if isinstance(route, dict) else '?'})")
        elif "path" not in signalk:
            err(f"{where}.signalk has neither 'path', 'routes', 'drop' nor "
                f"'collapsedInto' — nothing says where this channel goes")

        if "pathParam" in signalk:
            param = signalk["pathParam"]
            path = signalk.get("path", "")
            if "{" + str(param) + "}" not in path:
                err(f"{where}.signalk.pathParam is {param!r} but path {path!r} has no "
                    f"'{{{param}}}' placeholder to fill in")

        if "fallbackGroup" in signalk:
            priority = signalk.get("fallbackPriority")
            if not isinstance(priority, int):
                err(f"{where}.signalk has fallbackGroup "
                    f"{signalk['fallbackGroup']!r} but no integer fallbackPriority — "
                    f"the tie-break between redundant sources would be undefined")
            else:
                fallback_groups.setdefault(signalk["fallbackGroup"], []).append((priority, cid))

        transform = signalk.get("transform")
        if transform is None:
            err(f"{where}.signalk has no 'transform' — say {{\"type\": \"identity\"}} "
                f"if the value is already in SI units")
        else:
            _check_transform(transform, lookups, f"{where}.signalk.transform", err)

    for group, members in fallback_groups.items():
        seen = {}
        for priority, cid in members:
            if priority in seen:
                err(f"fallbackGroup {group!r}: channels {seen[priority]} and {cid} both "
                    f"claim fallbackPriority {priority} — which one wins is undefined")
            seen[priority] = cid

    return errors, warnings


def _check_pieces(pieces, size, where, err):
    """Every bit-field piece must name a byte inside the record and a hex mask."""
    if not isinstance(pieces, list) or not pieces:
        err(f"{where} must be a non-empty list of bit-field pieces")
        return
    for n, piece in enumerate(pieces):
        if not isinstance(piece, dict):
            err(f"{where}[{n}] must be an object")
            continue
        for field in ("byte", "mask", "shiftLeft"):
            if field not in piece:
                err(f"{where}[{n}] is missing {field!r}")
        index = piece.get("byte")
        if isinstance(index, int) and not (0 <= index < size):
            err(f"{where}[{n}].byte = {index} is outside this record's {size} data bytes")
        if "mask" in piece and not _is_hex_number(piece["mask"]):
            err(f"{where}[{n}].mask = {piece['mask']!r} is not a hex number like '0xFF'")


def _check_transform(transform, lookups, where, err):
    """A transform must name a type _apply_transform() implements, and carry
    the numeric fields that type reads."""
    if not isinstance(transform, dict) or "type" not in transform:
        err(f"{where} must be an object with a 'type'")
        return
    kind = transform["type"]
    spec = TRANSFORM_SPECS.get(kind)
    if spec is None:
        err(f"{where}.type is {kind!r}, which _apply_transform() does not implement "
            f"(has {sorted(TRANSFORM_SPECS)}) — this raises ValueError at decode time")
        return
    for field in spec:
        if field not in transform:
            err(f"{where} (type {kind!r}) is missing required field {field!r}")
        elif field == "ref":
            if transform[field] not in lookups:
                err(f"{where}.ref names {transform[field]!r}, which is not in lookups")
        elif not isinstance(transform[field], (int, float)):
            err(f"{where}.{field} must be a number, got {transform[field]!r}")


def _collect_emitted_paths(channels):
    """Every Signal K path some channel actually emits — used to check that a
    'collapsedInto' target is a real destination and not a typo."""
    paths = set()
    for info in channels.values():
        signalk = info.get("signalk") if isinstance(info, dict) else None
        if not isinstance(signalk, dict) or signalk.get("drop"):
            continue
        if isinstance(signalk.get("path"), str):
            paths.add(signalk["path"])
        for route in (signalk.get("routes") or {}).values():
            if isinstance(route, dict) and isinstance(route.get("path"), str):
                paths.add(route["path"])
    return paths


def main():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors, warnings = validate(schema)

    for warning in warnings:
        print(f"warning: {warning}")
    for error in errors:
        print(f"ERROR: {error}")

    channel_count = len(schema.get("channels", {}))
    if errors:
        print(f"\n{SCHEMA_PATH.name}: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"\n{SCHEMA_PATH.name} OK — {channel_count} channels, "
          f"{len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
