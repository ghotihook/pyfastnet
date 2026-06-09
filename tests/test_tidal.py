import unittest
from fastnet_decoder.decode_fastnet import decode_frame


def _decode(hex_str):
    result = decode_frame(bytes.fromhex(hex_str))
    assert "error" not in result, f"Decode error: {result}"
    return result["values"]


# Both channels use format 0x07 (4 bytes: status | seg | msb | lsb).
#   Tidal Set:   seg 0x66 → layout '°M'    — bearing, always positive
#   Tidal Drift: seg 0xbb → layout 'd[data]' — 'd' prefix, always positive


class TestTidalSet(unittest.TestCase):
    """
    Tidal Set = 270°M: format 0x07, segment byte 0x66 → layout '°M'.
    9-bit value encoded as (msb & 0x7F) << 8 | lsb: here msb=0x01, lsb=0x0e → 270.
    """
    FRAME = "ff600a019684070066010e8383bb023d"

    def setUp(self):
        self.v = _decode(self.FRAME)["Tidal Set"]

    def test_value(self):
        self.assertAlmostEqual(self.v["value"], 270.0, places=0)

    def test_layout(self):
        self.assertEqual(self.v["layout"], "°M")

    def test_display(self):
        self.assertEqual(self.v["display_text"], "270°M")


class TestTidalDrift(unittest.TestCase):
    """
    Tidal Drift = 0.02 kn: format 0x03, segment byte 0xbb → layout 'd[data]'.
    'd' prefix on the instrument display; value is always non-negative.
    """
    FRAME = "ff600a019684070066010e8383bb023d"

    def setUp(self):
        self.v = _decode(self.FRAME)["Tidal Drift"]

    def test_value(self):
        self.assertAlmostEqual(self.v["value"], 0.02, places=2)

    def test_layout(self):
        self.assertEqual(self.v["layout"], "d[data]")

    def test_display(self):
        self.assertEqual(self.v["display_text"], "d0.02")


if __name__ == "__main__":
    unittest.main()
