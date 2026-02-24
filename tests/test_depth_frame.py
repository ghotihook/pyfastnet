import unittest
from fastnet_decoder.decode_fastnet import decode_frame


class TestDepthFrame(unittest.TestCase):
    """
    Tests for depth channel decoding (0xC1 Meters, 0xC2 Feet, 0xC3 Fathoms).

    The format 0x07 decoder uses a 15-bit value split across two bytes:
        msb = data_bytes[2] & 0x7F   (7 bits)
        lsb = data_bytes[3]          (8 bits)
        value = (msb << 8) | lsb

    When depth > 25.5 m (raw value > 255), data_bytes[2] is non-zero.
    This is the case that previously decoded incorrectly due to a spurious >> 1.
    """

    # Real broadcast frame captured from fastnet_record.txt.
    # from_address = 0x01 (Normal CPU / Depth Board).
    # Contains: Depth Meters=12.0, Depth Feet=39.5, Depth Fathoms=6.6
    # plus Dead Reckoning Distance and Dead Reckoning Course.
    DEPTH_FRAME_HEX = "ff011c01e3c14700800078c2470080018bc357008000428184ff000000d308cd64ff"

    def setUp(self):
        self.decoded = decode_frame(bytes.fromhex(self.DEPTH_FRAME_HEX))
        self.values = self.decoded["values"]

    def test_no_decode_error(self):
        self.assertNotIn("error", self.decoded)

    def test_all_depth_channels_present(self):
        self.assertIn("Depth (Meters)", self.values)
        self.assertIn("Depth (Feet)", self.values)
        self.assertIn("Depth (Fathoms)", self.values)

    def test_depth_meters(self):
        self.assertEqual(self.values["Depth (Meters)"]["interpreted"], 12.0)

    def test_depth_feet(self):
        # Raw value is 395 (> 255), so data_bytes[2] = 0x01 — this is the case
        # that was broken before the msb >> 1 fix. Correct value is 39.5 ft.
        self.assertEqual(self.values["Depth (Feet)"]["interpreted"], 39.5)

    def test_depth_fathoms(self):
        self.assertEqual(self.values["Depth (Fathoms)"]["interpreted"], 6.6)

    def test_depth_units_are_consistent(self):
        meters = self.values["Depth (Meters)"]["interpreted"]
        feet = self.values["Depth (Feet)"]["interpreted"]
        fathoms = self.values["Depth (Fathoms)"]["interpreted"]

        # Allow 0.2 tolerance: each channel is independently rounded to 0.1 of its
        # own unit by the instrument, so cross-unit comparisons can differ by ~0.15.
        self.assertAlmostEqual(meters * 3.28084, feet, delta=0.2,
                               msg="Feet should equal meters × 3.28084")
        self.assertAlmostEqual(meters / 1.8288, fathoms, delta=0.2,
                               msg="Fathoms should equal meters / 1.8288")


if __name__ == "__main__":
    unittest.main()
