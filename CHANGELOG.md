# Changelog

All notable changes to pyfastnet. Versions follow [semantic versioning](https://semver.org/):
the **output format** is the public contract, so a change to what `FrameBuffer` queues is a
major bump.

This file was reconstructed from git history in 3.2.0; entries before that were written
after the fact from the tagged releases.

## [3.2.0] — 2026-09-06

The protocol is now stored as data rather than code. **No change to output or API** — every
decode is byte-identical to 3.1.0.

### Changed
- The hand-written decoder (`mappings.py`, `decode_fastnet.py`, `signalk_map.py`) is
  replaced by [`fastnet_decoder/data/fastnet.json`](fastnet_decoder/data/fastnet.json) — the
  protocol written down as data — plus `interpreter.py`, a generic engine that reads it and
  holds no protocol facts of its own. Rationale in
  [`docs/architecture.md`](docs/architecture.md).
- Verified byte-identical to 3.1.0 across all eight bundled captures: 9,322 frames, covering
  the complete decode, the Signal K projection, `channel_map()` and `unit_for()`. Replayed
  through `fastnet2ip` on both wire formats, 23,420 messages unchanged.

### Added
- `tools/validate_schema.py`, run by the test suite, so a malformed schema edit fails at test
  time rather than as a runtime error on the water.
- `docs/protocol.md` — a language-agnostic description of the FastNet wire protocol, for
  porting the decoder to another language.
- `docs/architecture.md`, `CHANGELOG.md`.

### Fixed
- `set_log_level()` now accepts a `logging` constant (`set_log_level(logging.DEBUG)`) as well
  as a name. The constant form is what the README documents, and it previously raised
  `AttributeError`.

### Note
- No runtime dependency was added; `data/fastnet.json` ships inside the package.

## [3.1.0] — 2026-07-22

### Added
- `channel_map()` — the master reference of every B&G channel number → name → Signal K path
  + unit, derived from the mapping so it cannot drift. Rendered as
  [`docs/channel_map.md`](docs/channel_map.md).

### Changed
- Channels that decode but have no Signal K mapping are emitted as `bandg.unknown.0x<id>`
  rather than dropped, so decodable data is never silently lost.

### Fixed
- `0x86` (Barometric Pressure Trend) handling.
- `channel_map()` renders routed paths in brace form (`heading{Magnetic,True}`).

## [3.0.0] — 2026-07-22

**Breaking: the output format changed.**

### Changed
- `FrameBuffer` now queues `{signalk_path: SI_value}` — e.g.
  `navigation.speedThroughWater = 3.6` — instead of the v2 name-keyed
  `{value, display_text, layout}` dicts. Units follow the Signal K spec: radians, m/s,
  metres, kelvin, pascals.
- Redundant unit-variant channels (°F, knots, feet/fathoms depth) are collapsed onto one
  canonical path.

### Added
- `project()` exported at package top level, to project a single decoded frame yourself.
- `unit_for(path)` — the SI unit for any emitted path.
- B&G-proprietary channels with no standard Signal K path are emitted under a `bandg.*`
  namespace, including the four raw pre-calibration sensor values.

### Migration
- The complete v2-style decode is still available: `FrameBuffer(project=False)`.

## [2.0.19] — 2026-07-22

### Fixed
- `set_log_level()` validates level names instead of failing obscurely on an unknown one.

## [2.0.18] — 2026-06-15

### Added
- Backlight / Light Intensity frames (command `0xC9`) are decoded.
- Autopilot Mode (`0xB5`) reworked into a structured engagement-state + mode decode.

## [2.0.17] — 2026-06-13

### Changed
- Only Broadcast and LatLon frames are decoded and queued. Other commands are probed
  speculatively for reverse-engineering rather than emitted as if understood.

## [2.0.16] — 2026-06-13

### Changed
- Modern packaging: `pyproject.toml`, single-sourced version.

## [2.0.15] — 2026-06-09

A large correctness and test release.

### Fixed
- **Heel angle sign** corrected.
- **Leeway sign** bug fixed.
- LatLon frames were being mislabelled via the generic channel table.
- Tidal Drift is always non-negative; the downwind VMG layout correctly yields a negative
  value.

### Added
- All `SEGMENT_A` layout codes decoded from 7-segment bit analysis, and `SEGMENT_B`
  expanded from raw log analysis.
- Comprehensive per-channel unit tests covering value, display text, layout and sign.

### Changed
- Decoded channel dicts simplified to `{value, display_text, layout}`.
- Unrecognised segment layout codes return `TBC` rather than `?`.

## [1.2.3] — 2026-02-25

### Fixed
- **Format `0x07` MSB bit-shift bug** — a spurious `>> 1` silently corrupted any value above
  255. Confirmed affecting Depth (Feet), Tidal Set, Autopilot Compass Target and VMG; latent
  for Depth (Metres) above 25.5 m, Depth (Fathoms) above 13.9 fm, and Leeway. Regression
  tests added for every affected channel.

### Changed
- `Course` renamed `Course (HDG + Leeway)` to reflect what it actually is; where leeway is
  unavailable it returns the same value as heading.
- Logging levels made sensible.

## [1.2.0] — 2026-01-21

First tagged release on PyPI.

[3.2.0]: https://github.com/ghotihook/pyfastnet/releases/tag/v3.2.0
[3.1.0]: https://github.com/ghotihook/pyfastnet/releases/tag/v3.1.0
[3.0.0]: https://github.com/ghotihook/pyfastnet/releases/tag/v3.0.0
[2.0.19]: https://github.com/ghotihook/pyfastnet/releases/tag/v2.0.19
[2.0.18]: https://github.com/ghotihook/pyfastnet/releases/tag/v2.0.18
[2.0.17]: https://github.com/ghotihook/pyfastnet/releases/tag/v2.0.17
[2.0.16]: https://github.com/ghotihook/pyfastnet/releases/tag/v2.0.16
[2.0.15]: https://github.com/ghotihook/pyfastnet/releases/tag/v2.0.15
[1.2.3]: https://github.com/ghotihook/pyfastnet/releases/tag/v1.2.3
[1.2.0]: https://github.com/ghotihook/pyfastnet/releases/tag/1.2.0
