# v3 Output Spec — FastNet → Signal K mapping (PROPOSAL, not implemented)

> **Path validation:** all standard paths below verified against the Signal K
> schema (SignalK/specification `master`, spec 1.7.0) on 2026-07-22. Units confirmed
> from the schema. `navigation.courseThroughWater` was confirmed **not** to exist and
> has been moved to VENDOR. `performance.tackMagnetic` and the `...nextPoint.*` /
> `performance.*` families were confirmed present.

Target for a v3 rewrite: the decoder emits a flat map of **`{ signalk_path: SI_value }`**,
one canonical entry per physical quantity, in the unit Signal K defines for that path.
No `display_text`, no `layout`, no unit-variant duplicates. Delta/`$source`/timestamp
wrapping is left to the consumer (fastnet2ip, fastnet2n2k).

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

## Open items — TBC

Resolve (decision or live data) before/at implementation. None block the spec.

| # | TBC item | Channels | Ref |
|---|----------|----------|-----|
| 1 | Confirm 0xFA and 0xE8 are distinct (active route vs selected wpt) or collapse onto one path | 0xFA, 0xE8 | note 2 |
| 2 | Depth path when a keel/waterline offset is set (belowKeel/belowSurface) — source chain metres→feet→fathoms already DECIDED | 0xC1 | note 4 |
| 3 | Finalise Autopilot `state` enum mapping table, esp. "Power" mode | 0xB5 | note 6 |
| 4 | Pick `nextPoint.velocityMadeGood` vs `performance.velocityMadeGoodToWaypoint` for VMC | 0xEC | note 8 |
| 5 | Layline encoding (format + unit) unconfirmed — no data in captured logs | 0xE2, 0xFB | note 11 |
| 6 | `bandg.motion.rate` unit; `bandg.performance.headLiftTrend` value type (enum vs signed) | 0x3C, 0x27 | tree |
| 7 | **Routing WIRED** (Magnetic confirmed from data). Single fill-in: capture the `°T` layout byte value (no True bearing in any log) and add its `SEGMENT_A` entry — True routing then activates unchanged | 0x49, 0x6D, 0x84 | note 13 |
| 8 | Define the `navigation.position` value shape emitted by the decoder (e.g. `{latitude, longitude}` decimal degrees) — consumer currently parses the ASCII itself | LatLon | note 14 |

## Unit conventions (Signal K)

| Quantity | SK unit | From FastNet | Action |
|---|---|---|---|
| Angle | **radian** | degrees | convert ×π/180 |
| Speed | **m/s** | knots (or native m/s) | convert ×0.514444 / select |
| Distance | **metre** | nautical miles | convert ×1852 |
| Depth | **metre** | metres (native) | select (see precision note) |
| Temperature | **kelvin** | °C | convert +273.15 |
| Pressure | **pascal** | hPa/mbar | convert ×100 |
| Ratio / % | **ratio 0–1** | percent | convert ÷100 |
| Voltage | **volt** | volts | select |
| Time / duration | **second** | seconds | select |
| Position | **degree** (lat/lon) | ASCII deg | parse |

`select` = value already on the bus in the SK unit (zero math).
`convert` = needs a constant from the table at the bottom.

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

---

## Mapping — channels WITH a standard Signal K path

> **Layout-driven path routing (Magnetic vs True) — WIRED, decoder responsibility.** Three
> channels use one channel id for a quantity Signal K splits by reference; the reference is in the
> decoded layout byte, so the decoder routes on it (`channel + layout → path`):
>
> | Ch | layout `°M` (0x66) → | layout `°T` (byte TBD) → |
> |----|----------------------|--------------------------|
> | 0x49 Heading | `navigation.headingMagnetic` | `navigation.headingTrue` |
> | 0x6D True Wind Direction | `environment.wind.directionMagnetic` | `environment.wind.directionTrue` |
> | 0x84 Tidal Set | `environment.current.setMagnetic` | `environment.current.setTrue` |
>
> **Data confirms:** every captured bearing is `°M` (Heading/TWD/Set = 625/315/314 frames, all `°M`),
> so the default is **Magnetic** — this *corrects* the earlier static guesses of `directionTrue` /
> `setTrue` for TWD and Set. COG (`0xE9`/`0xEA`) carries `layout=None` and is disambiguated by channel
> id → static, as specified (likewise waypoint bearings `0xE0`/`0xE1`, `0xE3`–`0xE6`). The only missing
> input is the `°T` byte *value* (no True frame in any capture); routing activates for True the moment
> its `SEGMENT_A` entry is added — no other change. See note 13.

### navigation.*

| Ch | Current name | Signal K path | Unit | Action |
|----|--------------|---------------|------|--------|
| 0x41 | Boatspeed (Knots) | `navigation.speedThroughWater` | m/s | convert |
| 0xEB | Speed Over Ground | `navigation.speedOverGround` | m/s | convert |
| 0x49 | Heading | `navigation.heading{Magnetic\|True}` | rad | convert ¹³ |
| 0xE9 | Course Over Ground (True) | `navigation.courseOverGroundTrue` | rad | convert |
| 0xEA | Course Over Ground (Mag) | `navigation.courseOverGroundMagnetic` | rad | convert |
| 0x44 | Yaw rate | `navigation.rateOfTurn` | rad/s | convert |
| 0x34 | Heel Angle | `navigation.attitude.roll` | rad | convert |
| 0x9B | Fore/Aft Trim | `navigation.attitude.pitch` | rad | convert |
| 0x82 | Leeway | `navigation.leewayAngle` | rad | convert |
| 0xCD | Stored Log (NM) | `navigation.log` | m | convert |
| 0xCF | Trip Log (NM) | `navigation.trip.log` | m | convert |
| LatLon | (command 0x03) | `navigation.position` | deg | parse |
| 0xDD | UTC Time | `navigation.datetime` | RFC3339 | see note ¹ |
| 0xE7 | Distance to Waypoint (Rhumb) | `navigation.courseRhumbline.nextPoint.distance` | m | convert |
| 0xE8 | Distance to Waypoint (G.C.) | `navigation.courseGreatCircle.nextPoint.distance` | m | convert |
| 0xFA | Next Waypoint Distance | `navigation.courseGreatCircle.nextPoint.distance` | m | convert ² |
| 0xE3 | Bearing to Wpt (Rhumb True) | `navigation.courseRhumbline.nextPoint.bearingTrue` | rad | convert |
| 0xE4 | Bearing to Wpt (Rhumb Mag) | `navigation.courseRhumbline.nextPoint.bearingMagnetic` | rad | convert |
| 0xE5 | Bearing to Wpt (G.C. True) | `navigation.courseGreatCircle.nextPoint.bearingTrue` | rad | convert |
| 0xE6 | Bearing to Wpt (G.C. Mag) | `navigation.courseGreatCircle.nextPoint.bearingMagnetic` | rad | convert |
| 0xE0 | Bearing Wpt→Wpt (True) | `navigation.courseGreatCircle.bearingTrackTrue` | rad | convert ³ |
| 0xE1 | Bearing Wpt→Wpt (Mag) | `navigation.courseGreatCircle.bearingTrackMagnetic` | rad | convert ³ |
| 0xEC | VMG to Waypoint (VMC) | `navigation.courseGreatCircle.nextPoint.velocityMadeGood` | m/s | convert ⁸ |
| 0xED | Time to Waypoint | `navigation.courseGreatCircle.nextPoint.timeToGo` | s | select |
| 0xEE | Cross Track Error | `navigation.courseGreatCircle.crossTrackError` | m | convert |
| 0xE2 | Layline Distance | `navigation.racing.layline.distance` | m | convert ¹¹ |
| 0xFB | Time to Layline | `navigation.racing.layline.time` | s | select ¹¹ |

### environment.*

| Ch | Current name | Signal K path | Unit | Action |
|----|--------------|---------------|------|--------|
| 0xC1 | Depth (Meters) | `environment.depth.belowTransducer` | m | select ⁴ |
| 0x1F | Sea Temperature (°C) | `environment.water.temperature` | K | convert |
| 0x1D | Air Temperature (°C) | `environment.outside.temperature` | K | convert |
| 0x87 | Barometric Pressure | `environment.outside.pressure` | Pa | convert |
| 0x4F | Apparent Wind Speed (m/s) | `environment.wind.speedApparent` | m/s | select ⁵ |
| 0x51 | Apparent Wind Angle | `environment.wind.angleApparent` | rad | convert |
| 0x56 | True Wind Speed (m/s) | `environment.wind.speedTrue` | m/s | select ⁵ |
| 0x59 | True Wind Angle | `environment.wind.angleTrueWater` | rad | convert |
| 0x6D | True Wind Direction | `environment.wind.direction{Magnetic\|True}` | rad | convert ¹³ |
| 0x83 | Tidal Drift | `environment.current.drift` | m/s | convert |
| 0x84 | Tidal Set | `environment.current.set{Magnetic\|True}` | rad | convert ¹³ |

### steering.*

| Ch | Current name | Signal K path | Unit | Action |
|----|--------------|---------------|------|--------|
| 0x0B | Rudder Angle | `steering.rudderAngle` | rad | convert |
| 0xB5 | Autopilot Mode | `steering.autopilot.state` | enum string | map ⁶ |
| 0xA6 | Autopilot Compass Target | `steering.autopilot.target.headingMagnetic` | rad | convert |

### performance.*

| Ch | Current name | Signal K path | Unit | Action |
|----|--------------|---------------|------|--------|
| 0x7F | Velocity Made Good (Knots) | `performance.velocityMadeGood` | m/s | convert |
| 0x7D | Target Boatspeed | `performance.targetSpeed` | m/s | convert |
| 0x53 | Target TWA | `performance.targetAngle` | rad | convert |
| 0x7C | Polar Performance | `performance.polarSpeedRatio` | ratio | convert ÷100 |
| 0x9A | Heading on Next Tack | `performance.tackMagnetic` | rad | convert ⁹ |

### electrical.*

| Ch | Current name | Signal K path | Unit | Action |
|----|--------------|---------------|------|--------|
| 0x8D | Battery Volts | `electrical.batteries.<id>.voltage` | V | select ⁷ |

---

## Mapping — channels with NO standard Signal K path

Approach legend:
- **DROP** — protocol/control/diagnostic, not vessel data. Don't emit.
- **VENDOR** — real data but no standard SK path → emit under a single proprietary
  root **`bandg.*`**, mirroring SK's own grouping/camelCase style one level down
  (`bandg.wind.*`, `bandg.performance.*`, `bandg.steering.autopilot.*`, …). One root
  means a consumer can keep, remap, or strip every non-standard value with a single
  `path.startswith("bandg.")` test. Nothing collides with the SK standard tree.
- **TENTATIVE** — a plausible standard path exists but needs confirming against the
  SK schema / real semantics before committing.

### DROP — protocol, control, diagnostics

| Ch | Name | Why drop |
|----|------|----------|
| 0x00 | Node Reset | bus control message, not data |
| 0x50 | from NMEA | routing marker |
| 0x68 | Request for Data | protocol handshake |
| 0x6A | Act for Data | protocol handshake |
| 0x36 | Depth Sounder Receiver Gain | instrument diagnostic |
| 0x37 | Depth Sounder Noise | instrument diagnostic |
| 0xC9 | Backlight (Light Intensity) | display config, not vessel data (or VENDOR `bandg.display.backlight` if wanted) |

### VENDOR — proposed `bandg.*` namespace tree

```
bandg
├─ wind
│  ├─ measuredSpeed              0x57   m/s    masthead speed pre-calibration
│  ├─ measuredAngle              0x5A   rad    masthead angle pre-calibration
│  └─ upwash                     0x85   rad    upwash correction angle
├─ mast
│  ├─ rotation                   0x9C   rad    Mast Angle (rotation)
│  └─ windAngle                  0x9D   rad    Wind Angle to the Mast
├─ performance
│  ├─ headLiftTrend              0x27   enum   header/lift trend
│  ├─ tacking                    0x32   ratio  Tacking Performance
│  ├─ reaching                   0x33   ratio  Reaching Performance
│  ├─ courseToSail               0xF9   rad
│  ├─ optimumWindAngle           0x35   rad    unobserved; 0x53 owns performance.targetAngle
│  └─ nextLeg
│     ├─ angleApparent           0x6F   rad
│     ├─ speedApparent           0x71   m/s
│     └─ targetSpeed             0x70   m/s
├─ navigation
│  ├─ speedThroughWaterAverage   0x64   m/s    Average Speed
│  ├─ courseThroughWater         0x69   rad    Course (HDG + Leeway)
│  └─ deadReckoning
│     ├─ distance                0x81   m
│     └─ course                  0xD3   rad
├─ motion
│  ├─ rate                       0x3C   rad/s? Rate Motion (unit TBC)
│  └─ pitchRate                  0x9E   rad/s
├─ steering
│  ├─ offCourse                  0x29   rad    Off Course
│  └─ autopilot
│     ├─ offCourse               0xAF   rad    Autopilot Off Course
│     └─ fixedSpeed              0x46   m/s    Autopilot Speed Fixed
├─ environment
│  └─ pressureTrend              0x86   Pa/s   Barometric Pressure Trend
├─ time
│  ├─ local                      0xDC   s      Local Time (or DROP; SK is UTC)
│  └─ timer                      0x75   s      free-running elapsed timer/clock (NOT race countdown — see note 12)
└─ sensors
   ├─ linear.<1..16>             0x0C–0x17, 0x38–0x3B   generic analog (see note)
   └─ remote.<0..9>              0xEF–0xF8              generic remote (see note)
```

**`bandg.sensors.*`** (Linear 1–16, Remote 0–9) carry user-assigned meaning and are
opaque without configuration. Default: **DROP**; expose under `bandg.sensors.linear.<n>` /
`bandg.sensors.remote.<n>` only when a consumer supplies a label + unit.

Flat form (what the decoder emits):

| Ch | Name | `bandg.*` path | Unit |
|----|------|----------------|------|
| 0x57 | Measured Wind Speed | `bandg.wind.measuredSpeed` | m/s |
| 0x5A | Measured Wind Angle | `bandg.wind.measuredAngle` | rad |
| 0x85 | Upwash | `bandg.wind.upwash` | rad |
| 0x9C | Mast Angle | `bandg.mast.rotation` | rad |
| 0x9D | Wind Angle to the Mast | `bandg.mast.windAngle` | rad |
| 0x27 | Head/Lift Trend | `bandg.performance.headLiftTrend` | enum/signed |
| 0x32 | Tacking Performance | `bandg.performance.tacking` | ratio |
| 0x33 | Reaching Performance | `bandg.performance.reaching` | ratio |
| 0xF9 | Course to Sail | `bandg.performance.courseToSail` | rad |
| 0x35 | Optimum Wind Angle | `bandg.performance.optimumWindAngle` | rad |
| 0x6F | Next Leg Apparent Wind Angle | `bandg.performance.nextLeg.angleApparent` | rad |
| 0x71 | Next Leg Apparent Wind Speed | `bandg.performance.nextLeg.speedApparent` | m/s |
| 0x70 | Next Leg Target Boat Speed | `bandg.performance.nextLeg.targetSpeed` | m/s |
| 0x64 | Average Speed | `bandg.navigation.speedThroughWaterAverage` | m/s |
| 0x69 | Course (HDG + Leeway) | `bandg.navigation.courseThroughWater` | rad |
| 0x81 | Dead Reckoning Distance | `bandg.navigation.deadReckoning.distance` | m |
| 0xD3 | Dead Reckoning Course | `bandg.navigation.deadReckoning.course` | rad |
| 0x3C | Rate Motion | `bandg.motion.rate` | rad/s? |
| 0x9E | Pitch Rate (Motion) | `bandg.motion.pitchRate` | rad/s |
| 0x29 | Off Course | `bandg.steering.offCourse` | rad |
| 0xAF | Autopilot Off Course | `bandg.steering.autopilot.offCourse` | rad |
| 0x46 | Autopilot Speed Fixed | `bandg.steering.autopilot.fixedSpeed` | m/s |
| 0x86 | Barometric Pressure Trend | `bandg.environment.pressureTrend` | Pa/s |
| 0xDC | Local Time | `bandg.time.local` | s |
| 0x75 | Timer | `bandg.time.timer` | s |
| 0x0C–0x17, 0x38–0x3B | Linear 1–16 | `bandg.sensors.linear.<n>` | — |
| 0xEF–0xF8 | Remote 0–9 | `bandg.sensors.remote.<n>` | — |

### Tentative items — RESOLVED (data-driven, captured logs 2026-07-22)

| Ch | Was tentative | Resolution | Evidence in logs |
|----|---------------|-----------|------------------|
| 0x75 | `navigation.racing.timeToStart` | ❌ **rejected** → `bandg.time.timer` | 318 samples, fmt 0x05, value **increments 1/sec up to ~49 h** ("1 day, 21:29:09") — a free-running clock, not a start countdown |
| 0x35 | `performance.targetAngle` | ⚠️ **demoted** → `bandg.performance.optimumWindAngle` | count = 0 (never seen); 0x53 Target TWA is observed and owns `performance.targetAngle` |
| 0xE2 | `navigation.racing.layline.distance` | ✅ **accepted** (standard table) | count = 0, but SK def "current distance to the layline" (m) is an exact semantic match — encoding unconfirmed, see note 11 |
| 0xFB | `navigation.racing.layline.time` | ✅ **accepted** (standard table) | count = 0, but SK def "time to the layline at current speed/heading" (s) matches exactly — encoding unconfirmed, see note 11 |

---

## Notes

1. **UTC Time (0xDD):** FastNet sends time-of-day only, no date. `navigation.datetime`
   wants a full RFC3339 timestamp — consumer must supply the date. Emit seconds-since-
   midnight and let the consumer assemble, or DROP.
2. **0xFA vs 0xE8:** both look like distance-to-next-waypoint. Confirm whether they
   differ (active route vs selected wpt) before collapsing onto one path.
3. **Bearing Wpt→Wpt (0xE0/0xE1):** this is the *leg* bearing (origin→destination),
   mapped to `bearingTrack*`, distinct from bearing-to-next (0xE3–0xE6).
4. **Depth source — DECIDED (fallback chain).** Emit `belowTransducer` from **metres (0xC1)**;
   if unavailable fall back to **feet (0xC2 × 0.3048)**, then **fathoms (0xC3 × 1.8288)**. Metres
   is preferred for simplicity even though feet (0.1 ft ≈ 0.03 m) is ~3× finer — precision
   trade accepted. *Still open:* FastNet depth is below-transducer by default, but a B&G keel/
   waterline offset would make the correct path `belowKeel` / `belowSurface` (TBC #2).
5. **Wind speed select vs convert:** m/s channels (0x4F/0x56) are `select`, but the
   knots channels (0x4D/0x55, 0.1 kn ≈ 0.05 m/s) are ~2× finer — convert from knots
   for best resolution.
6. **Autopilot state (0xB5) — DECIDED.** Map decoded FastNet mode → SK `steering.autopilot.state`:
   Standby (high 0x50) → `standby`; Compass (low 0x01) → `auto`; Wind (low 0x04) → `wind`;
   NMEA WP (low 0x13) → `route`; Power (low 0x02) → `directControl` (power-steer via ± buttons).
   SK `alarm`/`noDrift`/`depthContour` have no FastNet equivalent — leave unmapped.
7. **Battery id:** SK requires an instance id in the path; use a configured/default
   id (e.g. `house`) → `electrical.batteries.house.voltage` (verified unit V).
8. **VMG to Waypoint (0xEC):** mapped to `navigation.courseGreatCircle.nextPoint.velocityMadeGood`
   (verified, m/s). Alternative `performance.velocityMadeGoodToWaypoint` (also verified,
   m/s) is arguably a cleaner semantic home — pick one and be consistent.
9. **Heading on Next Tack (0x9A):** now a **standard** path — `performance.tackMagnetic`
   (verified, rad; "Magnetic heading on opposite tack"). Use `performance.tackTrue` if the
   value is referenced to true north instead. Was previously proposed as VENDOR.
10. **Course through water (0x69):** `navigation.courseThroughWater` was verified **not**
    to exist in the SK schema. No standard path → `bandg.navigation.courseThroughWater`,
    or drop and let the consumer derive it from heading + leeway.
11. **Laylines (0xE2 / 0xFB):** neither channel appears in the captured logs, so the FastNet
    encoding (format, unit) is **unconfirmed**. The SK paths are a confirmed semantic match.
    Assumption: 0xE2 distance is NM→m (convert), 0xFB time is seconds (select). Verify against
    live data before implementing. SK also has `oppositeLayline.*` for the other tack — FastNet
    exposes only one, mapped to `layline.*`.
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
    coverage. Nothing about sign depends on 0x06 — sign always comes from `SEGMENT_A` on the
    numeric frames, which are retained.
13. **Layout-driven Magnetic/True routing (0x49 / 0x6D / 0x84) — WIRED.** These single-id channels
    carry the reference in the layout byte; the decoder routes on it (`channel + layout → path`, see
    the routing table above). This removes the consumer's need to inspect `layout` for T/M
    (fastnet2n2k's `_bearing_ref` reads it today) — the reference is carried by *which path* arrives.
    Routing logic: `layout == °M (0x66)` → the Magnetic path; `layout == °T` → the True path; any
    other/unknown layout → default Magnetic (matches all captured data). **Correction:** the observed
    `°M` on TWD (0x6D) and Tidal Set (0x84) means their default is `directionMagnetic` / `setMagnetic`,
    not the `...True` I had statically assumed. **Single remaining input:** the `°T` byte *value* — no
    True bearing appears in any capture, so the `SEGMENT_A` `°T` entry is unknown; add it when a True
    frame is seen and True routing activates with no other change. See TBC #7.
14. **Position value shape (LatLon):** the decoder parses the ASCII fix into
    `navigation.position` — decimal degrees, negative for S/W. Define the value structure
    (recommended `{"latitude": <deg>, "longitude": <deg>}`) so consumers stop parsing the raw
    ASCII themselves (fastnet2n2k's `process_position` does this today). See TBC #8.

## Collapsed / dropped duplicate channels

These carry the same quantity as a channel already mapped above, in a redundant
unit or a raw pre-calibration form. Dropped entirely in v3:

| Ch | Name | Superseded by |
|----|------|---------------|
| 0x1C | Air Temperature (°F) | 0x1D → `environment.outside.temperature` |
| 0x1E | Sea Temperature (°F) | 0x1F → `environment.water.temperature` |
| 0x42 | Boatspeed (Raw) | 0x41 → `navigation.speedThroughWater` |
| 0x4A | Heading (Raw) | 0x49 → `navigation.headingMagnetic` |
| 0x4D | Apparent Wind Speed (Knots) | 0x4F → `environment.wind.speedApparent` (or convert from this if finer) |
| 0x4E | Apparent Wind Speed (Raw) | 0x4F |
| 0x52 | Apparent Wind Angle (Raw) | 0x51 → `environment.wind.angleApparent` |
| 0x55 | True Wind Speed (Knots) | 0x56 → `environment.wind.speedTrue` (or convert from this if finer) |
| 0x65 | Average Speed (raw) | 0x64 (itself VENDOR) |
| 0xC2 | Depth (Feet) | 0xC1 → `environment.depth.belowTransducer` (but finer — see note 4) |
| 0xC3 | Depth (Fathoms) | 0xC1 |

## Conversion constants

| From → To | Multiply by (or formula) |
|-----------|--------------------------|
| knots → m/s | 0.514444 |
| nautical miles → m | 1852 |
| feet → m | 0.3048 |
| fathom → m | 1.8288 |
| °C → K | + 273.15 |
| °F → K | (F − 32) × 5/9 + 273.15 |
| hPa/mbar → Pa | 100 |
| degrees → radians | π / 180 (0.0174533) |
| percent → ratio | ÷ 100 |
