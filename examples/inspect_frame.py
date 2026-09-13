#!/usr/bin/env python3
"""Decode one FastNet frame and show both of pyfastnet's views of it.

Give a complete frame as hex - header, body and both checksums, as it appears in a
capture or in pyfastnet's DEBUG log - to see the complete decode and the Signal K
projection the reference implementation produces. Useful when reverse-engineering a
channel, and when checking another implementation against this one.

    python examples/inspect_frame.py ff010a01f54192f9dd420a01ec082cea
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))   # use this checkout's library, installed or not

from fastnet_decoder import decode_ascii_frame, decode_frame, decode_light_frame, project
from fastnet_decoder.interpreter import COMMAND_LOOKUP
from fastnet_decoder.utils import calculate_checksum

DECODERS = {"Broadcast": decode_frame, "LatLon": decode_ascii_frame,
            "Light Intensity": decode_light_frame}


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    frame = bytes.fromhex(sys.argv[1])

    if len(frame) < 6 or len(frame) != 6 + frame[2]:
        sys.exit(f"Not one complete frame: {len(frame)} bytes given, but the header's "
                 f"body_size implies {6 + frame[2] if len(frame) > 2 else 'at least 6'}.")
    if calculate_checksum(frame[:4]) != frame[4] or calculate_checksum(frame[5:-1]) != frame[-1]:
        print("Warning: a checksum does not match - FrameBuffer would discard this frame.\n")

    command = COMMAND_LOOKUP.get(frame[3], f"Unknown (0x{frame[3]:02X})")
    decoder = DECODERS.get(command)
    if decoder is None:
        print(f"Command {command}: pyfastnet does not decode this frame type. "
              "FrameBuffer only probes it, in the DEBUG log.")
        return

    decoded = decoder(frame)
    print("Complete decode  (decode_frame(), or FrameBuffer(project=False))")
    print(json.dumps(decoded, indent=2, ensure_ascii=False))
    print("\nSignal K projection  (project(), or FrameBuffer() by default)")
    print(json.dumps(project(decoded), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
