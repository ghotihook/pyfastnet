import unittest
from fastnet_decoder.decode_fastnet import decode_frame


def _decode(hex_str):
    result = decode_frame(bytes.fromhex(hex_str))
    assert "error" not in result, f"Decode error: {result}"
    return result["values"]


# Sign convention (format 0x03, segment byte drives layout):
#   TWA port: seg 0xa8 → layout '=[data]' → value negative
#   TWA stb:  seg 0x28 → layout '[data]=' → value positive
#
# B&G uses '=' as an alternative minus symbol (equals-height segments).
# For port, it appears before the digits; for starboard, after.


class TestTWAPort(unittest.TestCase):
    """
    TWA to port: segment byte 0xa8 → layout '=[data]'.
    Leading '=' is B&G's minus-like symbol; value is stored negative.
    Display_text is just the signed number — decoder represents '=' as '-'.
    """
    FRAME = "ff051601e55561004b566100265913a8517f87009900006d08cc4994"

    def setUp(self):
        self.v = _decode(self.FRAME)["True Wind Angle"]

    def test_value(self):
        self.assertAlmostEqual(self.v["value"], -81.0, places=0)

    def test_layout(self):
        self.assertEqual(self.v["layout"], "=[data]")

    def test_display(self):
        self.assertEqual(self.v["display_text"], "-81")


class TestTWAStarboard(unittest.TestCase):
    """
    TWA to starboard: segment byte 0x28 → layout '[data]='.
    Trailing '=' encodes starboard direction; value is positive.
    """
    FRAME = "ff051601e55561005b5661002f591328187f87009900006d08cc4934"

    def setUp(self):
        self.v = _decode(self.FRAME)["True Wind Angle"]

    def test_value(self):
        self.assertAlmostEqual(self.v["value"], 24.0, places=0)

    def test_layout(self):
        self.assertEqual(self.v["layout"], "[data]=")

    def test_display(self):
        self.assertEqual(self.v["display_text"], "24=")


if __name__ == "__main__":
    unittest.main()
