"""Regenerate the v2 golden baseline: a compact, deterministic snapshot of the current
(pre-v3) decode of every bundled capture.

Two parts:
  * per-file ``decode_sha256`` over the full ordered frame decode — detects ANY change
    to the complete decoder through the v3 refactor (the decoder stays complete; its
    value/display_text/layout output must not drift).
  * per-channel ``distinct`` decode outcomes (value, display_text, layout + count) —
    the reference the v3 projection ({signalk_path: SI_value}) must derive from.

Run from the repo root:  python tests/golden/generate_baseline.py
"""
import hashlib
import json
import logging
from collections import Counter, defaultdict
from pathlib import Path

logging.getLogger("pyfastnet").setLevel(logging.CRITICAL)

from fastnet_decoder import __version__, FrameBuffer

REPO = Path(__file__).resolve().parents[2]
CAPTURES = sorted((REPO / "temp").glob("*.txt"))
OUT = Path(__file__).resolve().parent / "v2_baseline.json"


def decode_file(path):
    fb = FrameBuffer()
    frames = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            fb.add_to_buffer(bytes.fromhex(line))
        except ValueError:
            continue
        fb.get_complete_frames()
        while not fb.frame_queue.empty():
            fr = fb.frame_queue.get()
            frames.append(fr)
    return frames


def main():
    per_file = {}
    channel_distinct = defaultdict(Counter)   # name -> Counter[(value, display, layout)]
    channel_total = Counter()

    for cap in CAPTURES:
        frames = decode_file(cap)
        blob = json.dumps(frames, sort_keys=True, ensure_ascii=False)
        per_file[cap.name] = {
            "frame_count": len(frames),
            "decode_sha256": hashlib.sha256(blob.encode()).hexdigest(),
        }
        for fr in frames:
            for name, v in fr.get("values", {}).items():
                key = (v.get("value"), v.get("display_text"), v.get("layout"))
                channel_distinct[name][key] += 1
                channel_total[name] += 1

    channels = {}
    for name in sorted(channel_distinct):
        distinct = [
            {"value": val, "display_text": disp, "layout": lay, "count": n}
            for (val, disp, lay), n in sorted(
                channel_distinct[name].items(),
                key=lambda kv: (str(kv[0][0]), str(kv[0][1]), str(kv[0][2])),
            )
        ]
        channels[name] = {"occurrences": channel_total[name], "distinct": distinct}

    doc = {
        "meta": {
            "pyfastnet_version": __version__,
            "note": "v2 complete-decode baseline. decode_sha256 guards the decoder "
                    "through refactor; channels.distinct is the reference the v3 "
                    "{path: value} projection must derive from.",
        },
        "files": per_file,
        "channels": channels,
    }
    OUT.write_text(json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"wrote {OUT.relative_to(REPO)}  "
          f"({len(per_file)} captures, {len(channels)} channels, "
          f"{sum(len(c['distinct']) for c in channels.values())} distinct decodes)")


if __name__ == "__main__":
    main()
