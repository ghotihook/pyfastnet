import unittest
from fastnet_decoder.decode_fastnet import decode_frame


def _decode(hex_str):
    result = decode_frame(bytes.fromhex(hex_str))
    assert "error" not in result, f"Decode error: {result}"
    return result["values"]


class TestBatteryVolts(unittest.TestCase):
    """
    Battery Volts: format 0x01, 16-bit signed, divisor 100.
    Channel 0x8D; value 13.18 V.
    """
    FRAME = "ff051401e78d8105263b3101fa344700f300cc9b4700a000099b"

    def setUp(self):
        self.v = _decode(self.FRAME)["Battery Volts"]

    def test_value(self):
        self.assertAlmostEqual(self.v["value"], 13.18, places=2)

    def test_display(self):
        self.assertEqual(self.v["display_text"], "13.18")


if __name__ == "__main__":
    unittest.main()
