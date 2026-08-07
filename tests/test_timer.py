import unittest
from fastnet_decoder import decode_frame


def _decode(hex_str):
    result = decode_frame(bytes.fromhex(hex_str))
    assert "error" not in result, f"Decode error: {result}"
    return result["values"]


class TestTimer(unittest.TestCase):
    """
    Timer: format 0x05, data bytes [unused, H, M, S].
    value = total seconds; display_text = H:MM:SS string.
    7h 44m 06s = 27846 seconds.
    """
    FRAME = "ff050601f5750501072c064c"

    def setUp(self):
        self.v = _decode(self.FRAME)["Timer"]

    def test_total_seconds(self):
        self.assertEqual(self.v["value"], 27846.0)

    def test_display_hms(self):
        self.assertEqual(self.v["display_text"], "7:44:06")


if __name__ == "__main__":
    unittest.main()
