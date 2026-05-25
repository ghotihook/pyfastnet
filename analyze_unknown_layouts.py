#!/usr/bin/env python3
"""
Replay all temp/*.txt raw log files through the FastNet decoder and report
every occurrence where a segment lookup returns "?" (unknown layout/display code).

Covers:
  SEGMENT_A unknowns — formats 0x03, 0x07, 0x08  (layout indicator byte)
  SEGMENT_B unknowns — format  0x06              (7-segment display bytes)
  Unsupported format types                        (no decoder case)
"""

import sys
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).parent))

from fastnet_decoder.utils import calculate_checksum
from fastnet_decoder.mappings import (
    FORMAT_SIZE_MAP, CHANNEL_LOOKUP, SEGMENT_A, SEGMENT_B,
    COMMAND_LOOKUP, IGNORED_COMMANDS,
)
from fastnet_decoder.decode_fastnet import decode_format_and_data

TEMP_DIR = Path(__file__).parent / "temp"

KNOWN_FORMAT_BITS = {0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x0A}


def extract_frames(data: bytearray):
    """Yield validated raw FastNet frames, skipping LatLon and ignored commands."""
    buf = bytearray(data)
    while len(buf) >= 6:
        body_size = buf[2]
        command   = buf[3]
        full_len  = 5 + body_size + 1

        if len(buf) < full_len:
            break

        frame          = bytes(buf[:full_len])
        body           = frame[5:-1]
        body_checksum  = frame[-1]

        if calculate_checksum(buf[:4]) != buf[4]:
            buf = buf[1:]
            continue
        if calculate_checksum(body) != body_checksum:
            buf = buf[1:]
            continue

        buf = buf[full_len:]

        cmd_name = COMMAND_LOOKUP.get(command, f"Unknown(0x{command:02X})")
        if cmd_name in IGNORED_COMMANDS or cmd_name == "LatLon":
            continue

        yield frame


def walk_channels(frame: bytes):
    """Yield (channel_id, format_byte, data_bytes) for every channel in a frame body."""
    body  = frame[5:-1]
    index = 0
    while index + 1 < len(body):
        channel_id  = body[index]
        format_byte = body[index + 1]
        index      += 2
        data_len    = FORMAT_SIZE_MAP.get(format_byte & 0x0F, 0)
        if index + data_len > len(body):
            break
        yield channel_id, format_byte, bytes(body[index : index + data_len])
        index += data_len


def seg_code_for(format_bits: int, data_bytes: bytes):
    """Return the SEGMENT_A lookup byte for formats 0x03 / 0x07 / 0x08."""
    if format_bits == 0x03 and data_bytes:
        return data_bytes[0]
    if format_bits == 0x07 and len(data_bytes) > 1:
        return data_bytes[1]
    if format_bits == 0x08 and data_bytes:
        return (data_bytes[0] >> 1) & 0x7F
    return None


def ch_name(channel_id: int) -> str:
    return CHANNEL_LOOKUP.get(channel_id, f"Unknown(0x{channel_id:02X})")


def main():
    seg_a_counts   = Counter()   # (channel_id, format_bits, seg_code) → count
    seg_b_counts   = Counter()   # (channel_id, byte_val)              → count
    unsup_counts   = Counter()   # (channel_id, format_bits)           → count
    examples       = defaultdict(list)

    txt_files     = sorted(TEMP_DIR.glob("*.txt"))
    total_frames  = 0
    total_channels = 0

    for txt_file in txt_files:
        raw = bytearray()
        with open(txt_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw.extend(bytes.fromhex(line))
                except ValueError:
                    continue

        for frame in extract_frames(raw):
            total_frames += 1
            for channel_id, format_byte, data_bytes in walk_channels(frame):
                total_channels += 1
                format_bits = format_byte & 0x0F

                if format_bits not in KNOWN_FORMAT_BITS:
                    key = (channel_id, format_bits)
                    unsup_counts[key] += 1
                    if len(examples[("unsup",) + key]) < 3:
                        examples[("unsup",) + key].append(data_bytes.hex() or "(empty)")
                    continue

                result = decode_format_and_data(channel_id, format_byte, data_bytes)
                if result is None:
                    continue

                # SEGMENT_A miss
                if result.get("layout") == "TBC":
                    seg_code = seg_code_for(format_bits, data_bytes)
                    key = (channel_id, format_bits, seg_code)
                    seg_a_counts[key] += 1
                    if len(examples[("A",) + key]) < 3:
                        examples[("A",) + key].append((data_bytes.hex(), result.get("value")))

                # SEGMENT_B miss (format 0x06 only)
                if format_bits == 0x06 and "TBC" in (result.get("display_text") or ""):
                    for b in data_bytes:
                        if b not in SEGMENT_B:
                            key = (channel_id, b)
                            seg_b_counts[key] += 1
                            if len(examples[("B",) + key]) < 3:
                                examples[("B",) + key].append(data_bytes.hex())

    # ── Report ──────────────────────────────────────────────────────────────

    print(f"\nFiles: {len(txt_files)}  |  Frames: {total_frames}  |  Channels: {total_channels}\n")

    if seg_a_counts:
        print("=" * 72)
        print("SEGMENT_A UNKNOWNS  —  layout '?'  (formats 0x03 / 0x07 / 0x08)")
        print("=" * 72)
        for (cid, fmt, sc), count in seg_a_counts.most_common():
            print(f"\n  Channel : 0x{cid:02X}  {ch_name(cid)}")
            print(f"  Format  : 0x{fmt:02X}")
            print(f"  SegCode : 0x{sc:02X}")
            print(f"  Count   : {count}")
            for raw_hex, val in examples[("A", cid, fmt, sc)]:
                print(f"  Example : [{raw_hex}]  →  numeric={val}")

    if seg_b_counts:
        print()
        print("=" * 72)
        print("SEGMENT_B UNKNOWNS  —  display '?'  (format 0x06)")
        print("=" * 72)
        for (cid, bv), count in seg_b_counts.most_common():
            print(f"\n  Channel : 0x{cid:02X}  {ch_name(cid)}")
            print(f"  Byte    : 0x{bv:02X}")
            print(f"  Count   : {count}")
            for raw_hex in examples[("B", cid, bv)]:
                print(f"  Example : [{raw_hex}]")

    if unsup_counts:
        print()
        print("=" * 72)
        print("UNSUPPORTED FORMAT TYPES  —  no decoder case")
        print("=" * 72)
        for (cid, fmt), count in unsup_counts.most_common():
            print(f"\n  Channel : 0x{cid:02X}  {ch_name(cid)}")
            print(f"  Format  : 0x{fmt:02X}")
            print(f"  Count   : {count}")
            for raw_hex in examples[("unsup", cid, fmt)]:
                print(f"  Example : [{raw_hex}]")

    if not seg_a_counts and not seg_b_counts and not unsup_counts:
        print("No unknown layout codes found — all segment lookups resolved.")


if __name__ == "__main__":
    main()
