# pyfastnet

A Python library for decoding the **FastNet** protocol used by B&G Hydra / H2000
instruments. Feed it raw bytes from the Fastnet bus and it handles
synchronisation, checksum validation, and decoding — returning instrument data as
**Signal K paths in SI units**, ready for further processing.

The protocol itself is kept as data —
[`fastnet.json`](https://github.com/ghotihook/pyfastnet/blob/main/fastnet_decoder/data/fastnet.json) —
separate from the Python that reads it, so the same description can drive a decoder
in any language. See [How it works](#how-it-works-the-protocol-is-data).

> **Upgrading from v2?** v3.0 changed the output format to `{signalk_path: SI_value}`
> (e.g. `navigation.speedThroughWater = 3.6`) from the v2 name-keyed
> `{value, display_text, layout}` dicts — see **Output format** below. The full v2-style
> decode is still available via `FrameBuffer(project=False)`. Release history is in
> [CHANGELOG.md](https://github.com/ghotihook/pyfastnet/blob/main/CHANGELOG.md).

Developed for personal use and published for general interest. Runs on Raspberry
Pi, macOS, or Linux.

## Quick start

```bash
pip install pyfastnet
```

```python
#!/usr/bin/env python3
import serial
from fastnet_decoder import FrameBuffer

fb = FrameBuffer()

ser = serial.Serial(
    port="/dev/ttyUSB0",
    baudrate=28800,
    bytesize=serial.EIGHTBITS,
    stopbits=serial.STOPBITS_TWO,
    parity=serial.PARITY_ODD,
    timeout=0.1,
)

try:
    while True:
        data = ser.read(256)
        if not data:
            continue
        fb.add_to_buffer(data)
        fb.get_complete_frames()
        while not fb.frame_queue.empty():
            frame = fb.frame_queue.get()
            for path, value in frame["values"].items():
                print(path, value)   # e.g. navigation.speedThroughWater 3.6
finally:
    ser.close()
```

Serial settings for a B&G Fastnet bus are **28,800 baud, 8 data bits, odd parity,
2 stop bits**. (`serial` is [pyserial](https://pypi.org/project/pyserial/); pyfastnet
itself has no dependencies.)

## Try it without a boat

The repository includes real recorded bus traffic in
[`captures/`](https://github.com/ghotihook/pyfastnet/tree/main/captures) (it isn't in
the pip package). Clone it and replay one:

```bash
git clone https://github.com/ghotihook/pyfastnet.git
cd pyfastnet
python examples/replay_capture.py captures/big_with_ap_actions.txt
```

This feeds the recording through `FrameBuffer` exactly as a serial port would, and
prints the latest value and unit of every path:

```
2018 frames from big_with_ap_actions.txt, 42 paths

bandg.navigation.courseThroughWater                                        5.5501  rad
bandg.navigation.deadReckoning.course                                      5.5851  rad
…
```

To see how a single frame decodes:

```bash
python examples/inspect_frame.py ff010a01f54192f9dd420a01ec082cea
```

## The Fastnet toolkit

Three projects stack together — pick the layer that matches where you want the
data to end up:

| Project | What it does | Use it when |
|---|---|---|
| **pyfastnet** *(this library)* | **Decoder.** Turns raw Fastnet bytes into Signal K paths in SI units. | You're writing your own Python and want the decoded data. |
| [fastnet2ip](https://github.com/ghotihook/fastnet2ip) | **Serial → network.** Broadcasts decoded data over UDP as NMEA 0183 or NMEA 2000 (over IP). | Feeding Signal K, OpenCPN, or a plotter over WiFi / Ethernet. |
| [fastnet2n2k](https://github.com/ghotihook/fastnet2n2k) | **Serial → physical NMEA 2000 bus.** Transmits PGNs onto a CAN backbone via SocketCAN. | Wiring into a real NMEA 2000 network / chartplotter. |

```
                          ┌─ fastnet2ip   → UDP (NMEA 0183 / NMEA 2000 over IP) → Signal K, OpenCPN, plotters
B&G Fastnet bus ─(serial)─→ pyfastnet ─┤
                          └─ fastnet2n2k → SocketCAN (NMEA 2000 PGNs)           → CAN backbone, chartplotter
```

pyfastnet is the **engine** at the bottom of the stack. If you only want the
decoded data on your network or NMEA 2000 bus — including running it as an
always-on systemd service — use one of the companion apps; they handle the serial
port, a live data store, rate limiting, and output for you.

## Output format

Each decoded frame is a dict with `to_address`, `from_address`, `command`, and
`values`. `values` maps **Signal K paths to SI values** — one canonical entry per
physical quantity:

```python
{
  "to_address":   "Entire System",
  "from_address": "Normal CPU (Wind Board in H2000)",
  "command":      "Broadcast",
  "values": {
    "environment.wind.speedApparent":     4.6,    # m/s
    "environment.wind.angleApparent":     0.419,  # radians
    "environment.wind.directionMagnetic": 1.239,  # radians
    "navigation.speedThroughWater":       3.19,   # m/s
  }
}
```

Units follow the Signal K spec: angles in **radians**, speed in **m/s**, distance
in **metres**, temperature in **Kelvin**, pressure in **Pascals**. A value is a
`float` (SI), a `str` enum (e.g. `steering.autopilot.state` → `"standby"`), a
position object, or `None` when unavailable.

Redundant unit-variant channels the bus sends (feet/fathoms depth, knots wind, °F)
are collapsed to one canonical path. B&G-proprietary channels with no standard
Signal K path — including the pre-calibration `raw` sensor values — are emitted
under a `bandg.*` namespace (e.g. `bandg.wind.rawAngleApparent`).

### Units and the full path map

Every emitted path has a canonical SI unit, available programmatically:

```python
from fastnet_decoder import unit_for
unit_for("navigation.speedThroughWater")   # "m/s"
unit_for("navigation.headingMagnetic")      # "rad"
unit_for("environment.water.temperature")   # "K"
unit_for("navigation.position")             # "deg"
```

The master reference — every B&G channel number → name → Signal K path + unit — is
`channel_map()`, derived from the protocol schema so it can't drift:

```python
from fastnet_decoder import channel_map
channel_map()[0x41]
# {'name': 'Boatspeed (Knots)', 'path': 'navigation.speedThroughWater',
#  'unit': 'm/s', 'kind': 'standard'}
```

It is rendered as a table in
[`docs/channel_map.md`](https://github.com/ghotihook/pyfastnet/blob/main/docs/channel_map.md).

### Position

Position frames are emitted as `navigation.position`, a decimal-degree object
(negative for S / W):

```python
"navigation.position": {"latitude": -33.8742, "longitude": 151.2320}
```

### True vs Magnetic

The reference is carried by the **path**, not a separate field:
`navigation.headingMagnetic` vs `navigation.headingTrue`,
`environment.wind.directionMagnetic` vs `directionTrue`,
`environment.current.setMagnetic` vs `setTrue`. The decoder selects the right path
from the display's indicator symbol at decode time. (The raw stream carries no
magnetic variation or deviation, so it cannot convert between the two.)

### Complete (rich) decode

`FrameBuffer(project=False)` queues the full internal decode instead of the Signal K
projection. Each value is then a dict — `value`, `display_text`, `layout`,
`channel_id` — keyed by human-readable channel name (the v2 format). Useful for
debugging and reverse-engineering; `display_text` and `layout` are not exposed in
the default Signal K output.

You can also project a single decoded frame yourself:

```python
from fastnet_decoder import decode_frame, project
rich = decode_frame(raw_frame_bytes)      # complete decode
si = project(rich)                        # {signalk_path: SI_value}
```

### Debug API

```python
from fastnet_decoder import set_log_level
import logging
set_log_level(logging.DEBUG)
```

```python
fb.get_buffer_size()      # bytes currently in buffer
fb.get_buffer_contents()  # hex string of buffer contents
```

## Building a tool on pyfastnet

### The public API

Everything below is importable from `fastnet_decoder`.

| Name | What it does |
|---|---|
| `FrameBuffer(max_buffer_size=8192, max_queue_size=1000, project=True)` | Feed raw bytes with `add_to_buffer()`; `get_complete_frames()` finds, validates and decodes frames onto `frame_queue`. |
| `decode_frame(frame)`, `decode_ascii_frame(frame)`, `decode_light_frame(frame)` | Complete decode of one Broadcast, LatLon or Light Intensity frame (bytes, checksums included). |
| `project(decoded, battery_id="house")` | Turn a complete decode into `{signalk_path: SI_value}`. |
| `unit_for(path)` | The SI unit string for an emitted path. |
| `channel_map()` | Every channel id → name, path, unit and how it is handled. |
| `logger`, `set_log_level(level)` | The `pyfastnet` logger (INFO by default), and a setter taking a name (`"DEBUG"`) or a `logging` constant. |

### Things worth knowing

- **Frames are partial.** Each frame carries only a few paths, so most tools keep a
  latest-value store and update it as frames arrive —
  [`examples/replay_capture.py`](https://github.com/ghotihook/pyfastnet/blob/main/examples/replay_capture.py)
  does exactly that.
- **`None` means "on the bus, but no number".** Some installations broadcast certain
  channels — heel, trim, air temperature, pressure — only as 7-segment display text,
  never as a number. Those paths arrive as `None`
  ([why](https://github.com/ghotihook/pyfastnet/blob/main/docs/signalk-design.md#notes), note 12).
- **Drain the queue.** `frame_queue` holds at most `max_queue_size` frames; when it's
  full, new frames are dropped with a warning. Empty it after each `get_complete_frames()`.
- **Feed from one thread.** Call `add_to_buffer()` and `get_complete_frames()` from the
  same thread. `frame_queue` is a standard `queue.Queue`, so another thread may consume it.
- **Battery id.** Battery voltage is emitted as `electrical.batteries.house.voltage`. For
  a different id, use `FrameBuffer(project=False)` and call
  `project(frame, battery_id="start")` yourself.
- **Vendor paths.** Values with no standard Signal K path are under `bandg.*`, and
  channels that decode but haven't been mapped yet under `bandg.unknown.0x<id>`. One
  `path.startswith("bandg.")` test keeps or drops them all.
- **Backlight** (Light Intensity frames) has no Signal K path, so it appears only in the
  complete decode.

## How it works: the protocol is data

FastNet was defined by B&G decades ago and burned into instruments; this project's work
is *discovering* it. So the discoveries are written down as a description of the
protocol —
[`fastnet_decoder/data/fastnet.json`](https://github.com/ghotihook/pyfastnet/blob/main/fastnet_decoder/data/fastnet.json) —
and the Python is a small, generic engine that reads that description and holds almost no
protocol facts of its own.

Here is one channel, in full:

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

Each reading on the bus carries a format byte that selects one of a handful of byte
layouts, also described in the file. The engine unpacks the bytes with that layout,
converts knots to m/s with the factor, and emits the path. Identifying a new channel or
correcting a mapping is an edit to this file, not to code.

Why it's built this way, and what that cost:
[`docs/architecture.md`](https://github.com/ghotihook/pyfastnet/blob/main/docs/architecture.md).
How to edit the file:
[`fastnet_decoder/data/README.md`](https://github.com/ghotihook/pyfastnet/blob/main/fastnet_decoder/data/README.md).

## Implementing FastNet in another language

Because the protocol is data, a decoder in another language reuses `fastnet.json`
unchanged and implements only the engine:

1. Read [`docs/protocol.md`](https://github.com/ghotihook/pyfastnet/blob/main/docs/protocol.md)
   — what the bytes on the wire mean.
2. Follow [`docs/porting.md`](https://github.com/ghotihook/pyfastnet/blob/main/docs/porting.md)
   — the engine's contract, step by step, in build order.
3. Test against [`conformance/vectors.json`](https://github.com/ghotihook/pyfastnet/blob/main/conformance/README.md)
   — this library's output for real recorded frames, in a form any language can check.

## Documentation

Each file has one job, so nothing is documented in two places:

| Document | What's in it |
|---|---|
| [`docs/protocol.md`](https://github.com/ghotihook/pyfastnet/blob/main/docs/protocol.md) | The FastNet **wire protocol**, language-agnostic — frame envelope, checksum, format templates, segment encoding. |
| [`docs/porting.md`](https://github.com/ghotihook/pyfastnet/blob/main/docs/porting.md) | **Implementing the decoder in another language** — everything an engine must do with `fastnet.json`, in build order. |
| [`conformance/README.md`](https://github.com/ghotihook/pyfastnet/blob/main/conformance/README.md) | The **expected-output vectors** an implementation tests against, and how to compare. |
| [`fastnet_decoder/data/fastnet.json`](https://github.com/ghotihook/pyfastnet/blob/main/fastnet_decoder/data/fastnet.json) | The protocol **as data** — the single source of truth. Channel names, byte layouts, Signal K mappings. |
| [`fastnet_decoder/data/README.md`](https://github.com/ghotihook/pyfastnet/blob/main/fastnet_decoder/data/README.md) | How to **read and edit** that schema file. |
| [`docs/channel_map.md`](https://github.com/ghotihook/pyfastnet/blob/main/docs/channel_map.md) | The full **channel → name → path → unit** table. Generated — don't hand-edit. |
| [`docs/signalk-design.md`](https://github.com/ghotihook/pyfastnet/blob/main/docs/signalk-design.md) | **Why** the Signal K mapping is shaped as it is — the `bandg.*` namespace, Magnetic/True routing, open TBCs. Reasoning only; the mapping itself is in the schema. |
| [`docs/architecture.md`](https://github.com/ghotihook/pyfastnet/blob/main/docs/architecture.md) | Why the protocol is stored as data rather than code, what that cost, and what's still open. |
| [`captures/README.md`](https://github.com/ghotihook/pyfastnet/blob/main/captures/README.md) | The **recorded bus traffic** everything is verified against — its format, and what each file shows. |
| [`CHANGELOG.md`](https://github.com/ghotihook/pyfastnet/blob/main/CHANGELOG.md) | What changed in each release, and how to migrate across the breaking ones. |

## Working on pyfastnet

```bash
git clone https://github.com/ghotihook/pyfastnet.git
cd pyfastnet
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
python -m pytest tests/
```

| Path | What's there |
|---|---|
| `fastnet_decoder/` | The library: `interpreter.py` (the engine), `frame_buffer.py` (framing), `data/fastnet.json` (the protocol). |
| `captures/` | Recorded bus traffic — the evidence every test is built on. |
| `tests/` | Per-channel tests from real frames, the golden baseline, and the conformance, schema and example checks. |
| `conformance/` | The language-neutral expected output, and the script that generates it. |
| `examples/` | Runnable scripts using the library. |
| `tools/` | `validate_schema.py` proofreads the schema; `find_unknown_codes.py` lists what in the captures is still unidentified. |
| `docs/` | The protocol, the porting guide, design records and the generated channel map. |

To add or correct a channel, edit `fastnet.json` and run the tests.
[“After an edit”](https://github.com/ghotihook/pyfastnet/blob/main/fastnet_decoder/data/README.md#after-an-edit)
explains the checks that will then ask you to regenerate derived files.

## Acknowledgments

- [trlafleur](https://github.com/trlafleur) — background research
- [Oppedijk](https://www.oppedijk.com/bandg/fastnet.html) — protocol documentation
- [timmathews](https://github.com/timmathews/bg-fastnet-driver) — C++ reference implementation

## License

MIT — see [LICENSE](https://github.com/ghotihook/pyfastnet/blob/main/LICENSE).
