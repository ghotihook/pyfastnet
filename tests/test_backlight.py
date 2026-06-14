import unittest
from fastnet_decoder.frame_buffer import FrameBuffer


def _decode(hex_str):
    """Feed a raw frame through the buffer and return the queued decoded frame."""
    fb = FrameBuffer()
    fb.add_to_buffer(bytes.fromhex(hex_str))
    fb.get_complete_frames()
    assert not fb.frame_queue.empty(), f"No frame queued for {hex_str}"
    return fb.frame_queue.get_nowait()


class TestBacklight(unittest.TestCase):
    """
    Light Intensity command (0xC9), broadcast 0x50 -> 0xFF, 1-byte body giving
    the system backlight level. Real frames captured while toggling the FFD
    backlight off/low/med/high.
    """

    CASES = {
        "ff5001c9e70000": ("Off", 0.0),
        "ff5001c9e701ff": ("Low", 1.0),
        "ff5001c9e702fe": ("Medium", 2.0),
        "ff5001c9e704fc": ("High", 4.0),
    }

    def test_levels(self):
        for frame, (text, value) in self.CASES.items():
            with self.subTest(frame=frame):
                decoded = _decode(frame)
                bl = decoded["values"]["Backlight"]
                self.assertEqual(bl["display_text"], text)
                self.assertEqual(bl["value"], value)

    def test_command_name(self):
        decoded = _decode("ff5001c9e70000")
        self.assertEqual(decoded["command"], "Light Intensity")


if __name__ == "__main__":
    unittest.main()
