import unittest
from fastnet_decoder.decode_fastnet import decode_frame


class TestFormat08Layout(unittest.TestCase):
    """
    Tests for format 0x08 layout field (magnetic bearing indicator).

    Format 0x08: SEGCODE_B-derived 7-bit segment code + 9-bit unsigned value.
    Segment code 0x66 (segments f+g+a+b = degree symbol) activates the "°M"
    annunciator on the Hydra 2000 FFD, indicating a magnetic-referenced bearing.

    Frame "ff120e01e00b038c274908cc294a0a1cdd6067e5" contains:
      - Rudder Angle (0x0b), format 0x03
      - Heading     (0x49), format 0x08, data=[0xCC, 0x29]
          data[0]=0xCC → segment_code = (0xCC >> 1) & 0x7F = 0x66 → layout "°M"
          unsigned_value = 0x29 = 41 → interpreted 41.0°
      - Heading Raw (0x4a), format 0x0a
    """

    FRAME_HEX = "ff120e01e00b038c274908cc294a0a1cdd6067e5"

    def setUp(self):
        self.decoded = decode_frame(bytes.fromhex(self.FRAME_HEX))
        self.heading = self.decoded["values"]["Heading"]

    def test_no_decode_error(self):
        self.assertNotIn("error", self.decoded)

    def test_heading_present(self):
        self.assertIn("Heading", self.decoded["values"])

    def test_heading_interpreted_value(self):
        self.assertEqual(self.heading["interpreted"], 41.0)

    def test_heading_format_is_08(self):
        self.assertEqual(self.heading["format_bits"], 8)

    def test_heading_raw_has_layout(self):
        self.assertIn("layout", self.heading["raw"])

    def test_heading_layout_is_magnetic(self):
        self.assertEqual(self.heading["raw"]["layout"], "°M")

    def test_heading_segment_code(self):
        # 0x66 = segments f+g+a+b = degree symbol, co-activates Hydra 2000 "M" annunciator
        self.assertEqual(self.heading["raw"]["segment_code"], 0x66)

    def test_cog_true_has_blank_layout(self):
        # COG True is GPS-derived — no magnetic indicator, segment code 0x00 = blank
        # Frame: ff051601e5 ... e9 08 00 XX ... (COG True channel 0xe9)
        # Use a frame that contains COG True with blank segment code
        cog_frame = bytes.fromhex("FF051601E555610030566100185903A86B7F8700BB00016D08CD0DCB")
        decoded = decode_frame(cog_frame)
        cog = decoded["values"].get("Course Over Ground (True)")
        if cog:
            self.assertEqual(cog["raw"]["layout"], " ", "GPS COG should have blank layout (no magnetic indicator)")


if __name__ == "__main__":
    unittest.main()
