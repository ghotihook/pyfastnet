"""Regenerate docs/channel_map.md from fastnet_decoder.channel_map().

The code is the source of truth; this just renders it. Run from repo root:
    python docs/generate_channel_map.py
"""
from pathlib import Path
from fastnet_decoder import channel_map, __version__

OUT = Path(__file__).resolve().parent / "channel_map.md"

def main():
    rows = channel_map()
    lines = [
        "# B&G channel → name → Signal K path (master reference)",
        "",
        f"**Generated** from `fastnet_decoder.channel_map()` (pyfastnet {__version__}). "
        "Do not hand-edit — regenerate with `python docs/generate_channel_map.py`.",
        "",
        "This is the authoritative map, derived from the projection tables so it stays "
        "in step with what `project()` actually emits. `kind`: *standard* = SK path, "
        "*vendor* = `bandg.*`, *routed(M/T)* = Magnetic|True chosen from layout, "
        "*collapsed* = redundant variant folded onto a sibling, *drop* = not emitted.",
        "",
        "> Position (`navigation.position`) and backlight come from command frames "
        "(LatLon / Light Intensity), not channel ids, so they are not in this table.",
        "",
        "| ID | B&G name | Signal K path | Unit | Kind |",
        "|----|----------|---------------|------|------|",
    ]
    for cid, r in rows.items():
        lines.append(f"| 0x{cid:02X} | {r['name']} | `{r['path']}` | {r['unit']} | {r['kind']} |")
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.name}  ({len(rows)} channels)")

if __name__ == "__main__":
    main()
