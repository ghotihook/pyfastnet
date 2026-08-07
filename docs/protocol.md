# The FastNet protocol — a language-agnostic reference

This document describes the B&G FastNet wire protocol itself, independent of
any implementation. It's the thing to read first if you're porting this
decoder to another language (Rust, JS, C, ...) — everything here is a
protocol fact, not a Python detail.

For the machine-readable specifics (exact channel numbers, byte layouts,
Signal K mappings), see [`fastnet_decoder/data/fastnet.json`](../fastnet_decoder/data/fastnet.json)
and its own [README](../fastnet_decoder/data/README.md). This document
explains the *shape* of the protocol; that file has the *data*. The Python
reference implementation is [`fastnet_decoder/interpreter.py`](../fastnet_decoder/interpreter.py).

Historical sources this protocol was originally reverse-engineered from:
[Oppedijk's B&G FastNet page](https://www.oppedijk.com/bandg/fastnet.html)
and [timmathews' C++ driver](https://github.com/timmathews/bg-fastnet-driver).
Everything below has been independently verified against real captured data
in this repo's test suite, not just copied from those sources.

## Physical layer

FastNet runs over a serial bus at **28,800 baud, 8 data bits, odd parity, 2
stop bits**. This document covers the byte-level framing on top of that
serial stream, not the electrical/serial details themselves.

## Frame envelope

Every frame, regardless of what it carries, has the same fixed shape:

```
byte:     0           1             2          3        4                5 .. 5+N-1   5+N
field:    to_address  from_address  body_size  command  header_checksum  body (N bytes)  body_checksum
```

- `to_address`, `from_address` — one byte each, identifying bus devices (see
  `fastnet.json`'s `addresses` lookup — e.g. `0xFF` = "Entire System",
  `0xFA` = "All 20/20s").
- `body_size` — one byte, the number of bytes in `body` (N above).
- `command` — one byte, what kind of frame this is (see `fastnet.json`'s
  `commands` lookup). The three that carry actual data are `0x01`
  (Broadcast — channel records, see below), `0x03` (LatLon — a position
  fix), and `0xC9` (Light Intensity — a backlight level). `0x0C` (Keep
  Alive) carries no useful data and should be ignored. Any other command
  byte is a frame type this protocol's reverse-engineering hasn't covered
  yet (pilot messages, NMEA-sourced data, ...) — its body layout is
  currently unknown.
- `header_checksum` — checksum (see below) over just the first 4 bytes
  (`to_address`, `from_address`, `body_size`, `command`).
- `body` — `body_size` bytes; its structure depends on `command` (see
  below).
- `body_checksum` — checksum over `body` alone.

Total frame length is `5 + body_size + 1`.

### Checksum

A one's-complement-style additive checksum:

```
checksum(bytes) = (0 - sum(bytes)) & 0xFF
```

i.e. sum every byte, negate, and keep only the low 8 bits. A valid frame's
header bytes checksum-match `header_checksum`, and its body bytes
checksum-match `body_checksum`, independently.

### Finding frame boundaries in a live byte stream

There's no start-of-frame marker — a receiver just has a continuous byte
stream and has to find frame boundaries by validating checksums. The
practical approach (see `fastnet_decoder/frame_buffer.py`): read a
tentative frame using the current buffer position's `body_size`/`command`
bytes, check both checksums, and if either fails, discard **one byte** from
the front of the buffer and retry from the new position. This naturally
resynchronizes after any corrupted or missed byte, at the cost of
occasionally being slow to recover on a very noisy line.

## Broadcast frames (command `0x01`) — channel records

A Broadcast frame's body is a sequence of **channel records** packed back
to back, with no separator or count — you consume them until the body runs
out of bytes:

```
[channel_id, format_byte, data_bytes...] [channel_id, format_byte, data_bytes...] ...
```

- `channel_id` — one byte, identifying *what* physical quantity this is
  (boat speed, depth, wind angle, ...). See `fastnet.json`'s `channels`
  table for every channel identified so far (114 as of this writing) — a
  channel byte not in that table is simply not yet identified; it's still
  safe to skip over (see below), you just don't know what it means yet.
- `format_byte` — one byte, encoding two independent things (see next
  section): *how* the following `data_bytes` are laid out, and a scaling
  divisor.
- `data_bytes` — a fixed number of bytes whose *count* is determined purely
  by `format_byte`'s low nibble (see the format-size table below) — this is
  true even for a format nibble whose byte *layout* isn't understood yet,
  which is what lets a decoder skip cleanly over unknown channels/formats
  without losing sync on the rest of the frame.

### `format_byte`'s bits

```
bit:    7 6 | 5 4 | 3 2 1 0
        └┬┘   ??    └──┬──┘
     divisor          format
     selector        template
```

- **Low nibble** (`format_byte & 0x0F`) selects which **format template**
  (below) describes the byte layout. There are 16 possible nibble values;
  9 have a known layout as of this writing (`0x01`–`0x08`, `0x0A`); `0x00`
  has a known *size* (4 bytes) but no known layout; `0x09` and the rest
  have never been observed at all.
- **Top two bits** (`format_byte >> 6`) select a **divisor**, independent
  of which format template is used: `0` → divide by 1, `1` → divide by 10,
  `2` → divide by 100, `3` → divide by 1000. This turns the raw integer
  pulled out of the data bytes into a properly-scaled value — e.g. raw
  integer `477` with divisor `100` means the value `4.77`. It also
  determines how many decimal places to use if you're formatting the value
  as a display string (divisor 100 → 2 decimal places).
- **Bits 4-5** — not understood; no observed effect so far.

### Format templates

Each entry below: how many `data_bytes` follow, and how to decode them. All
multi-byte integers are big-endian.

| Nibble | Size | Layout |
|---|---|---|
| `0x00` | 4 bytes | Unknown — never seen decoded meaningfully. |
| `0x01` | 2 bytes | A plain signed 16-bit integer, ÷ divisor. **Exception:** channel `0xB5` (Autopilot Mode) reinterprets these same 2 bytes completely differently — see "Autopilot Mode" below. |
| `0x02` | 2 bytes | An unsigned 10-bit integer packed as `(byte0 & 0x03) << 8 \| byte1`, ÷ divisor. |
| `0x03` | 2 bytes | `byte0` = a **segment code** (see "Segment display encoding" below), giving both the value's sign and a display decoration. `byte1` = an unsigned 8-bit magnitude, ÷ divisor. |
| `0x04` | 4 bytes | `byte0` = a status/flag byte, purpose unknown, ignored. `bytes 1-3` = an unsigned 24-bit integer, ÷ divisor. |
| `0x05` | 4 bytes | `byte0` = a status/flag byte, ignored. `byte1` = hours, `byte2` = minutes, `byte3` = seconds — a duration, stored as total seconds (not divided by the scaling divisor; this format is used for a running timer, not a scaled physical quantity). |
| `0x06` | 4 bytes | Each of the 4 bytes independently encodes one raw 7-segment display glyph (digit or letter) — see "Segment display encoding" below. There is **no separate numeric value** for this format; it's display-text-only, by protocol design. |
| `0x07` | 4 bytes | `byte0` = a status/flag byte, ignored. `byte1` = a segment code (sign + display decoration, same as format `0x03`). `bytes 2-3` = an unsigned 15-bit integer (`byte2`'s top bit is masked off/unused), ÷ divisor. |
| `0x08` | 2 bytes | A 7-bit segment code is packed into bits 7-1 of `byte0` (affects display decoration only, **not** sign — unlike formats `0x03`/`0x07`). A 9-bit unsigned integer is packed across bit 0 of `byte0` (its high bit) and all of `byte1` (its low 8 bits), ÷ divisor. |
| `0x09` | — | Never observed in captured data. |
| `0x0A` | 4 bytes | Two independent signed 16-bit integers, each ÷ divisor — by convention the first is treated as "the" value, but both are meaningful (e.g. a raw sensor reading alongside its calibrated counterpart). |

Worked example — Heading arrives as `channel_id=0x49`, `format_byte=0x08`,
`data_bytes=[0xCC, 0x29]`:

1. `format_byte & 0x0F = 0x08` → format `0x08`'s layout applies.
2. `format_byte >> 6 = 0` → divisor 1.
3. Segment code: `(0xCC & 0xFE) >> 1 = 0x66` → looked up as "°M" (magnetic
   bearing).
4. Value: bit 0 of `0xCC` (= 0) becomes the high bit, all of `0x29` (= 41)
   is the low 8 bits → 41. Divided by 1 → **value 41.0**.
5. Display text, decorated with the "°M" segment code → **"41°M"**.

### Segment display encoding

Several format templates (`0x03`, `0x06`, `0x07`, `0x08`) include one or
more bytes whose bit pattern corresponds to which segments of the original
B&G display hardware were lit — but the *meaning* of that pattern differs
by context:

**As a "segment code" (formats `0x03`, `0x07`, `0x08`)** — the pattern
doesn't represent a digit at all. It represents a small textual annunciator
shown alongside the numeric value on the physical display: a unit suffix
(`°M`, `°C`, `°F`), a sign indicator (`H`/`L` for heel to port/starboard,
`-`/`=` variants), or similar. Known codes are cataloged in `fastnet.json`'s
`segmentA` lookup (21 identified as of this writing, plus 2 confirmed as
"blank / no indicator shown", plus 2 more observed on the bus but not yet
identified). An unrecognized code decodes as the placeholder value `"TBC"`
("to be confirmed") rather than failing — new codes are still being found
during ongoing reverse-engineering.

**As a raw display digit (format `0x06` only)** — each byte's bit pattern
directly encodes one alphanumeric character exactly as it appeared on a
physical 7-segment-style B&G display. The bit-to-segment mapping (as
confirmed from captured data) is: `bit7`=segment e, `bit6`=g, `bit5`=f,
`bit4`=d, `bit3`=a, `bit2`=b, `bit1`=c, `bit0`=decimal point. Note that
B&G's hardware uses a **non-standard** segment choice for at least three
digits (`2`, `3`, `4`) compared to a "typical" 7-segment encoding — don't
assume a textbook 7-segment table will match without cross-checking against
`fastnet.json`'s `segmentB` table (14 glyphs identified as of this
writing, including the digits 0-9 seen so far and a handful of letters used
for units, e.g. `C` for Celsius).

### Autopilot Mode (channel `0xB5`) — the one special case

Every other channel decodes purely from its format template — `channel_id`
only matters for knowing what the value *means*, not *how* to decode it.
Channel `0xB5` is the sole documented exception: its format-`0x01` 16-bit
value is not a plain scaled number. It's a composite of two independent
pieces of information:

```
bit:  15 .......... 8 | 7 .......... 0
      engagement state | selected mode
```

- **High byte** (engagement state): `0x50` = Standby, `0x51` = Engaged,
  `0x59` = Compass steering (actively steering to a heading). When the
  high byte is `0x50` (Standby), the mode is always reported as "Standby"
  regardless of the low byte.
- **Low byte** (selected mode, only meaningful when engaged): looked up in
  `fastnet.json`'s `autopilotState` table — currently `0x01`=Compass,
  `0x02`=Power, `0x04`=Wind, `0x13`=NMEA Waypoint.

## LatLon frames (command `0x03`) — position fix

Not a channel record at all — the entire body is one ASCII text field:

```
byte:  0             1                   2 .. end
field: source marker  (format byte,      ASCII position-fix text
       (varies by      unused/ignored)
       GPS unit)
```

- Byte 0 varies by which GPS unit produced the fix (`0x47`, `0x4E`, ... have
  been observed) — it is **not** a channel id and must not be looked up
  against the channel table.
- Byte 1 is present but has no known meaning for this frame type.
- The remainder is an ASCII string of the form
  `DDMM.MMM<N|S>DDDMM.MMM<E|W>` — latitude as 2 digits of whole degrees
  plus minutes (with decimal fraction), a direction letter, then longitude
  as 3 digits of whole degrees (up to 180°) plus minutes, then its
  direction letter. No delimiter separates the latitude and longitude
  fields other than the direction letters themselves.
  Example: `3352.450S15113.920E` → 33°52.450′S, 151°13.920′E.

## Light Intensity frames (command `0xC9`) — backlight level

Also not a channel record — a single byte:

```
byte:  0
field: backlight level
```

Looked up in `fastnet.json`'s `backlightLevels` table: `0x00`=Off,
`0x01`=Low, `0x02`=Medium, `0x04`=High. Broadcast from a Pilot FFD to the
whole system (typically `to_address = 0xFF`, "Entire System").

## Known gaps (as of this writing)

- Format nibbles `0x00` (sized but layout unknown) and `0x09` (never
  observed at all) have no known decode.
- A handful of segment codes (`segmentA`/`segmentB` byte values) have been
  observed on the bus but not yet matched to a meaning — they decode as
  `"TBC"`.
- The "°T" (True bearing, as opposed to "°M" Magnetic) segment code has
  **never been observed in any captured frame** — no instrument
  configuration captured so far has broadcast a True-referenced bearing.
  The routing logic for layout-routed bearings (Heading, True Wind
  Direction, Tidal Set) currently defaults to the Magnetic path for any
  layout byte that isn't the confirmed "°M" code (`0x66`); True routing is
  expected to activate automatically the moment the "°T" byte value is
  captured and added to `segmentA`, with no other code change needed.
- Non-Broadcast, non-LatLon, non-Light-Intensity command bytes (pilot
  messages, NMEA-sourced data passed through the bus, etc.) have an
  unknown body structure. `fastnet_decoder`'s `probe_frame()` speculatively
  decodes them as if they were Broadcast channel records, purely to help a
  human eyeball whether that structure happens to hold — there's no
  confirmation that it actually does for any of these command types yet.
