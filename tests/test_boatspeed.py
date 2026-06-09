import unittest
from fastnet_decoder.decode_fastnet import decode_frame


def _decode(hex_str):
    result = decode_frame(bytes.fromhex(hex_str))
    assert "error" not in result, f"Decode error: {result}"
    return result["values"]


class TestBoatspeed(unittest.TestCase):
    """
    Performance Processor broadcast containing Boatspeed (Knots) and
    Boatspeed (Raw).
    - Knots: format 0x01, 16-bit signed, divisor 100
    - Raw: format 0x0A, two 16-bit signed integers rendered as "first / second"
    """
    FRAME = "ff010a01f54192f9dd420a01ec082cea"

    def setUp(self):
        self.v = _decode(self.FRAME)

    def test_knots_value(self):
        self.assertAlmostEqual(self.v["Boatspeed (Knots)"]["value"], 4.77, places=2)

    def test_knots_display(self):
        self.assertEqual(self.v["Boatspeed (Knots)"]["display_text"], "4.77")

    def test_raw_is_pair(self):
        self.assertIn(" / ", self.v["Boatspeed (Raw)"]["display_text"])


if __name__ == "__main__":
    unittest.main()
