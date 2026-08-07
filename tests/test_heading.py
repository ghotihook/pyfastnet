import unittest
from fastnet_decoder import decode_frame


def _decode(hex_str):
    result = decode_frame(bytes.fromhex(hex_str))
    assert "error" not in result, f"Decode error: {result}"
    return result["values"]


class TestHeading(unittest.TestCase):
    """
    Heading: format 0x08, segment code 0x66 → layout '°M'.
    9-bit value; MSB=0 for values ≤ 255.
    """
    FRAME = "ff120e01e00b038c024908cd634a0afbe13d492d"

    def setUp(self):
        self.v = _decode(self.FRAME)["Heading"]

    def test_value(self):
        self.assertEqual(self.v["value"], 355.0)

    def test_layout(self):
        self.assertEqual(self.v["layout"], "°M")

    def test_display(self):
        self.assertEqual(self.v["display_text"], "355°M")


class TestRudder(unittest.TestCase):
    """
    Rudder Angle: format 0x03, segment byte 0x8c → layout '=[data]'.
    '=' is B&G's alternative minus symbol; value is stored negative.
    Same frame as TestHeading.
    """
    FRAME = "ff120e01e00b038c024908cd634a0afbe13d492d"

    def setUp(self):
        self.v = _decode(self.FRAME)["Rudder Angle"]

    def test_value(self):
        self.assertEqual(self.v["value"], -2.0)

    def test_layout(self):
        self.assertEqual(self.v["layout"], "=[data]")

    def test_display(self):
        self.assertEqual(self.v["display_text"], "-2")


class TestCourse(unittest.TestCase):
    """
    Course (HDG + Leeway): format 0x08, layout '°M'.
    Heading on Next Tack: format 0x08, layout '°M'.
    Both from a 4-channel navigation broadcast.
    """
    FRAME = "ff051401e74a0afbe1fbe1824700d800006908cd639a08cce65e"

    def setUp(self):
        self.v = _decode(self.FRAME)

    def test_course_value(self):
        self.assertEqual(self.v["Course (HDG + Leeway)"]["value"], 355.0)

    def test_course_display(self):
        self.assertEqual(self.v["Course (HDG + Leeway)"]["display_text"], "355°M")

    def test_next_tack_value(self):
        self.assertEqual(self.v["Heading on Next Tack"]["value"], 230.0)

    def test_next_tack_display(self):
        self.assertEqual(self.v["Heading on Next Tack"]["display_text"], "230°M")

    def test_leeway_value(self):
        self.assertEqual(self.v["Leeway"]["value"], 0.0)


if __name__ == "__main__":
    unittest.main()
