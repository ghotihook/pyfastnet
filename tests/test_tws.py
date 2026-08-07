import unittest
from fastnet_decoder import decode_frame


def _decode(hex_str):
    result = decode_frame(bytes.fromhex(hex_str))
    assert "error" not in result, f"Decode error: {result}"
    return result["values"]


class TestTrueWindSpeed(unittest.TestCase):
    """
    16-channel broadcast containing true wind speed in both units.
    Format 0x01, 16-bit signed, divisor 10.
    TWA sign variants are in test_twa.py; TWD variants in test_twd.py.
    """
    FRAME = "ff051601e5555100a656610055590328767f8700bb00db6d08cc7061"

    def setUp(self):
        self.v = _decode(self.FRAME)

    def test_knots_value(self):
        self.assertAlmostEqual(self.v["True Wind Speed (Knots)"]["value"], 16.6, places=1)

    def test_knots_display(self):
        self.assertEqual(self.v["True Wind Speed (Knots)"]["display_text"], "16.6")

    def test_ms_value(self):
        self.assertAlmostEqual(self.v["True Wind Speed (m/s)"]["value"], 8.5, places=1)

    def test_ms_display(self):
        self.assertEqual(self.v["True Wind Speed (m/s)"]["display_text"], "8.5")


class TestVMG(unittest.TestCase):
    """
    Velocity Made Good: format 0x07, segment byte 0xbb → layout 'd[data]'.
    'd' prefix on the instrument display; value is always non-negative.
    Same frame as TestTrueWindSpeed.
    """
    FRAME = "ff051601e5555100a656610055590328767f8700bb00db6d08cc7061"

    def setUp(self):
        self.v = _decode(self.FRAME)["Velocity Made Good (Knots)"]

    def test_value(self):
        self.assertAlmostEqual(self.v["value"], 2.19, places=2)

    def test_layout(self):
        self.assertEqual(self.v["layout"], "d[data]")

    def test_display(self):
        self.assertEqual(self.v["display_text"], "d2.19")


if __name__ == "__main__":
    unittest.main()
