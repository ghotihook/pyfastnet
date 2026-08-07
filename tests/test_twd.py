import unittest
from fastnet_decoder import decode_frame


def _decode(hex_str):
    result = decode_frame(bytes.fromhex(hex_str))
    assert "error" not in result, f"Decode error: {result}"
    return result["values"]


# TWD uses format 0x08 (2 bytes). The segment code encodes the °M marker;
# the 9-bit value spans bit 0 of byte 0 (MSB) and all of byte 1 (LSB).
# Values 0–255 fit in byte 1 alone; values 256–359 require MSB=1 in byte 0.
# Layout is always '°M' regardless of value.
#
# TWD_gt180 frame is constructed: TWD=225° is a valid 8-bit value so MSB=0,
# only byte 1 changes (0x49→0xe1=225). Body checksum recomputed.


class TestTWDBelow180(unittest.TestCase):
    """
    TWD = 73°M: value fits in byte 1, MSB bit of byte 0 is 0.
    """
    FRAME = "ff051601e55561004b566100265913a8517f87009900006d08cc4994"

    def setUp(self):
        self.v = _decode(self.FRAME)["True Wind Direction"]

    def test_value(self):
        self.assertAlmostEqual(self.v["value"], 73.0, places=0)

    def test_layout(self):
        self.assertEqual(self.v["layout"], "°M")

    def test_display(self):
        self.assertEqual(self.v["display_text"], "73°M")


class TestTWDAbove180(unittest.TestCase):
    """
    TWD = 269°M: value > 255, so MSB bit of byte 0 is set (9-bit encoding).
    Real captured frame; TWD bytes are 0xcd 0x0d → seg=0x66 (°M), MSB=1, LSB=13 → 269°.
    """
    FRAME = "ff051601e555610030566100185903a86b7f8700bb00016d08cd0dcb"

    def setUp(self):
        self.v = _decode(self.FRAME)["True Wind Direction"]

    def test_value(self):
        self.assertAlmostEqual(self.v["value"], 269.0, places=0)

    def test_layout(self):
        self.assertEqual(self.v["layout"], "°M")

    def test_display(self):
        self.assertEqual(self.v["display_text"], "269°M")


if __name__ == "__main__":
    unittest.main()
