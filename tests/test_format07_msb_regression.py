import unittest
from fastnet_decoder.decode_fastnet import decode_frame


class TestFormat07MSBRegression(unittest.TestCase):
    """
    Regression tests for the format 0x07 MSB bit-shift bug.

    The bug: msb was computed as (data_bytes[2] >> 1) & 0x7F instead of
    data_bytes[2] & 0x7F. The spurious >> 1 discarded bit 0 of data_bytes[2],
    collapsing the MSB contribution to zero for any raw value > 255
    (i.e. whenever data_bytes[2] is non-zero).

    All frames below are real captures where the raw value exceeds 255, so
    data_bytes[2] == 0x01. The table shows the wrong vs correct reading:

      Channel                    Raw   Buggy        Correct
      Depth (Feet)      0xC2     465   20.9 ft   →  46.5 ft
      Tidal Set         0x84     297   41.0 °    →  297.0 °
      Autopilot Target  0xA6     354   98.0 °    →  354.0 °
      VMG (Knots)       0x7F     415    1.59 kn  →  4.15 kn
    """

    def _decode(self, hex_str):
        decoded = decode_frame(bytes.fromhex(hex_str))
        self.assertNotIn("error", decoded, f"Frame decode error: {decoded}")
        return decoded["values"]

    # ------------------------------------------------------------------
    # Tidal Set (0x84) — raw 297, format_byte 0x07, divisor 1
    # Buggy result: 41°  (297 - 256 = 41, MSB dropped)
    # Correct:     297°
    # Frame also contains Tidal Drift (0x83) as a sanity cross-check.
    # ------------------------------------------------------------------
    TIDAL_SET_FRAME = "ff600a01968407006601298383bb30f4"

    def test_tidal_set_present(self):
        values = self._decode(self.TIDAL_SET_FRAME)
        self.assertIn("Tidal Set", values)

    def test_tidal_set_value(self):
        values = self._decode(self.TIDAL_SET_FRAME)
        self.assertEqual(values["Tidal Set"]["interpreted"], 297.0,
                         "Tidal Set should be 297° (was 41° with the >> 1 bug)")

    def test_tidal_drift_unaffected(self):
        # Tidal Drift raw value is 48 (< 256), so data_bytes[2] == 0 — unaffected by bug
        values = self._decode(self.TIDAL_SET_FRAME)
        self.assertIn("Tidal Drift", values)
        self.assertAlmostEqual(values["Tidal Drift"]["interpreted"], 0.48, places=2)

    # ------------------------------------------------------------------
    # Autopilot Compass Target (0xA6) — raw 354, format_byte 0x07, divisor 1
    # Buggy result:  98°  (354 - 256 = 98, MSB dropped)
    # Correct:      354°
    # Frame also contains Autopilot Mode as a sanity cross-check.
    # ------------------------------------------------------------------
    AUTOPILOT_TARGET_FRAME = "ff120a01e4b5015101a6070066016282"

    def test_autopilot_target_present(self):
        values = self._decode(self.AUTOPILOT_TARGET_FRAME)
        self.assertIn("Autopilot Compass Target", values)

    def test_autopilot_target_value(self):
        values = self._decode(self.AUTOPILOT_TARGET_FRAME)
        self.assertEqual(values["Autopilot Compass Target"]["interpreted"], 354.0,
                         "Autopilot Compass Target should be 354° (was 98° with the >> 1 bug)")

    def test_autopilot_mode_unaffected(self):
        # Autopilot Mode uses format 0x01 (16-bit signed), not format 0x07 — unaffected
        values = self._decode(self.AUTOPILOT_TARGET_FRAME)
        self.assertIn("Autopilot Mode", values)
        self.assertEqual(values["Autopilot Mode"]["interpreted"], "Compass")


if __name__ == "__main__":
    unittest.main()
