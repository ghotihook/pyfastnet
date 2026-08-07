import unittest
from fastnet_decoder import decode_frame


def _decode(hex_str):
    result = decode_frame(bytes.fromhex(hex_str))
    assert "error" not in result, f"Decode error: {result}"
    return result["values"]


class TestApparentWindSpeed(unittest.TestCase):
    """
    18-channel broadcast containing apparent wind speed in both units.
    Format 0x01, 16-bit signed, divisor 10.
    AWA sign variants are in test_awa.py.
    """
    FRAME = "ff051801e34e0a061c05fe4d51009c4f610050520a47f347f351032065a0"

    def setUp(self):
        self.v = _decode(self.FRAME)

    def test_knots_value(self):
        self.assertAlmostEqual(self.v["Apparent Wind Speed (Knots)"]["value"], 15.6, places=1)

    def test_knots_display(self):
        self.assertEqual(self.v["Apparent Wind Speed (Knots)"]["display_text"], "15.6")

    def test_ms_value(self):
        self.assertAlmostEqual(self.v["Apparent Wind Speed (m/s)"]["value"], 8.0, places=1)

    def test_ms_display(self):
        self.assertEqual(self.v["Apparent Wind Speed (m/s)"]["display_text"], "8.0")


if __name__ == "__main__":
    unittest.main()
