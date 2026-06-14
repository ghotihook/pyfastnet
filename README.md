# pyfastnet

A Python library for decoding the **FastNet** protocol used by B&G Hydra / H2000
instruments. Feed it raw bytes from the Fastnet bus and it handles
synchronisation, checksum validation, and decoding — returning structured
instrument data ready for further processing.

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
            for channel, decoded in frame["values"].items():
                print(channel, decoded)
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
| **pyfastnet** *(this library)* | **Decoder.** Turns raw Fastnet bytes into named instrument channels. | You're writing your own Python and want the decoded data. |
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
`values`. Each entry in `values` is keyed by channel name:

```python
{
  "to_address":   "Entire System",
  "from_address": "Normal CPU (Wind Board in H2000)",
  "command":      "Broadcast",
  "values": {
    "Apparent Wind Speed (Knots)": {
      "channel_id":   "0x4D",
      "value":        7.0,
      "display_text": "7.0",
      "layout":       None,
    },
    "Apparent Wind Angle": {
      "channel_id":   "0x51",
      "value":        -6.0,
      "display_text": "-6.0",
      "layout":       "-[data]",
    },
    "True Wind Direction": {
      "channel_id":   "0x6D",
      "value":        213.0,
      "display_text": "213.0°M",
      "layout":       "°M",
    },
  }
}
```

### Position (LatLon) frames

Position frames (command `LatLon`) appear under the `"LatLon"` key. The raw
coordinate string (`DDMM.mmm` with hemisphere letters) is carried in
`display_text`; `value` is `None`. The originating source's marker byte is
preserved in `channel_id` (e.g. `0x47`, `0x4E`) but does not affect the key:

```python
"LatLon": {
    "channel_id":   "0x4E",
    "value":        None,
    "display_text": "3352.450S15113.920E",
    "layout":       None,
}
```

### Layout field

The `layout` field describes the indicator symbol shown on the physical display
around the numeric value. It is the **only** place True/Magnetic, port/starboard
sign, and similar context is carried — the raw stream contains no magnetic
variation or deviation.

| `layout` | Meaning | Sign |
|---|---|---|
| `None` | No indicator symbol | positive |
| `"[data]="` | `=` after value (starboard) | positive |
| `"=[data]"` | `=` before value (port) | negative |
| `"[data]-"` | `-` after value (starboard) | positive |
| `"-[data]"` | `-` before value (port) | negative |
| `"H[data]"` | `H` prefix — heading | positive |
| `"°M"` | Magnetic bearing suffix | positive |
| `"u[data]"` | `u` prefix — upwind (VMG) | positive |
| `"d[data]"` | `d` prefix — downwind (VMG) | positive |
| `"L[data]"` | `L` before — leeway port | negative |
| `"[data]L"` | `L` after — AP compass target | positive |
| `"[data]°C"` | Celsius suffix | positive |
| `"[data]°F"` | Fahrenheit suffix | positive |
| `"[data]z"` / `"z[data]"` | Dog-leg symbol — AP off course | positive |
| `"TBC"` | Symbol seen but not yet identified | positive |

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

## Acknowledgments

- [trlafleur](https://github.com/trlafleur) — background research
- [Oppedijk](https://www.oppedijk.com/bandg/fastnet.html) — protocol documentation
- [timmathews](https://github.com/timmathews/bg-fastnet-driver) — C++ reference implementation

## License

MIT — see [LICENSE](LICENSE).
