"""Every script in examples/ and tools/ must actually run.

Scripts that nothing executes rot silently - two did, and went on importing modules
that 3.2.0 deleted. Each is run here the way a reader would run it.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _run(*args):
    result = subprocess.run([sys.executable, *args], cwd=REPO, capture_output=True,
                            text=True, encoding="utf-8", timeout=120)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_replay_capture():
    out = _run("examples/replay_capture.py", "captures/big.txt")
    assert "frames from big.txt" in out
    assert "navigation.speedThroughWater" in out


def test_inspect_frame():
    out = _run("examples/inspect_frame.py", "ff010a01f54192f9dd420a01ec082cea")
    assert '"Boatspeed (Knots)"' in out
    assert '"navigation.speedThroughWater"' in out


def test_find_unknown_codes():
    out = _run("tools/find_unknown_codes.py", "captures/big.txt")
    assert "Broadcast frames:" in out


def test_validate_schema():
    _run("tools/validate_schema.py")
