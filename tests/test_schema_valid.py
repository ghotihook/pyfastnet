"""fastnet.json must be a well-formed description of the protocol.

interpreter.py trusts the schema completely, so a malformed edit is otherwise
invisible until a boat sends the frame that touches it — surfacing as a
KeyError or ValueError inside project(), in a library other applications
depend on. These tests run tools/validate_schema.py so that a bad edit fails
here instead.

What this does NOT check is whether the protocol facts are *right* — a wrong
scale factor or an inverted sign is a question about boats, and the
real-frame tests alongside this file are what answer it.
"""

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_schema", REPO_ROOT / "tools" / "validate_schema.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_validator()
SCHEMA = json.loads(VALIDATOR.SCHEMA_PATH.read_text(encoding="utf-8"))


def test_shipped_schema_has_no_errors():
    errors, _warnings = VALIDATOR.validate(SCHEMA)
    assert not errors, "fastnet.json is malformed:\n  " + "\n  ".join(errors)


def test_validator_rejects_an_unimplemented_transform():
    # The failure mode this file exists for: _apply_transform() raises
    # ValueError on an unknown type, but only once that channel appears on
    # the wire — which for an untested channel could be months away.
    broken = json.loads(json.dumps(SCHEMA))
    broken["channels"]["0x41"]["signalk"]["transform"] = {"type": "scaled", "factor": 0.5}
    errors, _ = VALIDATOR.validate(broken)
    assert any("does not implement" in e for e in errors)


def test_validator_rejects_a_dangling_override():
    broken = json.loads(json.dumps(SCHEMA))
    broken["channels"]["0x41"]["overrides"] = {"0x01": "noSuchFunction"}
    errors, _ = VALIDATOR.validate(broken)
    assert any("noSuchFunction" in e for e in errors)


def test_validator_rejects_a_half_added_channel():
    # Adding to "channels" but forgetting lookups.channelNames (or vice versa)
    # leaves the channel decodable but nameless.
    broken = json.loads(json.dumps(SCHEMA))
    broken["channels"]["0x2D"] = {"name": "Test", "signalk": {"drop": True}}
    errors, _ = VALIDATOR.validate(broken)
    assert any("0x2D" in e and "channelNames" in e for e in errors)


def test_validator_rejects_a_non_canonical_channel_key():
    # interpreter.py matches f"0x{id:02X}", so '0x4a' silently never matches.
    broken = json.loads(json.dumps(SCHEMA))
    broken["channels"]["0x4a"] = broken["channels"].pop("0x4A")
    broken["lookups"]["channelNames"]["0x4a"] = broken["lookups"]["channelNames"].pop("0x4A")
    errors, _ = VALIDATOR.validate(broken)
    assert any("canonical byte code" in e for e in errors)


def test_validator_rejects_a_template_reading_past_its_record():
    broken = json.loads(json.dumps(SCHEMA))
    broken["formatTemplates"]["0x01"]["valueBytes"] = [0, 4]  # 0x01 records are 2 bytes
    errors, _ = VALIDATOR.validate(broken)
    assert any("outside this record" in e for e in errors)


def test_validator_rejects_an_ambiguous_fallback_chain():
    # Depth resolves metres > feet > fathoms by fallbackPriority; a tie would
    # make which one wins undefined.
    broken = json.loads(json.dumps(SCHEMA))
    broken["channels"]["0xC3"]["signalk"]["fallbackPriority"] = \
        broken["channels"]["0xC2"]["signalk"]["fallbackPriority"]
    errors, _ = VALIDATOR.validate(broken)
    assert any("fallbackPriority" in e for e in errors)
