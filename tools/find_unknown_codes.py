#!/usr/bin/env python3
"""Find the bytes on the bus that fastnet.json can't describe yet.

Replays every capture in captures/ (or the files you name) and reports each place a
lookup comes back unidentified:

  segmentA misses  - a layout/indicator code that decoded as "TBC" (any format
                     whose template reads a layout byte)
  segmentB misses  - a 7-segment glyph byte that decoded as "TBC" (the
                     segmentDisplay format)
  unsupported      - a record whose format nibble has no decodable template

This is the reverse-engineering to-do list: every hit is a real byte from a real
instrument that the schema doesn't explain. Once you know what one means, add it to
fastnet_decoder/data/fastnet.json (see the README next to it) and it disappears from
this report.

    python tools/find_unknown_codes.py                  # every bundled capture
    python tools/find_unknown_codes.py my_capture.txt   # your own recording
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))   # always the checkout's own library

from fastnet_decoder import FrameBuffer
from fastnet_decoder.interpreter import CHANNEL_LOOKUP, SCHEMA, decode_channel_value

EXAMPLES_KEPT = 3

# Everything below is read from the schema, so this report can't disagree with it.
_FORMAT_SIZES = {int(key, 16): size for key, size in SCHEMA["formatSizeMap"].items()}
_TEMPLATES = {int(key, 16): template for key, template in SCHEMA["formatTemplates"].items()}


class _BroadcastCollector(FrameBuffer):
    """The library's own framing, keeping each valid Broadcast frame instead of
    decoding it."""

    def __init__(self):
        super().__init__()
        self.broadcast_frames = []

    def decode_and_queue_frame(self, frame, command_name):
        if command_name == "Broadcast":
            self.broadcast_frames.append(bytes(frame))


def read_capture(path):
    """Every valid Broadcast frame in a capture file (one line of hex per burst)."""
    collector = _BroadcastCollector()
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line:
            collector.add_to_buffer(bytes.fromhex(line))
            collector.get_complete_frames()
    return collector.broadcast_frames


def walk_records(frame):
    """Yield (channel_id, format_byte, data_bytes) for each record in a frame body."""
    body = frame[5:-1]
    index = 0
    while index + 1 < len(body):
        channel_id, format_byte = body[index], body[index + 1]
        index += 2
        size = _FORMAT_SIZES.get(format_byte & 0x0F, 0)
        if index + size > len(body):
            return
        yield channel_id, format_byte, body[index:index + size]
        index += size


def layout_code(template, data_bytes):
    """The raw segmentA code a template reads, or None if it reads no layout."""
    if "layoutByte" in template:
        return data_bytes[template["layoutByte"]]
    if "layoutBits" in template:
        spec = template["layoutBits"]
        return (data_bytes[spec["byte"]] & int(spec["mask"], 16)) >> spec["shiftRight"]
    return None


def channel_name(channel_id):
    return CHANNEL_LOOKUP.get(channel_id, f"Unknown (0x{channel_id:02X})")


def _keep(examples, key, text):
    if len(examples[key]) < EXAMPLES_KEPT:
        examples[key].append(text)


def main():
    paths = [Path(arg) for arg in sys.argv[1:]] or sorted((REPO_ROOT / "captures").glob("*.txt"))

    segment_a = Counter()     # (channel_id, format nibble, code) -> count
    segment_b = Counter()     # (channel_id, glyph byte)          -> count
    unsupported = Counter()   # (channel_id, format nibble)       -> count
    examples = defaultdict(list)
    frame_count = record_count = 0

    for path in paths:
        for frame in read_capture(path):
            frame_count += 1
            for channel_id, format_byte, data_bytes in walk_records(frame):
                record_count += 1
                nibble = format_byte & 0x0F
                template = _TEMPLATES.get(nibble)

                if template is None or template["op"] == "unsupported":
                    key = (channel_id, nibble)
                    unsupported[key] += 1
                    _keep(examples, ("unsupported",) + key, f"[{data_bytes.hex() or 'no data'}]")
                    continue

                record = decode_channel_value(channel_id, format_byte, data_bytes)
                if record is None:
                    continue

                if record["layout"] == "TBC":
                    key = (channel_id, nibble, layout_code(template, data_bytes))
                    segment_a[key] += 1
                    _keep(examples, ("A",) + key, f"[{data_bytes.hex()}] -> value {record['value']}")

                if template["op"] == "segmentDisplay":
                    known = {int(k, 16) for k in SCHEMA["lookups"][template["lookup"]]}
                    for glyph in data_bytes:
                        if glyph not in known:
                            key = (channel_id, glyph)
                            segment_b[key] += 1
                            _keep(examples, ("B",) + key, f"[{data_bytes.hex()}]")

    print(f"\nFiles: {len(paths)}  |  Broadcast frames: {frame_count}  |  Records: {record_count}\n")

    if segment_a:
        print("=" * 72)
        print("segmentA UNKNOWNS  -  layout decoded as 'TBC'")
        print("=" * 72)
        for (channel_id, nibble, code), count in segment_a.most_common():
            print(f"\n  Channel : 0x{channel_id:02X}  {channel_name(channel_id)}")
            print(f"  Format  : 0x{nibble:02X}")
            print(f"  Code    : 0x{code:02X}")
            print(f"  Count   : {count}")
            for text in examples[("A", channel_id, nibble, code)]:
                print(f"  Example : {text}")

    if segment_b:
        print("\n" + "=" * 72)
        print("segmentB UNKNOWNS  -  7-segment glyph decoded as 'TBC'")
        print("=" * 72)
        for (channel_id, glyph), count in segment_b.most_common():
            print(f"\n  Channel : 0x{channel_id:02X}  {channel_name(channel_id)}")
            print(f"  Byte    : 0x{glyph:02X}")
            print(f"  Count   : {count}")
            for text in examples[("B", channel_id, glyph)]:
                print(f"  Example : {text}")

    if unsupported:
        print("\n" + "=" * 72)
        print("UNSUPPORTED FORMATS  -  no decodable template for this nibble")
        print("=" * 72)
        for (channel_id, nibble), count in unsupported.most_common():
            print(f"\n  Channel : 0x{channel_id:02X}  {channel_name(channel_id)}")
            print(f"  Format  : 0x{nibble:02X}")
            print(f"  Count   : {count}")
            for text in examples[("unsupported", channel_id, nibble)]:
                print(f"  Example : {text}")

    if not (segment_a or segment_b or unsupported):
        print("Nothing unidentified - every lookup in these captures resolved.")


if __name__ == "__main__":
    main()
