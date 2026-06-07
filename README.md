# pyfastnet

Python library for decoding the FastNet protocol used by B&G Hydra/H2000 instruments. Developed for personal use and published for general interest.

## Purpose

Feed a raw byte stream from a FastNet bus into the library. It handles synchronisation, checksum validation, and decoding — returning structured instrument data ready for further processing.

## Installation

```
pip install pyfastnet
```

## Example usage

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

## Output format

Each decoded frame is a dict with `to_address`, `from_address`, `command`, and `values`. Each entry in `values` is keyed by channel name:

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

Position frames (command `LatLon`) appear under the `"LatLon"` key. The raw coordinate
string (`DDMM.mmm` with hemisphere letters) is carried in `display_text`; `value` is
`None`. The originating source's marker byte is preserved in `channel_id` (e.g. `0x47`,
`0x4E`) but does not affect the key:

```python
"LatLon": {
    "channel_id":   "0x4E",
    "value":        None,
    "display_text": "3352.450S15113.920E",
    "layout":       None,
}
```

### Layout field

The `layout` field describes the indicator symbol shown on the physical display around the numeric value:

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

## Debug API

```python
from fastnet_decoder import set_log_level
import logging
set_log_level(logging.DEBUG)
```

```python
fb.get_buffer_size()      # bytes currently in buffer
fb.get_buffer_contents()  # hex string of buffer contents
```

## Companion apps

- [fastnet2ip](https://github.com/ghotihook/fastnet2ip) — reads FastNet from serial, broadcasts NMEA 0183 via UDP
- [fastnet2ip_n2k](https://github.com/ghotihook/fastnet2ip_n2k) — reads FastNet from serial, broadcasts NMEA 2000 via UDP

Both run on Raspberry Pi, macOS, or Linux.

## Acknowledgments

- [trlafleur](https://github.com/trlafleur) — background research
- [Oppedijk](https://www.oppedijk.com/bandg/fastnet.html) — protocol documentation
- [timmathews](https://github.com/timmathews/bg-fastnet-driver) — C++ reference implementation
