"""conformance/vectors.json must match what this library produces.

The vectors are the contract other-language implementations test against, so they
must never drift silently from the reference. If a change to the output is intended
(or fastnet.json was edited), regenerate with `python conformance/generate_vectors.py`
and say why in the commit. See conformance/README.md.
"""
import importlib.util
import json
from pathlib import Path

import pytest

CONFORMANCE = Path(__file__).resolve().parents[1] / "conformance"
REGENERATE = "regenerate with: python conformance/generate_vectors.py"

_spec = importlib.util.spec_from_file_location("generate_vectors", CONFORMANCE / "generate_vectors.py")
_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gen)

_committed = json.loads((CONFORMANCE / "vectors.json").read_text(encoding="utf-8"))
# Round-trip through JSON so the comparison sees exactly what a file would hold.
_fresh = json.loads(json.dumps(_gen.build(), ensure_ascii=False))
_fresh_streams = {stream["capture"]: stream for stream in _fresh["streams"]}
_fresh_frames = {vector["id"]: vector for vector in _fresh["frames"]}


def test_vectors_were_generated_from_this_schema():
    assert _fresh["meta"]["schema_sha256"] == _committed["meta"]["schema_sha256"], (
        f"fastnet.json changed since vectors.json was generated - {REGENERATE}")


def test_same_frames_selected():
    assert [v["frame"] for v in _fresh["frames"]] == [v["frame"] for v in _committed["frames"]], (
        f"the coverage-driven frame selection changed - {REGENERATE}")


@pytest.mark.parametrize("stream", _committed["streams"], ids=lambda s: s["capture"])
def test_stream(stream):
    assert _fresh_streams.get(stream["capture"]) == stream, REGENERATE


@pytest.mark.parametrize("vector", _committed["frames"], ids=lambda v: v["id"])
def test_frame(vector):
    assert _fresh_frames.get(vector["id"]) == vector, REGENERATE
