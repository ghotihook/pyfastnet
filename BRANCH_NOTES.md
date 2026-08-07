# `experiment/schema-interpreter` — working notes

Branch status as of this writing: **not merged to `main`**. Plan is to merge
soon, but treat the items under "Before merging to main" below as real gates,
not just a to-do wishlist — see the "Honest assessment" section for why.

## What this branch does

Replaces pyfastnet's hand-written decoder (`mappings.py` + `decode_fastnet.py`
+ `signalk_map.py`, ~1090 lines across 3 files) with:

- `fastnet_decoder/data/fastnet.json` — the protocol as data: channel names,
  the 8 format-byte "templates" (byte layout + scale rule), segment-display
  lookup tables, and the Signal K path/unit/transform mapping per channel.
- `fastnet_decoder/interpreter.py` (~640 lines incl. heavy docs) — one
  small, generic, schema-driven decode engine. No channel names or
  per-channel logic are hardcoded; it dispatches on the format byte's low
  nibble to one of ~8 generic ops (`scaledInt`, `layoutValue`, etc.).
- `fastnet_decoder/data/README.md` — how to read/edit the schema file.
- `docs/protocol.md` — a standalone, language-agnostic description of the
  FastNet wire protocol itself (frame envelope, checksum, format templates,
  segment-display encoding, the two non-channel message types, known gaps).
  Didn't exist before; the closest prior thing was scattered code comments.

`fastnet_decoder/frame_buffer.py` and `utils.py` are essentially unchanged
(only import lines updated) — envelope parsing and checksum logic are
protocol-fixed, not schema-driven.

### Why

Original motivation: explore a canboat-style approach so other-language
(Rust/JS/C) implementations become plausible later. Landed on a generic
runtime interpreter instead of full codegen, specifically because the
protocol is still being actively reverse-engineered (new channels, new
segment codes still being found) — a generic interpreter means a newly
identified channel is a data edit, with zero code changes required in any
language, as long as it fits an existing format template.

### Verification performed (all before/during cutover, not just after)

- 18,645 real-frame decode + Signal K projection comparisons against the
  original hand-written decoder, across every capture under `temp/*.txt`.
- Full existing test suite (147 tests) passes with zero assertion changes
  (only import-path fixes, since several tests imported internal modules
  directly rather than the public API).
- `tests/golden/v2_baseline.json` (hash + per-channel-decode baseline) and
  `docs/channel_map.md` both regenerate byte-identical.
- Built an actual wheel, installed into a clean venv, imported from outside
  the repo — confirms `data/fastnet.json` packages correctly and there's no
  new runtime dependency.
- Every function's docstring `Example:` (35 total) was independently
  executed and checked against real output before committing — caught one
  fabricated example (`from_address` guessed wrong) in the process.

## Honest assessment — read this before merging

The correctness of this migration is solid. The *decision* to fully replace
the production decoder now, rather than a lower-risk alternative, is less
settled than the execution quality suggests. Specifically:

**The inconsistency**: early in this work we deliberately avoided building
multi-language codegen *because* the protocol is still actively changing —
locking in an abstraction before the domain model stabilizes means paying a
coordination cost on every future discovery that doesn't fit. We didn't
apply that same caution to retiring the flexible hand-written Python
decoder, which carries the identical risk: if a future discovery needs a
9th format `op` the current vocabulary doesn't cover, that's now a schema
change *and* an `interpreter.py` change, coordinated — more friction than
editing a Python `elif` chain used to be.

**The two arguments that justified going ahead anyway, and how solid they
really were:**
1. "Editing JSON is about as fast as editing a Python dict" — an
   assumption, never actually tested against a real reverse-engineering
   session. Still untested as of this writing.
2. "Keeping two parallel implementations risks drift — we found a bug from
   exactly that" — the "bug" (two autopilot tables,
   `AUTOPILOT_MODE_BY_LOW` vs `_AP_MODE_BY_LOW`, with different string
   values) turned out, on closer inspection, not to be a bug at all — the
   two tables were supposed to hold different vocabularies (human display
   text vs. Signal K enum). This was corrected mid-session but means the
   strongest concrete evidence for "parallel implementations are
   dangerous" was weaker than it was treated as at decision time.

An available, lower-risk alternative (extract a schema for reference/future
porting use, but keep the hand-written Python decoder authoritative and
fast to iterate on, only flipping to "schema is canonical" once the format
template vocabulary has demonstrably stopped changing) was proposed and
then bypassed in favor of the fuller replacement done here.

This isn't a claim that the migration was wrong — it's fully reversible
(unmerged, `main` still has the original files in git history) and
correctness is thoroughly proven. It's a flag that the *timing* of "commit
to one source of truth" may have been earlier than the project's current
phase (active RE, not yet stable) actually warranted.

## Before merging to main

These are the open items that would actually test whether this was the
right call, not just whether it's correct:

1. **Do a real RE session on this branch** — find or add a genuinely new
   channel/segment code to `fastnet.json` the way you'd normally work, and
   see if it's actually as fast/pleasant as hoped. This is the single most
   important unverified claim.
2. **Check `fastnet2ip`'s imports.** If it imports from
   `fastnet_decoder.mappings`/`.decode_fastnet`/`.signalk_map` directly
   (not just the public `fastnet_decoder` top-level API), this migration
   breaks it the next time the pin is bumped. Never checked.
3. **Spike a tiny second-language reader** — even just one channel decoded
   in Rust or JS against `fastnet.json`, no polish — to convert "should be
   portable" into "is portable."
4. **Add minimal schema validation** (a JSON Schema check, or even just a
   `--check`-style sanity script) so a malformed `fastnet.json` edit fails
   loudly at edit time rather than surfacing as a runtime `KeyError` later.
   There's currently no CI and no validation step at all.

## Picking this back up

```
git checkout experiment/schema-interpreter
.venv/bin/pytest tests/ -v                       # should be 154 passed
.venv/bin/python tests/golden/generate_baseline.py   # diff should be empty (or version-string only)
```

Key files: `fastnet_decoder/interpreter.py` (start with its module
docstring), `fastnet_decoder/data/fastnet.json` +
`fastnet_decoder/data/README.md`, `docs/protocol.md`.
