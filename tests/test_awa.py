import unittest
from fastnet_decoder.decode_fastnet import decode_frame


def _decode(hex_str):
    result = decode_frame(bytes.fromhex(hex_str))
    assert "error" not in result, f"Decode error: {result}"
    return result["values"]


# Sign convention (format 0x03, segment byte drives layout):
#   AWA port: seg 0xa0 → layout '-[data]' → value negative
#   AWA stb:  seg 0x20 → layout '[data]-' → value positive
#
# Dash before digits = port (negative); dash after digits = starboard (positive).
# The trailing dash on the B&G display is a direction marker, not a minus sign.


class TestAWAPort(unittest.TestCase):
    """
    AWA to port: segment byte 0xa0 → layout '-[data]'.
    Leading dash drives sign negative; value is stored negative.
    """
    FRAME = "ff051801e34e0a030a02bd4d61004a4f610026520ac4bbc4bb5113a0525e"

    def setUp(self):
        self.v = _decode(self.FRAME)["Apparent Wind Angle"]

    def test_value(self):
        self.assertAlmostEqual(self.v["value"], -82.0, places=0)

    def test_layout(self):
        self.assertEqual(self.v["layout"], "-[data]")

    def test_display(self):
        self.assertEqual(self.v["display_text"], "-82")


class TestAWAStarboard(unittest.TestCase):
    """
    AWA to starboard: segment byte 0x20 → layout '[data]-'.
    Trailing dash encodes starboard direction; value is positive.
    """
    FRAME = "ff051801e34e0a02cf02804d61005a4f61002e520a128f128f5113201835"

    def setUp(self):
        self.v = _decode(self.FRAME)["Apparent Wind Angle"]

    def test_value(self):
        self.assertAlmostEqual(self.v["value"], 24.0, places=0)

    def test_layout(self):
        self.assertEqual(self.v["layout"], "[data]-")

    def test_display(self):
        self.assertEqual(self.v["display_text"], "24-")


if __name__ == "__main__":
    unittest.main()
