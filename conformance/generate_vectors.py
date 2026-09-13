#!/usr/bin/env python3
"""Regenerate conformance/vectors.json - the expected output of a FastNet decoder.

The vectors come from running this library - the reference implementation - over
the recorded captures in captures/. They let an implementation in any language
check itself without running Python. conformance/README.md explains the format.

Two parts:

  streams - for each capture, the exact sequence of frames the framing layer must
            find in the raw bytes (a count, a SHA-256, and the first few frames).
  frames  - individual frames with their expected complete decode and Signal K
            projection. Picked greedily from every distinct captured frame until
            every combination of channel, format byte, layout, sign, command,
            address and emitted path seen in the captures is covered; then a few
            synthetic frames for behaviour no capture contains.

Deterministic: re-running on unchanged code and data reproduces the file exactly,
apart from meta.pyfastnet_version. Only regenerate when an output change is
intended, and say why in the commit - tests/test_conformance.py fails whenever the
committed file and the library disagree.

    python conformance/generate_vectors.py
"""
import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))   # always the checkout's own library

from fastnet_decoder import (FrameBuffer, __version__, decode_ascii_frame, decode_frame,
                             decode_light_frame, project, set_log_level)
from fastnet_decoder.interpreter import (ADDRESS_LOOKUP, CHANNEL_LOOKUP, SCHEMA,
                                         decode_channel_value)
from fastnet_decoder.utils import calculate_checksum

SCHEMA_PATH = REPO_ROOT / "fastnet_decoder" / "data" / "fastnet.json"
CAPTURES = sorted((REPO_ROOT / "captures").glob("*.txt"))
OUT = Path(__file__).resolve().parent / "vectors.json"

FIRST_FRAMES_SHOWN = 3

_COMMAND_NAMES = {int(key, 16): name for key, name in SCHEMA["lookups"]["commands"].items()}
_FORMAT_SIZES = {int(key, 16): size for key, size in SCHEMA["formatSizeMap"].items()}
_DECODERS = {"Broadcast": decode_frame, "LatLon": decode_ascii_frame,
             "Light Intensity": decode_light_frame}


class _RecordingFrameBuffer(FrameBuffer):
    """The reference FrameBuffer, recording each frame it hands on for decoding:
    every checksum-valid frame whose command is not in ignoredCommands."""

    def __init__(self):
        super().__init__()
        self.frames = []

    def decode_and_queue_frame(self, frame, command_name):
        self.frames.append(bytes(frame))


def capture_frames(path):
    recorder = _RecordingFrameBuffer()
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            recorder.add_to_buffer(bytes.fromhex(line))
            recorder.get_complete_frames()
    return recorder.frames


def reference_output(frame):
    """(decode, signalk) exactly as the reference produces them - both None for a
    command pyfastnet does not decode."""
    decoder = _DECODERS.get(_COMMAND_NAMES.get(frame[3]))
    if decoder is None:
        return None, None
    decoded = decoder(frame)
    return decoded, project(decoded)


def _sign(value):
    if value is None:
        return None
    return (value > 0) - (value < 0)


def coverage_features(frame, decoded, signalk):
    """Every behaviour this frame exercises, as hashable tuples. A frame earns a
    place in the vectors only by exercising something no chosen frame has yet."""
    features = {("command", frame[3]), ("to", frame[0]), ("from", frame[1])}
    if decoded is None:
        return features

    if _COMMAND_NAMES.get(frame[3]) == "Broadcast":
        body = frame[5:-1]
        index = 0
        while index + 1 < len(body):
            channel_id, format_byte = body[index], body[index + 1]
            size = _FORMAT_SIZES.get(format_byte & 0x0F, 0)
            data_bytes = body[index + 2:index + 2 + size]
            index += 2 + size
            record = decode_channel_value(channel_id, format_byte, data_bytes)
            if record is None:
                features.add(("undecodable", channel_id, format_byte))
                continue
            text = record["display_text"] or ""
            features.add(("record", channel_id, format_byte, record["layout"],
                          _sign(record["value"]), "TBC" in text, "day" in text))

    if _COMMAND_NAMES.get(frame[3]) == "LatLon":
        # Position text comes in more than one layout (digits vary, shape doesn't);
        # cover each shape.
        for entry in decoded.get("values", {}).values():
            features.add(("latlon-text", re.sub(r"\d", "9", entry["display_text"] or "")))

    for path, value in (signalk or {}).items():
        features.add(("path", path, type(value).__name__))
    return features


def choose_frames(candidates):
    """Greedy set cover: repeatedly take the frame adding the most uncovered
    features (the earliest one on a tie), until nothing new remains."""
    covered, chosen = set(), []
    while True:
        best = max(candidates, key=lambda candidate: len(candidate["features"] - covered))
        gain = best["features"] - covered
        if not gain:
            return sorted(chosen, key=lambda candidate: candidate["order"])
        covered |= gain
        chosen.append(best)


def _frame(body, command, to_address=0xFF, from_address=0x01):
    header = bytes([to_address, from_address, len(body), command])
    return header + bytes([calculate_checksum(header)]) + body + bytes([calculate_checksum(body)])


def synthetic_frames():
    """(frame, note) pairs for behaviour that no capture happens to contain."""
    unnamed_channel = min(set(range(256)) - set(CHANNEL_LOOKUP))
    unnamed_address = min(set(range(256)) - set(ADDRESS_LOOKUP))
    return [
        (_frame(bytes([0x41, 0x00, 0x01, 0x02, 0x03, 0x04, 0x8D, 0x81, 0x05, 0x26]), 0x01),
         "A record in format 0x00 (size known, layout unknown) decodes to null and is "
         "skipped by the projection; the rest of the frame still decodes."),
        (_frame(bytes([unnamed_channel, 0x01, 0x01, 0x2C]), 0x01, from_address=unnamed_address),
         "A channel id and an address the schema has no name for: placeholder names, "
         "and the value is emitted under bandg.unknown.0x<id>."),
        (bytes.fromhex("ff5001c9e701ff"),
         "Light Intensity (backlight), captured live but not present in captures/: "
         "decoded, but it has no Signal K path, so the projection is empty."),
    ]


def _stream_sha256(frames):
    joined = "\n".join(frame.hex() for frame in frames)
    return hashlib.sha256(joined.encode("ascii")).hexdigest()


def build():
    streams, candidates, seen = [], [], set()

    for path in CAPTURES:
        frames = capture_frames(path)
        source = path.relative_to(REPO_ROOT).as_posix()
        by_command = {}
        for frame in frames:
            command = f"0x{frame[3]:02X}"
            by_command[command] = by_command.get(command, 0) + 1
        streams.append({
            "capture": source,
            "frames": len(frames),
            "frames_sha256": _stream_sha256(frames),
            "first_frames": [frame.hex() for frame in frames[:FIRST_FRAMES_SHOWN]],
            "frames_by_command": dict(sorted(by_command.items())),
        })

        for frame in frames:
            if frame in seen:
                continue
            seen.add(frame)
            decoded, signalk = reference_output(frame)
            candidates.append({"order": len(candidates), "source": source, "frame": frame,
                               "decode": decoded, "signalk": signalk,
                               "features": coverage_features(frame, decoded, signalk)})

    vectors = []
    for candidate in choose_frames(candidates):
        vectors.append({"source": candidate["source"], "frame": candidate["frame"].hex(),
                        "decode": candidate["decode"], "signalk": candidate["signalk"]})
    for frame, note in synthetic_frames():
        decoded, signalk = reference_output(frame)
        vectors.append({"source": "synthetic", "note": note, "frame": frame.hex(),
                        "decode": decoded, "signalk": signalk})

    frames = [dict({"id": f"f{number:03d}"}, **vector) for number, vector in enumerate(vectors, 1)]

    # Line endings normalised, so a CRLF checkout hashes the same schema identically.
    schema_bytes = SCHEMA_PATH.read_bytes().replace(b"\r\n", b"\n")
    return {
        "meta": {
            "description": "Expected output of a FastNet decoder, produced by pyfastnet, "
                           "the reference implementation. See conformance/README.md.",
            "pyfastnet_version": __version__,
            "schema": "fastnet_decoder/data/fastnet.json",
            "schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
            "battery_id": "house",
        },
        "streams": streams,
        "frames": frames,
    }


def main():
    set_log_level("CRITICAL")
    doc = build()
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO_ROOT)}  "
          f"({len(doc['streams'])} streams, {len(doc['frames'])} frames)")


if __name__ == "__main__":
    main()
