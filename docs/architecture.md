# Why the protocol is data, not code

**Decision, 2026-09-05. Implemented in 3.2.0.**

pyfastnet's decoder used to be hand-written Python: `mappings.py` (channel and lookup
tables), `decode_fastnet.py` (an `elif` chain over format bytes) and `signalk_map.py`
(the projection). Since 3.2.0 the protocol lives in
[`fastnet_decoder/data/fastnet.json`](../fastnet_decoder/data/fastnet.json) — written down
as data — and [`interpreter.py`](../fastnet_decoder/interpreter.py) is a generic engine
that reads it and holds no protocol facts of its own.

This note records why, what it cost, and what remains open. It replaces the
`BRANCH_NOTES.md` working notes kept during the migration.

## The argument

**FastNet is a fixed external artifact being discovered, not a system being designed.**
B&G defined it decades ago and burned it into instruments; nothing about it will change
in response to anything this project does. What the project actually accumulates, capture
by capture, is *knowledge about that artifact*. The library is downstream of that
knowledge.

For a discovered constant, the right primary artifact is a **description** of the thing.
Code that embodies protocol knowledge is the wrong shape, because it encodes facts
implicitly — in which dict a line was put into, which function it points at, what order a
list is in. Two examples from the old implementation:

- A channel's **unit** was stored in a dictionary keyed by Python *function objects*
  (`_UNIT_BY_TF = {_kn: "m/s", ...}`). Answering "what unit is boatspeed in?" meant
  finding which lambda it pointed at, then looking that lambda up in another table. The
  unit was never recorded — it was inferred from which converter someone reached for.
- Depth's **metres → feet → fathoms** priority, a real fact about the instruments, was
  encoded as the order of a Python list.

Both are now stated: `"unit": "m/s"`, and `fallbackPriority: 0/1/2`.

Two consequences follow, and they matter more than the code change:

1. **Derived documents cannot drift.** `channel_map()` and
   [`channel_map.md`](channel_map.md) are generated from the description, so there is
   nothing for them to disagree with. (When this migration landed, a hand-maintained copy
   of those tables in [`signalk-design.md`](signalk-design.md) was found to have
   drifted in twelve places — including one channel documented as mapped that was not.
   Those tables were removed; that file now holds only reasoning.)
2. **Gaps become visible as gaps.** The protocol is now something you can ask questions
   of. That is how "only 41 of 114 channels have real-frame evidence" surfaced, and how
   `°T` was found to be a routing destination no segment code can actually produce.

It also puts the protocol where the maintainer's expertise applies: whether heel-to-port
is negative is a sailing question, checkable against an instrument, not a Python question
buried in an `elif` branch.

Portability to other languages (Rust, JS, C reading the same JSON) is a free consequence
of having a correct description. It was not the justification.

## What it cost

Recorded honestly, because these are real:

- **Sign and layout corrections got marginally harder.** Git history of the old files
  shows 38 commits touching decode logic versus 10 touching tables only, and 29 modifying
  `decode_format_and_data` itself. That — not adding channels — has always been the common
  change here. If such a fix needs a new format `op`, it is now a coordinated edit to both
  the schema and `interpreter.py`, where it used to be one `elif`. Accepted knowingly; the
  cost is small per occurrence.
- **A syntax check was lost.** A malformed Python dict failed at import; a malformed
  `fastnet.json` used to surface only as a runtime `KeyError`, in a library other
  applications depend on. This was measured, not assumed: of eight realistic schema edit
  mistakes run through the normal workflow, **six passed the full test suite silently**.
  Closed by [`tools/validate_schema.py`](../tools/validate_schema.py), which runs in the
  test suite.
- **One more hop to read.** Understanding a channel means reading its entry *and* the `op`
  it names.

## Evidence the migration was safe

- **Byte-identical output.** 9,322 frames across all eight captures — every decode, the
  full Signal K projection, `channel_map()`, and `unit_for()` for every emitted path —
  compare equal to the previous implementation by SHA-256.
- **Unchanged downstream.** Replayed through `fastnet2ip` on both wire formats across all
  eight captures: 23,420 NMEA 0183 sentences and CAN frames identical, once the two fields
  carrying wall-clock time are masked.
- **Public API identical** — the same nine exports.
- **Schema fit.** 113 of 114 channels are pure declarative data (58 `scale`, 32
  no-transform, 15 `identity`, 6 `drop`, 2 `affine`). Only autopilot `0xB5` needs a
  bespoke escape hatch, via `overrides`.
- **Performance irrelevant.** ~11 → ~13 µs/frame. FastNet runs at a few hundred
  frames/sec.

## When this would have been the wrong call

If the protocol were still moving — new byte layouts appearing regularly — then committing
to a fixed vocabulary of eight `op`s would cost on every discovery that didn't fit. The
evidence says it isn't: the vocabulary covered every format nibble in 9,322 captured
frames without strain. The protocol is done moving; the project is still finding it.

The decision is also reversible: the previous implementation is in git history, and the
public API is unchanged.

## Still open

- **Channel evidence coverage.** 41 of 114 channels have a real-frame test; 73 have no
  evidence anywhere. Most are unexercised rather than neglected — waypoint/route channels,
  `Linear 1`–`16`, `Remote 0`–`9` — but in the schema all 114 look alike, so a claim
  confirmed against a live display is indistinguishable from a guess. That invisibility is
  what let the format 0x07 MSB bug live for months. The fix is **not** a hand-written
  `confidence:` field — an asserted flag goes stale silently and recreates the
  two-sources-of-truth problem this migration exists to remove. Confidence should be
  *derived* from the test suite and regenerated on demand, the way `channel_map.md` is. A
  `tools/coverage.py` doing exactly that is proposed and deferred.
- **A real end-to-end schema fix.** Take a genuine sign or layout bug and fix it through
  the schema, to test the claim that the common change is still comfortable. Not blocking.
- **Second-language reader.** A small Rust or JS decoder reading `fastnet.json`, to turn
  "should be portable" into "is portable". Interesting, not a gate.
