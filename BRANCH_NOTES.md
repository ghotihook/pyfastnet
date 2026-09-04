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

---

# Update — 2026-09-05: decision reached, **go schema**

The sections above are preserved as written. This section records what changed
after a full comparative analysis of `main` vs this branch. Where the two
conflict, this section is current.

## Verdict

**Merge this branch.** Not yet executed — the branch is still unmerged.

Agreed path: schema validator -> merge to main -> bump to **3.2.0** (externally
nothing changes, but the internals and the new `data/` payload warrant a minor,
not a patch) -> run `fastnet2ip` against merged main **before** publishing to PyPI.

## What was measured

Both implementations were run over all eight captures in `temp/`:

- **Output is byte-identical.** 9,322 frames — every decode, every Signal K
  projection, the full `channel_map()`, and `unit_for()` for every emitted path
  compare equal. Not "tests pass"; the actual decode products.
- **Public API is character-for-character identical** (same nine exports).
- **Performance difference is irrelevant.** main 108ms vs branch 124ms best-of-7
  over the corpus (~11.6 vs ~13.3 us/frame); cold import 31 vs 32ms. FastNet
  runs at a few hundred frames/sec.
- **Executable Python drops 34%** (783 -> 515 lines). The "1148 replaces 1090"
  framing is misleading — 359 of the new lines are docstrings that didn't exist.
- **Schema fit is excellent.** 113 of 114 channels are pure declarative data
  (58 `scale`, 32 no-transform, 15 `identity`, 6 `drop`, 2 `affine`). Only
  autopilot `0xB5` needs a bespoke escape hatch.

## Gate status (supersedes "Before merging to main" above)

1. **Real RE session — REFRAMED.** The original gate tests the wrong workflow.
   Git history of the old files: **38 commits touched decode logic vs 10
   table-only**, and 29 modified `decode_format_and_data` itself. The real work
   here has always been sign conventions, layout semantics and format
   corrections — not adding channels. The sharper gate is: *take a real sign or
   layout bug and fix it end-to-end through the schema.* Still open, no longer
   blocking.
2. **`fastnet2ip` imports — CLEARED.** It imports only the public top-level API
   (`FrameBuffer`, `set_log_level`, `unit_for`, `logger`), never the deleted
   internal modules. This migration will not break it.
3. **Second-language spike — NOT A GATE.** It proves nothing about whether the
   *Python* library should ship this way. Do it whenever it's interesting.
4. **Schema validation — STILL THE ONE REAL GATE.** This is the single thing the
   migration genuinely made worse: a bad edit to a Python dict was at least
   syntax-checked at import; a bad `fastnet.json` edit surfaces as a runtime
   `KeyError` in a library `fastnet2ip` depends on. Close this before merging.

## Why the decision went this way

Not ergonomics — the churn finding above actually argues the *common* change got
marginally harder. That cost is accepted knowingly, because it is small per
occurrence.

The deciding argument is conceptual: **FastNet is a fixed external artifact being
discovered, not a system being designed.** B&G defined it decades ago and burned
it into instruments. For a discovered constant, the right primary artifact is a
*description* of the thing; code that embodies protocol knowledge is the wrong
shape. Portability to other languages is a free consequence of a correct
description, not the justification for one.

It also puts the protocol where the maintainer's expertise applies: whether
heel-to-port is negative is a sailing question, checkable against an instrument,
not a Python question buried in an `elif` branch.

The "premature commitment" worry in the Honest Assessment above is defused by
reversibility: main's files are in git history, the API is identical, and the
schema is proven complete because it reproduces the entire corpus exactly.

## A gap this analysis found (not a merge blocker)

Cross-referencing every captured frame in `tests/` against the schema:

```
channels with a real-frame test    : 41 of 114  (36%)
channels with NO evidence anywhere : 73
```

Most of the 73 are **unexercised, not neglected** — waypoint/route channels,
`Linear 1`-`16`, `Remote 0`-`9`, barometric pressure, air temperature: things
the capture boat never produced. But in the schema all 114 look identical, so a
claim confirmed against a live display is indistinguishable from a guess. That
invisibility is what let the 0x07 MSB bug live for months.

The fix is **not** hand-written `confidence:` fields in `fastnet.json` — an
asserted flag is inert, goes stale silently, and recreates the
two-sources-of-truth problem this migration exists to eliminate. Provenance
belongs in the test suite, because a test is executable and re-verifies itself.
Confidence should be **derived** and regenerated on demand, the way
`docs/channel_map.md` already is. A `tools/coverage.py` doing exactly that was
proposed and deliberately deferred.

## Housekeeping

Stale worktree at `.claude/worktrees/inspiring-moser-6d13d7` (branch
`claude/inspiring-moser-6d13d7`, 27 commits behind main, last commit "Update
setup.py") looks abandoned and is safe to prune.
