# pyfastnet

A Python library for decoding the **FastNet** protocol used by B&G Hydra / H2000
instruments. Feed it raw bytes from the Fastnet bus and it handles
synchronisation, checksum validation, and decoding — returning instrument data as
**Signal K paths in SI units**, ready for further processing.

> **v3.0 changes the output format.** Decoded frames are now `{signalk_path:
> SI_value}` (e.g. `navigation.speedThroughWater = 3.6`) instead of the v2
> name-keyed `{value, display_text, layout}` dicts. See **Output format** below.
> The full v2-style decode is still available via `FrameBuffer(project=False)`.

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
2 stop bits**. No instruments to hand? The companion apps below ship recorded
captures you can replay.

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

It is rendered as a table in [`docs/channel_map.md`](docs/channel_map.md).

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

## Documentation

Each file has one job, so nothing is documented in two places:

| Document | What's in it |
|---|---|
| [`docs/protocol.md`](docs/protocol.md) | The FastNet **wire protocol**, language-agnostic — frame envelope, checksum, format templates, segment encoding. Read this first if you're porting the decoder. |
| [`fastnet_decoder/data/fastnet.json`](fastnet_decoder/data/fastnet.json) | The protocol **as data** — the single source of truth. Channel names, byte layouts, Signal K mappings. |
| [`fastnet_decoder/data/README.md`](fastnet_decoder/data/README.md) | How to **read and edit** that schema file. |
| [`docs/channel_map.md`](docs/channel_map.md) | The full **channel → name → path → unit** table. Generated — don't hand-edit. |
| [`docs/v3_signalk_mapping.md`](docs/v3_signalk_mapping.md) | **Why** the Signal K mapping is shaped as it is — the `bandg.*` namespace, Magnetic/True routing, open TBCs. Reasoning only; the mapping itself is in the schema. |
| [`docs/architecture.md`](docs/architecture.md) | Why the protocol is stored as data rather than code, what that cost, and what's still open. |

## Acknowledgments

- [trlafleur](https://github.com/trlafleur) — background research
- [Oppedijk](https://www.oppedijk.com/bandg/fastnet.html) — protocol documentation
- [timmathews](https://github.com/timmathews/bg-fastnet-driver) — C++ reference implementation

## License

MIT — see [LICENSE](LICENSE).
