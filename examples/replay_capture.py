#!/usr/bin/env python3
"""Replay a recorded FastNet capture and print the latest value of every path.

No boat needed. This feeds a capture from captures/ through FrameBuffer exactly as a
serial port would, and keeps the most recent value for each Signal K path. That is
the pattern most tools want: each frame carries only a few paths, so a tool holds a
"latest known state" and updates it as frames arrive.

    python examples/replay_capture.py                           # a bundled capture
    python examples/replay_capture.py captures/heel-port.txt    # any capture file
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))   # use this checkout's library, installed or not

from fastnet_decoder import FrameBuffer, unit_for

DEFAULT_CAPTURE = REPO_ROOT / "captures" / "example1_fastnet_data.txt"


def read_capture(path):
    """Yield the raw bytes of a capture file: one line of hex per burst from the bus."""
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line:
            yield bytes.fromhex(line)


def shown(value):
    if value is None:
        return "None"          # channel present on the bus, but no numeric value
    if isinstance(value, dict):  # navigation.position
        return f"{value['latitude']:.5f}, {value['longitude']:.5f}"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)          # an enum string, e.g. steering.autopilot.state


def main():
    capture = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CAPTURE
    fb = FrameBuffer()
    latest = {}                # Signal K path -> most recent value
    frame_count = 0

    for chunk in read_capture(capture):
        fb.add_to_buffer(chunk)        # live: fb.add_to_buffer(serial_port.read(256))
        fb.get_complete_frames()
        while not fb.frame_queue.empty():
            frame = fb.frame_queue.get()
            frame_count += 1
            latest.update(frame["values"])

    print(f"{frame_count} frames from {capture.name}, {len(latest)} paths\n")
    for path in sorted(latest):
        print(f"{path:<58} {shown(latest[path]):>22}  {unit_for(path)}")


if __name__ == "__main__":
    main()
