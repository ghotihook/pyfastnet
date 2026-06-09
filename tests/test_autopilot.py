import unittest
from fastnet_decoder.decode_fastnet import decode_frame


def _decode(hex_str):
    result = decode_frame(bytes.fromhex(hex_str))
    assert "error" not in result, f"Decode error: {result}"
    return result["values"]


class TestAutopilotStandby(unittest.TestCase):
    """
    AP Mode = Standby: Autopilot Mode channel (0xB5), format 0x01,
    raw int 20484 maps to display string "Standby".
    In Standby the Compass Target channel carries an OFF segment display (value=None).
    """
    FRAME = "ff121c01d2b5015004a606bee8e800af06bee8e8005306bee8e8007606bee8e80088"

    def setUp(self):
        self.v = _decode(self.FRAME)

    def test_mode_display(self):
        self.assertEqual(self.v["Autopilot Mode"]["display_text"], "Standby")

    def test_target_is_off(self):
        self.assertIsNone(self.v["Autopilot Compass Target"]["value"])
        self.assertEqual(self.v["Autopilot Compass Target"]["display_text"], "OFF ")


class TestAutopilotCompass(unittest.TestCase):
    """
    AP Mode = Compass: target is a magnetic bearing (°M layout).
    Target = 0°M in this frame (just engaged).
    """
    FRAME = "ff120a01e4b5015101a60700660000e5"

    def setUp(self):
        self.v = _decode(self.FRAME)

    def test_mode_display(self):
        self.assertEqual(self.v["Autopilot Mode"]["display_text"], "Compass")

    def test_target_value(self):
        self.assertEqual(self.v["Autopilot Compass Target"]["value"], 0.0)

    def test_target_layout(self):
        self.assertEqual(self.v["Autopilot Compass Target"]["layout"], "°M")

    def test_target_display(self):
        self.assertEqual(self.v["Autopilot Compass Target"]["display_text"], "0°M")


class TestAutopilotWind(unittest.TestCase):
    """
    AP Mode = Wind: target is a magnetic bearing representing a locked wind angle.
    Target = 331°M in this frame.
    """
    FRAME = "ff120a01e4b5015104a6070066014b96"

    def setUp(self):
        self.v = _decode(self.FRAME)

    def test_mode_display(self):
        self.assertEqual(self.v["Autopilot Mode"]["display_text"], "Wind")

    def test_target_value(self):
        self.assertEqual(self.v["Autopilot Compass Target"]["value"], 331.0)

    def test_target_display(self):
        self.assertEqual(self.v["Autopilot Compass Target"]["display_text"], "331°M")


if __name__ == "__main__":
    unittest.main()
