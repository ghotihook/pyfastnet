# FastNet → Signal K mapping — design record

> **Status:** implemented since pyfastnet 3.0.0. Since 3.2.0 the mapping itself lives in
> [`fastnet_decoder/data/fastnet.json`](../fastnet_decoder/data/fastnet.json) — each channel's
> `signalk` block carries its path, unit and transform — and is applied by `project()` /
> `unit_for()` in [`fastnet_decoder/interpreter.py`](../fastnet_decoder/interpreter.py).

**This document holds the *reasoning*, not the mapping.** For which channel goes to which
path, in what unit, read one of these instead — all are derived from the schema, so none
of them can drift:

| Want | Look at |
|---|---|
| The full channel → name → path → unit table | [`channel_map.md`](channel_map.md) (generated) |
| The mapping as editable data | [`fastnet_decoder/data/fastnet.json`](../fastnet_decoder/data/fastnet.json) |
| The same table at runtime | `channel_map()` / `unit_for(path)` |

Everything below is the material that *isn't* derivable: why the namespace is shaped the
way it is, which choices were made against real captured data, and what remains open.

> **Note on history.** This file began as the pre-implementation spec for v3 and used to
> carry its own copy of the channel tables. They were removed in 3.2.0 — see
> [`architecture.md`](architecture.md) for why.

The decoder emits a flat map of **`{ signalk_path: SI_value }`**, one canonical entry per
physical quantity, in the unit Signal K defines for that path. No `display_text`, no
`layout`, no unit-variant duplicates. Delta/`$source`/timestamp wrapping is left to the
consumer (fastnet2ip, fastnet2n2k).

> **Scope note:** Signal K here is a *naming convention* only — a clean, self-describing,
> SI-typed key scheme. This output is **not** meant to be injected straight into a Signal K
> server; consumers adapt it. So we deliberately do **not** build SK delta objects, `$source`,
> timestamps, or `meta` blocks, and the vendor root `bandg.*` (schema-valid but not a
> standard branch) is fine precisely because no generic SK app needs to auto-discover it.

> **Architecture:** the decoder stays a **complete, faithful FastNet decoder** — every frame
> is decoded as fully as possible (numeric value, sign, `display_text`, layout, including the
> 7-segment 0x06 frames), even where downstream doesn't consume it. The `{ signalk_path:
> SI_value }` map is a **projection** selected over that full decode, not a replacement for it.
> Keeping the decode complete costs nothing downstream and preserves its value for debugging,
> reverse-engineering, and as the de-facto protocol spec. See note 12.

> **Path validation:** all standard paths were verified against the Signal K schema
> (SignalK/specification `master`, spec 1.7.0) on 2026-07-22. Units confirmed from the
> schema. `navigation.courseThroughWater` was confirmed **not** to exist and was moved to
> VENDOR. `performance.tackMagnetic` and the `...nextPoint.*` / `performance.*` families
> were confirmed present.

## Signal K guideline & design rationale

Checked against the Signal K spec (data-model doc, spec README, vessel schema) on
2026-07-22:

- **No mandated vendor-prefix convention exists** in the spec. Signal K's stated
  philosophy is "if a key you need is missing, define your own."
- **A top-level `bandg` branch is schema-valid** — the vessel schema does *not* set
  `"additionalProperties": false` at the root, so custom top-level keys are permitted.
- The only *soft* community preference (nest custom leaves under standard groups so a
  generic SK server/MFD auto-categorises them) **does not apply here** — this output is
  a naming convention consumed by bespoke adapters, not injected into a live SK server.
- Therefore `bandg.*` is chosen deliberately: schema-legal, collision-proof against
  future SK standardisation, and strippable/remappable with one `startswith("bandg.")`.
- Spec-blessed extras (`meta` blocks with units, upstreaming reusable keys via PR) are
  **optional** and intentionally out of scope — see the Scope note above.

## How each channel is disposed of

Every channel falls into exactly one of five categories. The rules are here; which category
a given channel is in is recorded in the schema and shown in `channel_map.md`'s `kind`
column.

| Category | Schema form | Meaning |
|---|---|---|
| **standard** | `signalk.path` on a standard SK path | A Signal K path exists for this quantity. |
| **vendor** | `signalk.path` under `bandg.*` | Real data, no standard SK path. One root means a consumer can keep, remap, or strip every non-standard value with a single `path.startswith("bandg.")` test, colliding with nothing in the SK standard tree. Grouped one level down in SK's own style (`bandg.wind.*`, `bandg.performance.*`, `bandg.steering.autopilot.*`, …). |
| **drop** | `signalk.drop: true` | Protocol, control or diagnostic traffic, not vessel data — bus control messages (Node Reset), protocol handshakes (Request/Act for Data), routing markers (from NMEA), instrument diagnostics (Depth Sounder Gain/Noise). Never emitted. |
| **collapsed** | `signalk.collapsedInto` | A redundant unit-variant of a channel already mapped — °F temperatures, knots wind speeds, feet/fathoms depth. Folded onto the canonical path rather than emitted twice. |
| **unknown** | no `signalk` block | Decodable, but no mapping decided yet. Emitted under `bandg.unknown.0x<id>` (raw value, no unit) rather than dropped, so decodable data is never silently lost. Covers the Linear/Remote user channels and any unrecognised channel id. |

**On `bandg.unknown.*` versus a designed path.** The Linear 1–16 and Remote 0–9 channels
carry user-assigned meaning and are opaque without configuration, so they are deliberately
left unmapped and surface as `bandg.unknown.0x<id>`. An earlier draft of this document
proposed `bandg.sensors.linear.<n>` / `bandg.sensors.remote.<n>`; that was never
implemented, and inventing a structured path for a value whose meaning is unknown would
imply knowledge the project doesn't have. Revisit if a consumer ever supplies a label and
unit.

## Unit conventions (Signal K)

| Quantity | SK unit | From FastNet | Action |
|---|---|---|---|
| Angle | **radian** | degrees | convert ×π/180 |
| Speed | **m/s** | knots (or native m/s) | convert ×0.514444 / select |
| Distance | **metre** | nautical miles | convert ×1852 |
| Depth | **metre** | metres (native) | select (see note 4) |
| Temperature | **kelvin** | °C | convert +273.15 |
| Pressure | **pascal** | hPa/mbar | convert ×100 |
| Ratio / % | **ratio 0–1** | percent | convert ÷100 |
| Voltage | **volt** | volts | select |
| Time / duration | **second** | seconds | select |
| Position | **degree** (lat/lon) | ASCII deg | parse |

`select` = the value is already on the bus in the SK unit (zero math; `{"type": "identity"}`
in the schema). `convert` = a `scale` or `affine` transform, whose exact factor is in the
schema alongside the channel.

> **Position is the one SK exception to radians** — `navigation.position` is decimal degrees.

## Output value types (DECIDED)

The output is a pure **`{ path: value }`** map — `display_text` and `layout` are **never**
exposed outside the decoder (they remain available internally for the decoder's own console /
debug only). `value` mirrors Signal K's own value model:

| Kind | Type | Notes |
|------|------|-------|
| Measurement | `float` | SI unit per the path; `None` = data unavailable |
| Enumerated state | `str` | the SK enum string (e.g. AP state `"auto"`, backlight `"Low"`) |
| Position | `object` | `{"latitude": <deg>, "longitude": <deg>}`, decimal degrees, −ve for S/W |

## Open items — TBC

None block the spec. Items 6, 7 and 8 are also surfaced by `tools/validate_schema.py` or by
`channel_map.md`, so they cannot quietly disappear from view.

| # | TBC item | Channels | Ref |
|---|----------|----------|-----|
| 1 | Confirm 0xFA and 0xE8 are distinct (active route vs selected wpt) or collapse onto one path | 0xFA, 0xE8 | note 2 |
| 2 | Depth path when a keel/waterline offset is set (belowKeel/belowSurface) — source chain metres→feet→fathoms already DECIDED | 0xC1 | note 4 |
| 3 | Finalise Autopilot `state` enum mapping table, esp. "Power" mode | 0xB5 | note 6 |
| 4 | Pick `nextPoint.velocityMadeGood` vs `performance.velocityMadeGoodToWaypoint` for VMC | 0xEC | note 8 |
| 5 | Layline encoding (format + unit) unconfirmed — no data in captured logs | 0xE2, 0xFB | note 11 |
| 6 | `bandg.motion.rate` unit (the schema currently declares it `"?"`); `bandg.performance.headLiftTrend` value type (enum vs signed) | 0x3C, 0x27 | — |
| 7 | **Routing WIRED** (Magnetic confirmed from data). Single fill-in: capture the `°T` layout byte value (no True bearing in any log) and add its `segmentA` entry — True routing then activates unchanged | 0x49, 0x6D, 0x84 | note 13 |
| 8 | **UTC Time (0xDD) is unmapped**, emitting `bandg.unknown.0xDD`. An earlier draft of this document claimed `navigation.datetime`; that was never implemented. Decide between `bandg.time.utc` (seconds since midnight, mirroring 0xDC `bandg.time.local`) and leaving it unmapped | 0xDD | note 1 |

*Resolved and removed:* the `navigation.position` value shape (formerly TBC #8) is settled —
`{"latitude": <deg>, "longitude": <deg>}`, decimal degrees, implemented and documented in the
README. See note 14.

## Tentative items — RESOLVED (data-driven, captured logs 2026-07-22)

| Ch | Was tentative | Resolution | Evidence in logs |
|----|---------------|-----------|------------------|
| 0x75 | `navigation.racing.timeToStart` | ❌ **rejected** → `bandg.time.timer` | 318 samples, fmt 0x05, value **increments 1/sec up to ~49 h** ("1 day, 21:29:09") — a free-running clock, not a start countdown |
| 0x35 | `performance.targetAngle` | ⚠️ **demoted** → `bandg.performance.optimumWindAngle` | count = 0 (never seen); 0x53 Target TWA is observed and owns `performance.targetAngle` |
| 0xE2 | `navigation.racing.layline.distance` | ✅ **accepted** (standard path) | count = 0, but the SK definition "current distance to the layline" (m) is an exact semantic match — encoding unconfirmed, see note 11 |
| 0xFB | `navigation.racing.layline.time` | ✅ **accepted** (standard path) | count = 0, but the SK definition "time to the layline at current speed/heading" (s) matches exactly — encoding unconfirmed, see note 11 |

---

## Notes

1. **UTC Time (0xDD):** FastNet sends time-of-day only, no date. `navigation.datetime`
   wants a full RFC3339 timestamp — the consumer would have to supply the date. The options
   are to emit seconds-since-midnight (as 0xDC Local Time does, under `bandg.time.local`) and
   let the consumer assemble it, or to leave it unmapped. Currently unmapped — see TBC #8.
2. **0xFA vs 0xE8:** both look like distance-to-next-waypoint. Confirm whether they
   differ (active route vs selected wpt) before collapsing onto one path.
3. **Bearing Wpt→Wpt (0xE0/0xE1):** this is the *leg* bearing (origin→destination),
   mapped to `bearingTrack*`, distinct from bearing-to-next (0xE3–0xE6).
4. **Depth source — DECIDED (fallback chain).** Emit `belowTransducer` from **metres (0xC1)**;
   if unavailable fall back to **feet (0xC2 × 0.3048)**, then **fathoms (0xC3 × 1.8288)**. Metres
   is preferred for simplicity even though feet (0.1 ft ≈ 0.03 m) is ~3× finer — precision
   trade accepted. In the schema this is the `fallbackGroup` / `fallbackPriority` pair.
   *Still open:* FastNet depth is below-transducer by default, but a B&G keel/waterline
   offset would make the correct path `belowKeel` / `belowSurface` (TBC #2).
5. **Wind speed select vs convert:** the m/s channels (0x4F/0x56) are `select`, but the
   knots channels (0x4D/0x55, 0.1 kn ≈ 0.05 m/s) are ~2× finer — convert from knots
   for best resolution.
6. **Autopilot state (0xB5) — DECIDED.** Map decoded FastNet mode → SK `steering.autopilot.state`:
   Standby (high 0x50) → `standby`; Compass (low 0x01) → `auto`; Wind (low 0x04) → `wind`;
   NMEA WP (low 0x13) → `route`; Power (low 0x02) → `directControl` (power-steer via ± buttons).
   SK `alarm`/`noDrift`/`depthContour` have no FastNet equivalent — leave unmapped. This is the
   one channel needing a bespoke decode step (`overrides` in the schema), because its 16-bit
   value is a composite of two separate pieces of information rather than a plain scaled number.
7. **Battery id:** SK requires an instance id in the path; use a configured/default
   id (e.g. `house`) → `electrical.batteries.house.voltage` (verified unit V). In the schema
   this is `pathParam`.
8. **VMG to Waypoint (0xEC):** mapped to `navigation.courseGreatCircle.nextPoint.velocityMadeGood`
   (verified, m/s). The alternative `performance.velocityMadeGoodToWaypoint` (also verified,
   m/s) is arguably a cleaner semantic home — pick one and be consistent.
9. **Heading on Next Tack (0x9A):** now a **standard** path — `performance.tackMagnetic`
   (verified, rad; "Magnetic heading on opposite tack"). Use `performance.tackTrue` if the
   value is referenced to true north instead. Was previously proposed as VENDOR.
10. **Course through water (0x69):** `navigation.courseThroughWater` was verified **not**
    to exist in the SK schema. No standard path → `bandg.navigation.courseThroughWater`,
    or drop it and let the consumer derive it from heading + leeway.
11. **Laylines (0xE2 / 0xFB):** neither channel appears in the captured logs, so the FastNet
    encoding (format, unit) is **unconfirmed**. The SK paths are a confirmed semantic match.
    Assumption: 0xE2 distance is NM→m (convert), 0xFB time is seconds (select). Verify against
    live data before relying on them. SK also has `oppositeLayline.*` for the other tack —
    FastNet exposes only one, mapped to `layline.*`.
12. **Format 0x06 is load-bearing, not redundant — RESOLVED: keep full decode.** Some channels
    (Heel, Trim, Target TWA, AP Compass Target, Air Temp, Baro) are, in some bus configurations,
    broadcast **only** as 7-segment display frames (format 0x06) — no numeric frame at all.
    Per-file evidence (Heel 0x34): `big.txt` 64 numeric / 0 display, but `example1` **0 / 181**,
    `example2` 0 / 191, `big_with_ap_actions` 0 / 137. Where both do appear (AP Compass Target),
    numeric usually dominates — so this is **not** "display updates more often than numeric"
    (an earlier mis-reading from pooling dissimilar captures). The real risk: a numeric-only
    decoder would emit **nothing** for these channels on a bus that only carries their display
    frames. Likely mechanism: 0x06 display frames are always broadcast to drive FFD/20-20
    displays; the numeric broadcast appears only when a node actively requests the channel.
    **Decision (DECIDED):** keep format 0x06 decode **as-is** — `display_text` only, `value`
    stays `None`; do **not** build a 0x06→numeric parser. Combined with the pure `{path: value}`
    output (display_text not exposed), this means a channel that arrives *only* as 0x06 emits
    `{path: None}` — **no usable downstream value** on a display-only bus (e.g. Heel in
    `example1`/`example2`). **This dropout is accepted** — simplicity over display-only-bus
    coverage. Nothing about sign depends on 0x06 — sign always comes from `segmentA` on the
    numeric frames, which are retained.
13. **Layout-driven Magnetic/True routing (0x49 / 0x6D / 0x84) — WIRED.** These single-id channels
    carry the reference in the layout byte; the decoder routes on it (`channel + layout → path`,
    `routedBy: "layout"` in the schema). This removes the consumer's need to inspect `layout` for
    T/M (fastnet2n2k's `_bearing_ref` reads it today) — the reference is carried by *which path*
    arrives. Routing logic: `layout == °M (0x66)` → the Magnetic path; `layout == °T` → the True
    path; any other/unknown layout → default Magnetic (matches all captured data). **Correction:**
    the observed `°M` on TWD (0x6D) and Tidal Set (0x84) means their default is
    `directionMagnetic` / `setMagnetic`, not the `...True` originally assumed statically.
    **Single remaining input:** the `°T` byte *value* — no True bearing appears in any capture, so
    the `segmentA` `°T` entry is unknown and the True paths are currently unreachable from real
    frames (`tools/validate_schema.py` reports this as a warning). Add the entry when a True frame
    is seen and True routing activates with no other change. See TBC #7.
14. **Position value shape (LatLon) — DECIDED.** The decoder parses the ASCII fix into
    `navigation.position` as `{"latitude": <deg>, "longitude": <deg>}` — decimal degrees,
    negative for S/W — so consumers no longer need to parse the raw ASCII themselves
    (fastnet2n2k's `process_position` predates this).
15. **Pressure trend (0x86):** a pressure *trend* is a rate/tendency, not an absolute
    pressure — so the value is emitted **opaque** (identity, no unit); the `0x86` encoding is
    unconfirmed (TBC). Signal K has **no standard** pressure-trend path (only
    `environment.outside.pressure`, Pa); the community `signalk-barometer-trend` plugin computes
    `environment.outside.pressure.trend.{tendency (string), severity (−4..+4)}` from pressure
    history — a consumer wanting that would derive it, not read it from 0x86 directly.
