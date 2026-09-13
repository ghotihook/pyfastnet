# Captures — recorded FastNet traffic

Real bytes recorded from B&G installations' FastNet buses. They are the project's
evidence: the per-channel tests, the [golden baseline](../tests/golden/README.md) and
the [conformance vectors](../conformance/README.md) are all derived from them. They live
in the repository, not in the PyPI package.

## Format

Plain text. Each line is one burst of bytes as read from the serial port, written as
lower-case hex with no separators. Every line is valid hex.

Lines are **not** aligned to frames: a recording starts mid-frame, and a frame can begin
part-way through one line and end in the next. So don't parse lines — feed the bytes
through framing (`FrameBuffer`, or your own implementation of
[`docs/porting.md` §2](../docs/porting.md#2-framing)), exactly as if they were arriving
from the bus:

```python
from fastnet_decoder import FrameBuffer

fb = FrameBuffer()
for line in open("captures/big.txt"):
    if line.strip():
        fb.add_to_buffer(bytes.fromhex(line.strip()))
        fb.get_complete_frames()
```

[`examples/replay_capture.py`](../examples/replay_capture.py) does this and prints the
result.

## The files

"Frames" counts the frames that reach the decoder — checksum-valid and not Keep Alive.
Across all eight that is 9,648 frames, of which 9,322 produce Signal K output (the rest
are pilot messages and other command types pyfastnet does not decode yet).

| File | Frames | What it shows |
|---|---:|---|
| `big.txt` | 954 | Heel and trim as numbers, on both sides (roll −20.4° to +34.0°, pitch −24.4° to +19.7°). Autopilot in standby. |
| `big_with_ap_actions.txt` | 2,115 | The autopilot engaged in Compass (`auto`) and Wind modes, with the pilot's command and acknowledge frames (commands `0xD1`–`0xD5`, `0xFD`, …), which are not decoded yet. |
| `example1_fastnet_data.txt` | 2,719 | Autopilot in standby, and the widest variety of undecoded command types. |
| `example2_fastnet_data.txt` | 2,907 | The autopilot in Compass, Power (`directControl`) and Wind modes. |
| `heel-port.txt` | 168 | Heeled to port: roll about −20°. |
| `heel-stb.txt` | 427 | Heeled to starboard: roll up to +34°. |
| `trim-neg.txt` | 165 | Bow down: pitch −22° to −24°. |
| `trim-pos.txt` | 193 | Bow up: pitch +14° to +20°. |

In `big_with_ap_actions.txt`, `example1` and `example2`, heel, trim, air temperature and
barometric pressure arrive **only** as 7-segment display text, never as numbers, so those
paths are always `None`. That's a real property of some installations, not a decoding
fault — see [`docs/signalk-design.md` note 12](../docs/signalk-design.md#notes).

## Adding a capture

Record the raw serial bytes in the same one-hex-line-per-read form and add the file
here. Then run the test suite: the golden baseline and the conformance vectors cover
every file in this directory, so both will ask to be regenerated — see their READMEs.
`python tools/find_unknown_codes.py your_file.txt` lists anything in it the schema
can't identify yet.
