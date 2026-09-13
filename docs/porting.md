# Implementing FastNet in another language

pyfastnet is two things kept apart on purpose: a **description** of the FastNet
protocol, [`fastnet_decoder/data/fastnet.json`](../fastnet_decoder/data/fastnet.json), and
a small **engine** that reads it. To decode FastNet somewhere else — Rust on a
microcontroller, JavaScript in a browser, C in a plotter — reuse the description
unchanged and write only the engine.

This guide is the engine's contract: everything an engine must do that the JSON doesn't
say, precisely enough to implement without reading any Python. An implementation is
correct when it reproduces [`conformance/vectors.json`](../conformance/README.md).

Related reading:

- [`protocol.md`](protocol.md) — the wire protocol itself: what the bytes mean.
- [`architecture.md`](architecture.md) — why the protocol is stored as data at all.
- [`fastnet_decoder/data/README.md`](../fastnet_decoder/data/README.md) — editing the schema.

## The model

```
                      ┌──────────────────── fastnet.json ────────────────────┐
                      │ formatSizeMap   formatTemplates   lookups   channels │
                      └──────┬────────────────┬──────────────┬─────────┬─────┘
                             │                │              │         │
 raw bytes ─► framing ─► record walk ─► decode a record ─► names ─► projection ─► {path: SI value}
              (§2)          (§3)            (§4)                       (§7)
```

Every box on the bottom row is engine; every table it consults is data. The division:

| In `fastnet.json` — reuse as-is | In the engine — you write this |
|---|---|
| All 114 channel names, and all address, command, segment-code and glyph tables | Framing: checksums, finding frames in a byte stream |
| How many bytes each format nibble occupies | Walking the records in a frame body |
| Each format's byte layout, as parameters for one of eight **ops** | What each of the eight ops *does* with those parameters |
| Every Signal K path, unit and conversion factor | Applying the projection rules and transforms |
| — | A short list of facts not yet in the schema ([§9](#9-facts-the-engine-holds)) |

The engine is small — pyfastnet's is about 500 lines of Python, most of it the eight ops
and the projection. It changes rarely; the description changes as the protocol is
discovered.

## Build order

Each step can be checked on its own before starting the next:

| Step | Implement | Check against `conformance/vectors.json` |
|---|---|---|
| 1 | Load the schema ([§1](#1-reading-fastnetjson)) | — |
| 2 | Framing ([§2](#2-framing)) | every `streams[*]` entry |
| 3 | Record walk and the eight ops ([§3](#3-broadcast-frames-walking-the-records)–[§5](#5-the-autopilot-override)) | `frames[*].decode` for command `0x01` |
| 4 | LatLon and Light Intensity ([§6](#6-latlon-and-light-intensity-frames)) | `frames[*].decode` for commands `0x03`, `0xC9` |
| 5 | Projection ([§7](#7-projection-to-signal-k)) | every `frames[*].signalk` |

Section numbers below name the reference function in
[`interpreter.py`](../fastnet_decoder/interpreter.py) or
[`frame_buffer.py`](../fastnet_decoder/frame_buffer.py), for when you want to compare.

---

## 1. Reading `fastnet.json`

- **Byte values are hex strings** — `"0x41"`, in keys (channel ids, addresses, segment
  codes) and in some values (bit masks). Parse base 16. The schema writes them upper case.
- **Keys beginning with `_`** (`"_comment"`) are documentation. Ignore them wherever they
  appear.
- `scaling` is keyed by **decimal** strings: `divisorByTopTwoBits` by `"0"`–`"3"`,
  `decimalPlacesByDivisor` by the divisor (`"1"`, `"10"`, `"100"`, `"1000"`).
- **Documentation-only content** an engine need not read: the whole `messages` section;
  `statusByte` in a template (it names a byte the op ignores); `ref` in an `overrideEnum`
  transform; the value of `routedBy` (always `"layout"`). A `segmentDisplay` template's
  `lookup` names its glyph table — always `segmentB`.
- **Reject what you can't carry out, at load time.** An `op`, transform `type` or override
  name your engine doesn't implement means the schema is newer than the engine. Failing
  loudly at load is better than wrong output at sea. (pyfastnet does this in
  [`tools/validate_schema.py`](../tools/validate_schema.py), run by its test suite; its
  `OP_SPECS` table lists every op's required fields.)

## 2. Framing

The wire format is in [`protocol.md`](protocol.md#frame-envelope): a 5-byte header
(`to_address`, `from_address`, `body_size`, `command`, `header_checksum`), then
`body_size` bytes of body, then `body_checksum`. A checksum is
`(0 − sum of the bytes) & 0xFF`.

There is no start-of-frame marker, so frames are found by trial (`FrameBuffer.get_complete_frames`):

```
while the buffer holds at least 6 bytes:
    length = 5 + buffer[2] + 1
    if the buffer holds fewer than length bytes:
        stop and wait for more data
    if checksum(buffer[0..3]) != buffer[4]:              drop 1 byte; continue
    if checksum(buffer[5..length-2]) != buffer[length-1]: drop 1 byte; continue
    frame = remove the first length bytes
    dispatch(frame)
```

Two details matter if your frame sequence is to match the vectors exactly:

- **Wait for the full length before checking either checksum** — including the header's.
  Mid-stream this makes no difference, but at the end of a capture a corrupt byte claiming
  a long body leaves the reference waiting, and any frames after it are never found.
- **Chunking doesn't matter.** Feeding a capture line by line or all at once gives the same
  frames, as long as your buffer doesn't overflow. pyfastnet keeps at most 8192 bytes,
  discarding the oldest; one capture line is far smaller.

**Dispatch** looks the command byte up in `lookups.commands`:

| Command name | Action |
|---|---|
| in `lookups.ignoredCommands` (`Keep Alive`) | discard silently |
| `Broadcast` | decode channel records — [§3](#3-broadcast-frames-walking-the-records) |
| `LatLon` | decode a position fix — [§6](#6-latlon-and-light-intensity-frames) |
| `Light Intensity` | decode a backlight level — [§6](#6-latlon-and-light-intensity-frames) |
| anything else | not decoded (pilot messages and others; body layout unknown) |

A stream vector's frames are exactly the frames that reach dispatch: checksum-valid, and
not in `ignoredCommands`.

## 3. Broadcast frames: walking the records

`decode_frame`. The body (`frame[5 .. length-2]`) is a run of records with no separator
and no count:

```
[channel_id, format_byte, data bytes…] [channel_id, format_byte, data bytes…] …
```

1. If the body is shorter than 2 bytes, or its length isn't `body_size`, the frame is an
   **error**.
2. At each position: if only one byte remains, the frame is an **error**. Otherwise read
   `channel_id` and `format_byte`; the data length is `formatSizeMap[format_byte & 0x0F]`,
   or 0 if the nibble isn't listed. If fewer bytes remain than that, the frame is an
   **error**.
3. Decode the record ([§4](#4-decoding-one-record)) and store it under the channel's
   name. If two records in one frame share a name, the later one wins.

An **error** means the whole frame is dropped: nothing is emitted from it. The reference
returns `{"error": "<message>"}`; the message text is not part of the contract.

A decoded frame is:

```json
{
  "to_address":   "Entire System",
  "from_address": "Normal CPU (Depth Board in H2000)",
  "command":      "Broadcast",
  "values": {
    "Boatspeed (Knots)": {"channel_id": "0x41", "value": 4.77,  "display_text": "4.77",       "layout": null},
    "Boatspeed (Raw)":   {"channel_id": "0x42", "value": 492.0, "display_text": "492 / 2092", "layout": null}
  }
}
```

**Names** come from `lookups.addresses`, `lookups.commands` and `lookups.channelNames`.
A missing entry becomes `"Unknown (0xNN)"` — the byte as two upper-case hex digits.

## 4. Decoding one record

`decode_channel_value`. Inputs: `channel_id`, `format_byte`, and the record's data bytes.
Output: `{"channel_id": "0xNN", "value", "display_text", "layout"}`, or **null** when the
record can't be decoded.

1. If there are no data bytes, the record is **null**. (This happens for a nibble with no
   `formatSizeMap` entry. Because its size is unknown the walk continues from the very
   next byte, so what follows in that frame is probably misread — a protocol gap, not an
   engine choice.)
2. `nibble = format_byte & 0x0F`. `divisor = scaling.divisorByTopTwoBits[format_byte >> 6]`,
   `decimals = scaling.decimalPlacesByDivisor[divisor]`.
3. If `channels["0xNN"].overrides` has an entry for this nibble (`"0x01"`), run the named
   override ([§5](#5-the-autopilot-override)) instead of a template.
4. Otherwise take `formatTemplates[nibble]`. If there is none, or its `op` is
   `"unsupported"`, the record is **null**.
5. Run the op (below).

`channel_id` in the output is always two upper-case hex digits: `"0x4A"`, never `"0x4a"`.

### Helpers the ops share

| Name | Definition |
|---|---|
| **int(start, end, signed)** | Bytes `data[start]` up to but not including `data[end]`, as one big-endian integer; two's complement if `signed`. |
| **pieces(list)** | For each piece `{byte, mask, shiftLeft}`: `(data[byte] & mask) << shiftLeft`. OR them together. Always unsigned. |
| **layout(code)** | `lookups.segmentA[code]`. That is a token string such as `"°M"` or `"H[data]"`, or **null** where the entry is null (a confirmed-blank indicator). A code with **no entry** gives the string `"TBC"`. |
| **sign(layout)** | `lookups.layoutSign[layout]` if present (always −1), otherwise +1 — including for null and `"TBC"`. |
| **number(v)** | `v` in fixed-point notation with `decimals` digits after the point. Since `decimals` is always log₁₀ of the divisor, this is the raw integer with a decimal point inserted: raw 477 ÷ 100 → `"4.77"`, raw −5 ÷ 10 → `"-0.5"`, raw 7 ÷ 1000 → `"0.007"`, raw 41 ÷ 1 → `"41"`. |
| **render(layout, text)** | Look up `lookups.layoutDisplay[layout]`. If the layout is null or has no rule, return `text` unchanged. Otherwise: if the rule has `stripSign`, remove leading `-` from `text`; then return `prefix + text + suffix` (each optional). |

**Apply the sign in integers, then divide.** In `signedLayoutValue`, multiply the sign and
the magnitude as integers before dividing by the divisor. A negative sign with a magnitude
of 0 is then plain 0, with no minus sign in its text (`"0"`, `"0.0"`) — never −0. Real
captures do this: True Wind Angle reading 0 with a negative indicator. Where the multiply
happens in floating point (JavaScript, or a C `double`), −1 × 0 gives −0, which formats as
`"-0"` — normalise it to 0.

### The eight ops

| `op` | Template fields | value | display_text | layout |
|---|---|---|---|---|
| `scaledInt` | `signed`, `valueBytes: [s, e]` | int(s, e, signed) ÷ divisor | number(value) | null |
| `scaledBitfield` | `pieces` | pieces ÷ divisor | number(value) | null |
| `signedLayoutValue` | `layoutByte`, and `pieces` *or* `valueBytes` | sign(L) × magnitude ÷ divisor, where magnitude is pieces, or int(s, e, **unsigned**) | render(L, number(value)) | L = layout(data[layoutByte]) |
| `layoutValue` | `layoutBits: {byte, mask, shiftRight}`, `pieces` | pieces ÷ divisor — **no sign applied** | render(L, number(value)) | L = layout((data[byte] & mask) >> shiftRight) |
| `durationHMS` | `hByte`, `mByte`, `sByte` | h×3600 + m×60 + s, in seconds — **divisor not applied** | duration(value), below | null |
| `segmentDisplay` | `lookup` | **null**, always | each data byte looked up in that table (`"TBC"` if absent), concatenated | null |
| `pairedScaledInt` | `signed`, `firstBytes`, `secondBytes` | a = int(first) ÷ divisor | number(a) + `" / "` + number(b), where b = int(second) ÷ divisor | null |
| `unsupported` | — | the record is **null** | | |

`scaledBitfield` templates carry `"signed": false`; the value is unsigned either way.

**duration(seconds)** — hours are not zero-padded; minutes and seconds are; whole days
are split off:

```
days = seconds ÷ 86400 (integer), rest = seconds mod 86400
text = H:MM:SS of rest                       e.g. "7:05:09"
if days ≥ 1: text = "<days> day, " + text    ("1 day, 21:29:09")  — "days" when more than 1
```

Real captures reach 1 day and more: the Timer channel runs freely for tens of hours.

## 5. The autopilot override

Channel `0xB5` (Autopilot Mode) in format nibble `0x01` names the override
`"autopilotMode"`: its 16 bits are two separate pieces of information, not one number
([protocol.md](protocol.md#autopilot-mode-channel-0xb5--the-one-special-case)).

```
raw   = int(0, 2, signed)          value = raw          (divisor not applied)
high  = data[0]                    low   = data[1]
display_text = "Standby"                                  if high == 0x50
             = autopilotState["0xLL"].displayText         if high is 0x51 or 0x59 and low has an entry
             = "Unknown (<raw>)"                          otherwise — raw as signed decimal
layout = null
```

## 6. LatLon and Light Intensity frames

Neither carries channel records. Both produce the same frame shape as §3, with one entry
in `values`.

**LatLon** (`decode_ascii_frame`). Body byte 0 is a marker that varies by GPS unit — *not*
a channel id. Byte 1 is ignored. The rest is ASCII text such as `3352.450S15113.920E`.

```
values = { "LatLon": { "channel_id": "0x<marker>", "value": null,
                       "display_text": <bytes 2… as ASCII, whitespace trimmed>, "layout": null } }
```

The entry's name is the command name. An empty body, or a byte outside ASCII, makes the
frame an error. ("Whitespace" is the reference's definition, which includes bytes
`0x1C`–`0x1F` as well as the usual space, tab, CR, LF, VT and FF.)

**Light Intensity** (`decode_light_frame`). Body byte 0 is the level:

```
values = { "Backlight": { "channel_id": null, "value": <level as a number>,
                          "display_text": backlightLevels["0xLL"] or "Unknown (<level in decimal>)",
                          "layout": null } }
```

An empty body is an error.

## 7. Projection to Signal K

`project`. Turns a decoded frame into `{signalk_path: value}`. It takes one setting,
`battery_id` (default `"house"`).

**LatLon frames** are handled whole: for each entry, parse its `display_text` as a
position (below); if that succeeds, emit `navigation.position` = `{"latitude",
"longitude"}`. Nothing else.

**Every other frame** — take each entry in `values`, in order, and apply the first rule
that matches:

| # | If… | Then |
|---|---|---|
| 1 | the entry is null (an undecodable record) | skip it |
| 2 | its `channel_id` is null (Backlight) | skip it |
| 3 | `channels["0xNN"]` has no `signalk` block | if value isn't null, emit `bandg.unknown.0xNN` = the raw value, untransformed |
| 4 | `signalk.drop` is true | skip it |
| 5 | `signalk.collapsedInto` is present | skip it |
| 6 | `signalk.fallbackGroup` is present | keep it as a candidate (below); emit nothing yet |
| 7 | `signalk.transform.type` is `"overrideEnum"` | emit `signalk.path` = the autopilot state (below), unless that is none |
| 8 | `signalk.routedBy` is present | path = `routes["°T"].path` if the entry's layout is exactly `"°T"`, otherwise `routes["°M"].path`; emit it |
| 9 | otherwise | path = `signalk.path`, with `{id}` replaced by `battery_id` if `pathParam` is present; emit it |

"Emit" in rules 8 and 9 means: null if the value is null, else transform(value).

**Fallback candidates** (depth, sent as metres, feet and fathoms). After the loop, take the
candidate with the lowest `fallbackPriority` whose value isn't null — on a tie, the first
seen — and emit its `signalk.path` = transform(value). If every candidate's value is null,
emit nothing. (Unlike rules 8–9, a missing depth is absent rather than null.) The
reference treats every `fallbackGroup` member as one group; today there is only `depth`.

**Transforms**, computed in exactly this order so results match bit for bit:

| `type` | Result |
|---|---|
| `identity` | value |
| `scale` | value × `factor` |
| `affine` | value × `scale` + `offset` (`scale` defaults to 1, `offset` to 0) |

**Autopilot state** (rule 7): from the decoded value, `raw` as an integer, `high = (raw >> 8)
& 0xFF`, `low = raw & 0xFF`. High `0x50` → `"standby"`. High `0x51` or `0x59` →
`autopilotState["0xLL"].signalk` if there is an entry, otherwise none. Anything else →
none.

**Position parsing** (`parse_position`): find the latitude letter (`N` or `S`) and the
longitude letter (`E` or `W`); if either is missing, there is no position. Latitude is the
text before its letter: the first 2 characters are whole degrees, the rest are minutes
(÷ 60). Longitude is the text between the two letters: the first **3** characters are whole
degrees, the rest are minutes. `S` and `W` make the value negative. Anything that doesn't
parse gives no position.

Minutes come with 3 decimals or 2, and in the 2-decimal form a space separates each number
from its letter — `3352.450S15113.920E` and `1646.61 S17920.23 E` are both real
([protocol.md](protocol.md#latlon-frames-command-0x03--position-fix)). Ignore whitespace
around each number before converting it.

**What FrameBuffer queues.** In its default mode, pyfastnet queues `{to_address,
from_address, command, values: <projection>}`, and only when the projection isn't empty.
A Backlight frame therefore never appears. With `project=False` it queues the decoded
frame itself, for every frame that isn't an error.

## 8. Units (optional)

pyfastnet's `unit_for(path)` is a convenience, not part of decoding. It returns the
`unit` of the channel whose `signalk.path` (without `pathParam`) or one of whose
`routes[*].path` equals the path, and otherwise: `navigation.position` → `"deg"`,
`steering.autopilot.state` → `"enum"`, `electrical.batteries.*.voltage` → `"V"`, anything
else → `""`.

## 9. Facts the engine holds

The schema holds nearly every protocol fact, but not quite all. A port must copy these
from this guide, because `fastnet.json` doesn't contain them:

| Fact | Section |
|---|---|
| The frame envelope, the checksum formula and the resync rule | §2 |
| Which command names dispatch to which decoder | §2 |
| The placeholder strings `"Unknown (0xNN)"`, `"Unknown (n)"`, `"TBC"` | §3, §4, §6 |
| Number and duration formatting | §4 |
| The autopilot composite: high byte `0x50` = standby, `0x51`/`0x59` = engaged | §5, §7 |
| The LatLon body layout and position text format | §6, §7 |
| The synthetic `"Backlight"` entry | §6 |
| Magnetic as the default route, and `"°T"` as the token that selects True | §7 |
| `battery_id` defaulting to `"house"` | §7 |
| The unit fallbacks | §8 |

Each is stable and small. They are candidates to move into the schema one day; until
then, this table is the complete list.

## 10. Checking your implementation

[`conformance/vectors.json`](../conformance/README.md) holds expected output produced by
pyfastnet from the recorded captures:

- **`streams`** — for each file in [`captures/`](../captures/README.md), how many frames
  your framing must find and a SHA-256 of the exact sequence. This checks §2.
- **`frames`** — about 70 frames chosen so that together they exercise every channel,
  format, layout, sign, command, address and Signal K path the captures contain, plus a few
  synthetic ones. Each has its expected `decode` (§3–§6) and `signalk` (§7).

[`conformance/README.md`](../conformance/README.md) gives the file format and the
comparison rules. To see the reference output for any other frame, run
`python examples/inspect_frame.py <hex>` in a checkout.

## 11. Staying in step with pyfastnet

Copy `fastnet.json` and `vectors.json` **from the same commit**: `vectors.json` records the
schema's SHA-256 in `meta.schema_sha256`, so you can check they are a pair.

Most changes to pyfastnet are discoveries recorded in the schema — a new channel, a segment
code or glyph, an address, a Signal K path or unit, a corrected factor or byte layout. Those
need no engine change: take the new `fastnet.json` and `vectors.json`, and your tests show
whether you still agree. A change that *does* need engine work — a new op, transform type,
override or projection rule — is marked **Engine change** in the
[CHANGELOG](../CHANGELOG.md), and this guide is updated in the same commit.
