# fastnet.json — how to read and edit this file

This file is the single source of truth for the FastNet protocol, as
currently understood. `fastnet_decoder/interpreter.py` reads it at import
time and contains no protocol-specific facts of its own — every channel
name, byte layout, and Signal K mapping lives here as data.

**If you've identified a new channel, a new segment-display code, or fixed
a wrong Signal K mapping: edit this file directly, then run the test suite.**
You do not need to touch any Python code unless the new discovery needs a
genuinely new byte layout (see "formatTemplates" below) — that's rare.

## Top-level sections

```
{
  "scaling":         how format_byte's top two bits select a divisor
  "formatSizeMap":   format nibble -> how many data bytes the record has
  "formatTemplates": format nibble -> how to decode those bytes
  "lookups":         small reference tables (addresses, commands, segment codes, ...)
  "channels":        channel id -> name + Signal K mapping
  "messages":        reference-only notes on the two non-channel frame types
}
```

### `scaling`

Every format byte's top two bits (`format_byte >> 6`) select a divisor,
independent of which format template is used. `divisorByTopTwoBits` maps
that 2-bit number (0-3) to the divisor; `decimalPlacesByDivisor` maps the
divisor to how many decimal places to show when formatting the value. You
will not need to edit this — it's a fixed, already-complete part of the
protocol.

### `formatSizeMap`

Maps a format byte's low nibble (`format_byte & 0x0F`, as a hex string like
`"0x08"`) to how many data bytes follow it in the wire record. Used to know
how many bytes to consume, even for a nibble whose layout isn't understood
yet (`formatTemplates` for that nibble would be `"unsupported"`, but its
size is still known, so the frame walker can skip over it correctly and
keep decoding the rest of the frame).

### `formatTemplates`

The heart of the schema: one entry per format nibble, describing exactly
how to turn its data bytes into a value. Every template has an `"op"` field
naming which decoding recipe to use — see the big comment block above
`decode_channel_value()` in `interpreter.py` for what each `op` does, with
a worked example. The current op vocabulary (`scaledInt`, `scaledBitfield`,
`signedLayoutValue`, `layoutValue`, `durationHMS`, `segmentDisplay`,
`pairedScaledInt`, `unsupported`) covers every format nibble seen in
captured data so far. **You should essentially never need to add a new
template** — if you've found a channel using an already-known format
nibble, it already has a template; just add the channel to `"channels"`
below. A new template is only needed if you discover an entirely new byte
layout that none of the existing ones describe.

### `lookups`

Small reference tables, each a plain `{"0xHH": value, ...}` map (or, for
`segmentA`/`layoutSign`/`layoutDisplay`, a map keyed by a "layout token"
string like `"°M"` or `"H[data]"` instead of a byte code — see below):

- `addresses` — FastNet bus address byte → device/group name.
- `commands` — command byte → command name (`Broadcast`, `LatLon`, ...).
- `ignoredCommands` — command names that should be silently skipped.
- `backlightLevels` — the single data byte of a Light Intensity frame → level name.
- `channelNames` — channel id → human-readable name. **Adding a newly
  identified channel usually means adding one entry here, plus one entry
  under `"channels"` below.**
- `segmentA` — a "segment code" byte (found inside certain format
  templates) → either `null` (a confirmed-blank display, no indicator) or a
  `{"sign": 1 or -1, "prefix": "...", "suffix": "..."}` object. `sign`
  affects the actual decoded *value* for some formats; `prefix`/`suffix`
  only affect the human-readable `display_text` string. Bytes not listed
  here decode as the literal string `"TBC"` ("to be confirmed") — see
  `_layout_for()` in `interpreter.py`.
- `segmentB` — a raw 7-segment-display byte → the digit/letter it represents.
  Used only by channels that arrive purely as a display string (format
  `0x06`), which never carry a separate numeric value.
- `layoutSign` — maps a layout token string (the same tokens `segmentA`
  produces) to `-1` if that token means "negative value". Any token not
  listed here is positive.
- `layoutDisplay` — maps a layout token string to how to decorate a
  formatted number with it (a prefix and/or suffix character, and
  sometimes `"stripSign": true`). See `_render_display()` in
  `interpreter.py` for the full explanation, including why `H[data]` and
  `L[data]` render differently despite both meaning "negative".
- `autopilotState` — channel 0xB5's low byte → `{"displayText": ..., "signalk": ...}`.
  See "channels" below for why 0xB5 is special.

### `channels`

One entry per channel id (as a hex string, e.g. `"0x41"`):

```json
"0x41": {
  "name": "Boatspeed (Knots)",
  "signalk": {
    "path": "navigation.speedThroughWater",
    "unit": "m/s",
    "transform": {"type": "scale", "factor": 0.514444}
  }
}
```

- `"name"` — required. The human-readable channel name.
- `"signalk"` — optional. If present, describes where this channel's value
  belongs in Signal K:
  - `"path"` / `"unit"` / `"transform"` — the common case. `transform` is
    one of `{"type": "identity"}` (already in SI units), `{"type": "scale",
    "factor": N}` (multiply by N), or `{"type": "affine", "scale": N,
    "offset": M}` (multiply then add — used for °C → K).
  - `"routedBy": "layout", "routes": {"°M": {...}, "°T": {...}}` — this
    channel's Signal K path depends on which layout byte it arrived with
    (e.g. Heading routes to `headingMagnetic` or `headingTrue`).
  - `"fallbackGroup"` / `"fallbackPriority"` — this channel is one of
    several redundant sources for the same physical quantity (currently
    only depth: metres/feet/fathoms); the lowest `fallbackPriority` number
    among whichever of them showed up in a given frame wins.
  - `"pathParam": "id"` — the path contains a `{id}` placeholder to be
    filled in at decode time (currently only the battery voltage path).
  - `"collapsedInto": "some.other.path"` — this channel is a redundant
    unit-variant of another one; its readings are dropped, not projected.
  - `"drop": true` — deliberately excluded (a protocol/control channel,
    not vessel data).
- `"overrides"` — optional, and should almost never be needed. Maps a
  format-nibble hex string to a named override function implemented in
  `interpreter.py`'s `_OVERRIDES` dict. Currently only channel `0xB5`
  (Autopilot Mode) uses this, because its 16-bit value is a composite of
  two separate pieces of information rather than a plain scaled number. If
  you find a similar case, you'll need to add both the schema entry here
  *and* a new function in `interpreter.py` — this is the one situation that
  genuinely requires a Python code change, not just a data edit.

A channel with **only** a `"name"` (no `"signalk"` key) is a known,
decodable channel that hasn't been mapped to a Signal K path yet. It still
decodes fine — `project()` will just emit it under a generic
`bandg.unknown.0x<id>` path rather than dropping it.

### `messages`

Reference documentation for the two frame types that aren't made of channel
records at all — LatLon (an ASCII position fix) and Light Intensity (a
single backlight-level byte). **This section is not read by
`interpreter.py`** — those two frame types are simple enough that
`decode_ascii_frame()` and `decode_light_frame()` implement them directly
in Python. It's kept here purely so the wire format is documented in one
place alongside everything else.

## `_comment` fields

JSON has no native comment syntax. Any `"_comment"` key you see is a plain
documentation string, ignored by `interpreter.py` — add one wherever a
value needs explaining, the same way you'd add a code comment.
