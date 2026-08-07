"""channel_map() is the master reference — verify coverage and doc sync."""
import importlib.util
from pathlib import Path

from fastnet_decoder import channel_map
from fastnet_decoder.interpreter import CHANNEL_LOOKUP

DOCS = Path(__file__).resolve().parents[1] / "docs"


def test_covers_every_channel():
    cm = channel_map()
    assert set(cm) == set(CHANNEL_LOOKUP), "channel_map must cover all CHANNEL_LOOKUP ids"
    for cid, r in cm.items():
        assert r["name"] == CHANNEL_LOOKUP[cid]
        assert set(r) == {"name", "path", "unit", "kind"}


def test_doc_is_in_sync():
    # Render via the generator and compare to the committed doc — catches drift.
    spec = importlib.util.spec_from_file_location("gen_cm", DOCS / "generate_channel_map.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    rows = channel_map()
    committed = (DOCS / "channel_map.md").read_text()
    for cid, r in rows.items():
        assert f"| 0x{cid:02X} | {r['name']} | `{r['path']}` |" in committed, \
            f"docs/channel_map.md out of date for 0x{cid:02X} — regenerate it"
