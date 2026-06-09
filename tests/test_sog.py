import unittest
from fastnet_decoder.decode_fastnet import decode_frame


def _decode(hex_str):
    result = decode_frame(bytes.fromhex(hex_str))
    assert "error" not in result, f"Decode error: {result}"
    return result["values"]


class TestSOGCOG(unittest.TestCase):
    """
    SOG, COG True, COG Mag from an NMEA FFD broadcast.
    - SOG: format 0x01, divisor 10
    - COG True/Mag: format 0x01, divisor 1 (integer degrees)
    """
    FRAME = "ff600c0194e9310000ea11015beb6100360d"

    def setUp(self):
        self.v = _decode(self.FRAME)

    def test_sog_value(self):
        self.assertAlmostEqual(self.v["Speed Over Ground"]["value"], 5.4, places=1)

    def test_sog_display(self):
        self.assertEqual(self.v["Speed Over Ground"]["display_text"], "5.4")

    def test_cog_mag_value(self):
        self.assertEqual(self.v["Course Over Ground (Mag)"]["value"], 347.0)

    def test_cog_mag_display(self):
        self.assertEqual(self.v["Course Over Ground (Mag)"]["display_text"], "347")

    def test_cog_true_value(self):
        self.assertEqual(self.v["Course Over Ground (True)"]["value"], 0.0)


if __name__ == "__main__":
    unittest.main()
