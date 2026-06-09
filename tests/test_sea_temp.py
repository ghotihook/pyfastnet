import unittest
from fastnet_decoder.decode_fastnet import decode_frame


def _decode(hex_str):
    result = decode_frame(bytes.fromhex(hex_str))
    assert "error" not in result, f"Decode error: {result}"
    return result["values"]


# Both sea temperature and navigation log channels live in the same broadcast frame.

FRAME = "ff011801e7cd840000acc7cf84ff0000001f17005c00171e17007400494f"


class TestSeaTemperature(unittest.TestCase):
    """
    Sea temperature in °C and °F: format 0x07, segment bytes 0x5c / 0x74.
    Divisor 1 (integer degrees). Cross-check: 23°C ≈ 73°F.
    """

    def setUp(self):
        self.v = _decode(FRAME)

    def test_celsius_value(self):
        self.assertEqual(self.v["Sea Temperature (°C)"]["value"], 23.0)

    def test_celsius_display(self):
        self.assertEqual(self.v["Sea Temperature (°C)"]["display_text"], "23°C")

    def test_fahrenheit_value(self):
        self.assertEqual(self.v["Sea Temperature (°F)"]["value"], 73.0)

    def test_fahrenheit_display(self):
        self.assertEqual(self.v["Sea Temperature (°F)"]["display_text"], "73°F")

    def test_unit_consistency(self):
        c = self.v["Sea Temperature (°C)"]["value"]
        f = self.v["Sea Temperature (°F)"]["value"]
        self.assertAlmostEqual(c * 9 / 5 + 32, f, delta=1.0)


class TestNavigationLog(unittest.TestCase):
    """
    Stored Log and Trip Log: format 0x04, 3-byte unsigned, divisor 100.
    Same frame as TestSeaTemperature.
    """

    def setUp(self):
        self.v = _decode(FRAME)

    def test_stored_log_value(self):
        self.assertAlmostEqual(self.v["Stored Log (NM)"]["value"], 442.31, places=2)

    def test_stored_log_display(self):
        self.assertEqual(self.v["Stored Log (NM)"]["display_text"], "442.31")

    def test_trip_log_zero(self):
        self.assertEqual(self.v["Trip Log (NM)"]["value"], 0.0)
        self.assertEqual(self.v["Trip Log (NM)"]["display_text"], "0.00")


if __name__ == "__main__":
    unittest.main()
