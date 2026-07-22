"""Regression guard: the complete decoder must match the committed v2 golden baseline.

Recomputes each capture's decode hash and compares to tests/golden/v2_baseline.json,
catching any unintended change to value/display_text/layout during the pre-v3 fixes.
See tests/golden/README.md. At the v3 cut-over, repoint this at the retained
complete-decode path.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

GOLDEN = Path(__file__).resolve().parent / "golden"

# Reuse the generator's decode so the guard can't drift from how the baseline is built.
_spec = importlib.util.spec_from_file_location("gen_baseline", GOLDEN / "generate_baseline.py")
_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gen)

_baseline = json.loads((GOLDEN / "v2_baseline.json").read_text())


@pytest.mark.parametrize("capture", _gen.CAPTURES, ids=lambda p: p.name)
def test_decode_matches_baseline(capture):
    frames = _gen.decode_file(capture)
    blob = json.dumps(frames, sort_keys=True, ensure_ascii=False)
    got = hashlib.sha256(blob.encode()).hexdigest()
    assert _baseline["files"][capture.name]["decode_sha256"] == got, (
        f"complete-decode drift in {capture.name} — "
        f"regenerate with tests/golden/generate_baseline.py if intended"
    )
