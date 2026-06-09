import unittest
from fastnet_decoder.decode_fastnet import decode_frame


def _decode(hex_str):
    result = decode_frame(bytes.fromhex(hex_str))
    assert "error" not in result, f"Decode error: {result}"
    return result["values"]


# Sign convention (format 0x07, segment byte drives layout):
#   Heel port:  seg 0xf3 → layout 'H[data]'  → value negative, display "H20.4"
#   Heel stb:   seg 0x73 → layout '[data]H'  → value positive, display "33.8H"
#   Trim pos:   seg 0x20 → layout '[data]-'  → value positive, display "19.7-"
#   Trim neg:   seg 0xa0 → layout '-[data]'  → value negative, display "-24.4"


class TestHeelPort(unittest.TestCase):
    """
    Heel to port: segment byte 0xf3 → layout 'H[data]'.
    H before the digits encodes port direction; value is stored negative.
    Display strips the minus — the H symbol itself carries the sign.
    """
    FRAME = "ff051401e78d8105263b3101fa344700f300cc9b4700a000099b"

    def setUp(self):
        self.v = _decode(self.FRAME)["Heel Angle"]

    def test_value(self):
        self.assertAlmostEqual(self.v["value"], -20.4, places=1)

    def test_layout(self):
        self.assertEqual(self.v["layout"], "H[data]")

    def test_display(self):
        self.assertEqual(self.v["display_text"], "H20.4")


class TestHeelStarboard(unittest.TestCase):
    """
    Heel to starboard: segment byte 0x73 → layout '[data]H'.
    H after the digits encodes starboard direction; value is positive.
    """
    FRAME = "ff051401e78d8105213b3101fb3447007301529b4700a0000899"

    def setUp(self):
        self.v = _decode(self.FRAME)["Heel Angle"]

    def test_value(self):
        self.assertAlmostEqual(self.v["value"], 33.8, places=1)

    def test_layout(self):
        self.assertEqual(self.v["layout"], "[data]H")

    def test_display(self):
        self.assertEqual(self.v["display_text"], "33.8H")


class TestTrimPositive(unittest.TestCase):
    """
    Positive (bow-down) trim: segment byte 0x20 → layout '[data]-'.
    Trailing dash encodes positive direction; value is positive.
    """
    FRAME = "ff051401e78d8105463b3101e13447007300249b47002000c580"

    def setUp(self):
        self.v = _decode(self.FRAME)["Fore/Aft Trim"]

    def test_value(self):
        self.assertAlmostEqual(self.v["value"], 19.7, places=1)

    def test_layout(self):
        self.assertEqual(self.v["layout"], "[data]-")

    def test_display(self):
        self.assertEqual(self.v["display_text"], "19.7-")


class TestTrimNegative(unittest.TestCase):
    """
    Negative (bow-up) trim: segment byte 0xa0 → layout '-[data]'.
    Leading dash encodes negative direction; sign appears in the formatted number.
    """
    FRAME = "ff051401e78d8105413b3101df34470073001d9b4700a000f4df"

    def setUp(self):
        self.v = _decode(self.FRAME)["Fore/Aft Trim"]

    def test_value(self):
        self.assertAlmostEqual(self.v["value"], -24.4, places=1)

    def test_layout(self):
        self.assertEqual(self.v["layout"], "-[data]")

    def test_display(self):
        self.assertEqual(self.v["display_text"], "-24.4")


if __name__ == "__main__":
    unittest.main()
