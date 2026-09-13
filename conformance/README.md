# Conformance vectors

[`vectors.json`](vectors.json) is the expected output of a FastNet decoder, produced by
pyfastnet — the reference implementation — from real recorded traffic. An implementation
in any language that reproduces it decodes FastNet the same way pyfastnet does.

The engine these vectors test is specified in [`docs/porting.md`](../docs/porting.md);
section numbers below (§2, §7) refer to it.

## What's in it

```
{
  "meta":    { "pyfastnet_version", "schema", "schema_sha256", "battery_id": "house" },
  "streams": [ one entry per capture ],
  "frames":  [ one entry per test frame ]
}
```

`meta.schema_sha256` is the SHA-256 of the `fastnet.json` the vectors were generated
from (line endings normalised to LF). Use the schema and the vectors from the same
commit.

### `streams` — framing (§2)

One entry per file in [`captures/`](../captures/README.md):

```json
{
  "capture": "captures/big.txt",
  "frames": 954,
  "frames_sha256": "28beeaf2f6c0209b0d7a63bb63a35abbd3d9dcfd43d547082584157fe750a693",
  "first_frames": ["ff010a01f541910000420a00000000e2", "ff050601f57505012d1d0932", "…"],
  "frames_by_command": {"0x01": 906, "0x03": 31, "0x0E": 9, "0xD1": 4, "0xD5": 4}
}
```

Feed the capture's bytes through your framing and collect every frame that reaches
dispatch — checksum-valid, and whose command isn't in `ignoredCommands`. Then check:

- `frames` — how many there are.
- `frames_sha256` — the SHA-256 of the frames as lower-case hex, joined with `"\n"` (no
  trailing newline), as ASCII.

`first_frames` and `frames_by_command` are there to help find a mismatch.

### `frames` — decoding (§3–§6) and projection (§7)

```json
{
  "id": "f001",
  "source": "captures/big.txt",
  "frame": "ff010a01f541910000420a00000000e2",
  "decode": {
    "to_address": "Entire System",
    "from_address": "Normal CPU (Depth Board in H2000)",
    "command": "Broadcast",
    "values": {
      "Boatspeed (Knots)": {"channel_id": "0x41", "value": 0.0, "display_text": "0.00", "layout": null},
      "Boatspeed (Raw)":   {"channel_id": "0x42", "value": 0.0, "display_text": "0 / 0", "layout": null}
    }
  },
  "signalk": {"navigation.speedThroughWater": 0.0, "bandg.navigation.rawSpeedThroughWater": 0.0}
}
```

- **`frame`** — one complete frame as hex, with valid checksums.
- **`decode`** — the expected decoded frame, or `null` when the command is one pyfastnet
  doesn't decode (pilot messages and other unknown commands).
- **`signalk`** — the expected projection with `battery_id` `"house"`, or `null` alongside
  a `null` decode. An empty object means the frame decodes but emits nothing — Backlight,
  for example.
- **`source`** — the capture the frame first appears in, or `"synthetic"` for a hand-built
  frame covering behaviour no capture contains. Synthetic frames carry a `note` saying
  what they test.

**How the frames were chosen.** From all 4,690 distinct frames in the captures, greedily,
until every combination seen anywhere in the captures is covered at least once: channel ×
format byte × layout × sign, every command and address, every form of position text, and
every emitted Signal K path. Three synthetic frames follow.

## Comparing

- **Numbers: exactly.** Each value is an integer put through at most a division by the
  divisor, then one multiply and one add, in the order porting.md gives. IEEE-754 doubles
  make that bit-for-bit reproducible, so a correct implementation matches exactly. Compare
  as numbers, not text: the file writes `355.0` where your language may print `355`.
- **`null`** is JSON null — a value with no number, a missing layout, Backlight's
  `channel_id`, and `decode`/`signalk` for undecoded commands.
- **Strings: exactly**, including `°` and other non-ASCII characters. The file is UTF-8.
- **Key order** in objects doesn't matter.

A harness, in pseudocode:

```
vectors = parse_json("conformance/vectors.json")

for s in vectors.streams:
    frames = my_framing(bytes of every line in s.capture)
    check len(frames) == s.frames
    check sha256(join("\n", lowercase_hex(f) for f in frames)) == s.frames_sha256

for v in vectors.frames:
    decoded = my_decode(from_hex(v.frame))              # null for undecoded commands
    check deep_equal(decoded, v.decode)
    check deep_equal(decoded == null ? null : my_project(decoded), v.signalk)
```

To see the reference output for a frame that isn't in the file, run
`python examples/inspect_frame.py <hex>` in a checkout.

## Regenerating

The vectors are generated, never hand-edited:

```
python conformance/generate_vectors.py
```

It is deterministic. `tests/test_conformance.py` fails whenever the library's output and
the committed file disagree. After an intended change — including any edit to
`fastnet.json` — regenerate, and say in the commit what changed and why. Implementations
elsewhere can then diff the new file to see exactly which outputs moved.
