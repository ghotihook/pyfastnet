import unittest
from fastnet_decoder.decode_fastnet import decode_frame


def _decode(hex_str):
    result = decode_frame(bytes.fromhex(hex_str))
    assert "error" not in result, f"Decode error: {result}"
    return result["values"]


# ---------------------------------------------------------------------------
# Boatspeed — format 0x01 (16-bit signed, divisor 100) + 0x0A pair
# ---------------------------------------------------------------------------

class TestBoatspeed(unittest.TestCase):
    """
    Frame from Performance Processor containing Boatspeed (Knots) and
    Boatspeed (Raw). Raw uses format 0x0A — two 16-bit signed integers.
    """
    FRAME = "ff010a01f54192f9dd420a01ec082cea"

    def setUp(self):
        self.v = _decode(self.FRAME)

    def test_boatspeed_knots_value(self):
        self.assertAlmostEqual(self.v["Boatspeed (Knots)"]["value"], 4.77, places=2)

    def test_boatspeed_knots_display(self):
        self.assertEqual(self.v["Boatspeed (Knots)"]["display_text"], "4.77")

    def test_boatspeed_raw_display_pair(self):
        # format 0x0A renders as "first / second"
        self.assertIn(" / ", self.v["Boatspeed (Raw)"]["display_text"])


# ---------------------------------------------------------------------------
# Apparent wind — format 0x01 (AWS) + 0x07 with port layout (AWA)
# ---------------------------------------------------------------------------

class TestApparentWind(unittest.TestCase):
    """
    18-channel broadcast frame containing all three apparent wind channels.
    - AWS Knots / m/s: format 0x01, divisor 10
    - AWA: format 0x07, layout '[data]-' (trailing dash = port side)
    """
    FRAME = "ff051801e34e0a061c05fe4d51009c4f610050520a47f347f351032065a0"

    def setUp(self):
        self.v = _decode(self.FRAME)

    def test_aws_knots_value(self):
        self.assertAlmostEqual(self.v["Apparent Wind Speed (Knots)"]["value"], 15.6, places=1)

    def test_aws_knots_display(self):
        self.assertEqual(self.v["Apparent Wind Speed (Knots)"]["display_text"], "15.6")

    def test_aws_ms_value(self):
        self.assertAlmostEqual(self.v["Apparent Wind Speed (m/s)"]["value"], 8.0, places=1)

    def test_awa_value(self):
        # Port/starboard is encoded in layout, not value sign — value stays positive
        self.assertEqual(self.v["Apparent Wind Angle"]["value"], 101.0)

    def test_awa_layout_port(self):
        self.assertEqual(self.v["Apparent Wind Angle"]["layout"], "[data]-")

    def test_awa_display_port(self):
        # Trailing dash is the port indicator rendered in display_text
        self.assertEqual(self.v["Apparent Wind Angle"]["display_text"], "101-")


# ---------------------------------------------------------------------------
# True wind — format 0x01 (TWS) + 0x07 (TWA starboard, TWD °M, VMG)
# ---------------------------------------------------------------------------

class TestTrueWind(unittest.TestCase):
    """
    16-channel broadcast frame with all true wind and VMG channels.
    - TWA: format 0x07, layout '[data]=' (trailing equals = starboard)
    - TWD: format 0x07, layout '°M'
    - VMG: format 0x07
    """
    FRAME = "ff051601e5555100a656610055590328767f8700bb00db6d08cc7061"

    def setUp(self):
        self.v = _decode(self.FRAME)

    def test_tws_knots(self):
        self.assertAlmostEqual(self.v["True Wind Speed (Knots)"]["value"], 16.6, places=1)

    def test_tws_ms(self):
        self.assertAlmostEqual(self.v["True Wind Speed (m/s)"]["value"], 8.5, places=1)

    def test_twa_value(self):
        self.assertEqual(self.v["True Wind Angle"]["value"], 118.0)

    def test_twa_layout_starboard(self):
        # Trailing equals = starboard; value remains positive
        self.assertEqual(self.v["True Wind Angle"]["layout"], "[data]=")

    def test_twa_display_starboard(self):
        self.assertEqual(self.v["True Wind Angle"]["display_text"], "118=")

    def test_twd_value(self):
        self.assertEqual(self.v["True Wind Direction"]["value"], 112.0)

    def test_twd_layout_magnetic(self):
        self.assertEqual(self.v["True Wind Direction"]["layout"], "°M")

    def test_twd_display(self):
        self.assertEqual(self.v["True Wind Direction"]["display_text"], "112°M")

    def test_vmg(self):
        self.assertAlmostEqual(self.v["Velocity Made Good (Knots)"]["value"], 2.19, places=2)


# ---------------------------------------------------------------------------
# Heading and Rudder — format 0x08 (Heading °M) + 0x03 (Rudder signed)
# ---------------------------------------------------------------------------

class TestHeadingAndRudder(unittest.TestCase):
    """
    3-channel frame: Heading, Rudder Angle, Heading (Raw).
    - Heading: format 0x08, segment code 0x66 → layout '°M'
    - Rudder Angle: format 0x03, segment byte 0x8c → layout '=[data]',
      value is negative (sign from layout, not from the raw byte)
    - Heading (Raw): format 0x0A two-signed pair
    """
    FRAME = "ff120e01e00b038c024908cd634a0afbe13d492d"

    def setUp(self):
        self.v = _decode(self.FRAME)

    def test_heading_value(self):
        self.assertEqual(self.v["Heading"]["value"], 355.0)

    def test_heading_layout(self):
        self.assertEqual(self.v["Heading"]["layout"], "°M")

    def test_heading_display(self):
        self.assertEqual(self.v["Heading"]["display_text"], "355°M")

    def test_rudder_negative_value(self):
        # '=[data]' → _sign_from_layout returns -1; raw byte = 2 → value = -2
        self.assertEqual(self.v["Rudder Angle"]["value"], -2.0)

    def test_rudder_layout(self):
        self.assertEqual(self.v["Rudder Angle"]["layout"], "=[data]")

    def test_rudder_display(self):
        # No layout suffix for '=[data]'; sign appears in the formatted number
        self.assertEqual(self.v["Rudder Angle"]["display_text"], "-2")

    def test_heading_raw_is_pair(self):
        # format 0x0A always renders as "signed / signed"
        self.assertIn(" / ", self.v["Heading (Raw)"]["display_text"])

    def test_heading_raw_first_signed(self):
        # Both halves signed; first value should be negative here
        self.assertLess(self.v["Heading (Raw)"]["value"], 0)


# ---------------------------------------------------------------------------
# Course + Leeway + Heading on Next Tack — format 0x08 / 0x07
# ---------------------------------------------------------------------------

class TestCourseAndNavigation(unittest.TestCase):
    """
    4-channel frame: Heading (Raw), Leeway, Course (HDG+Leeway),
    Heading on Next Tack.
    Course and Heading on Next Tack use format 0x08 with '°M' layout.
    Leeway uses format 0x07 with an unrecognised segment code → layout '?'.
    """
    FRAME = "ff051401e74a0afbe1fbe1824700d800006908cd639a08cce65e"

    def setUp(self):
        self.v = _decode(self.FRAME)

    def test_course_value(self):
        self.assertEqual(self.v["Course (HDG + Leeway)"]["value"], 355.0)

    def test_course_layout(self):
        self.assertEqual(self.v["Course (HDG + Leeway)"]["layout"], "°M")

    def test_course_display(self):
        self.assertEqual(self.v["Course (HDG + Leeway)"]["display_text"], "355°M")

    def test_heading_on_next_tack_value(self):
        self.assertEqual(self.v["Heading on Next Tack"]["value"], 230.0)

    def test_heading_on_next_tack_layout(self):
        self.assertEqual(self.v["Heading on Next Tack"]["layout"], "°M")

    def test_heading_on_next_tack_display(self):
        self.assertEqual(self.v["Heading on Next Tack"]["display_text"], "230°M")

    def test_leeway_value(self):
        self.assertEqual(self.v["Leeway"]["value"], 0.0)


# ---------------------------------------------------------------------------
# Heel Angle + Fore/Aft Trim — format 0x07, sign from segment layout
# ---------------------------------------------------------------------------

class TestHeelAndTrim(unittest.TestCase):
    """
    Heel-port capture: Heel Angle and Fore/Aft Trim both use format 0x07.
    - Heel: segment byte 0xf3 → layout 'H[data]' (H prefix, value positive)
    - Trim: segment byte 0xa0 → layout '-[data]' (value negative = aft trim)

    Battery Volts is also in this frame: format 0x01, divisor 100.
    """
    FRAME = "ff051401e78d8105263b3101fa344700f300cc9b4700a000099b"

    def setUp(self):
        self.v = _decode(self.FRAME)

    def test_heel_positive_value(self):
        # 'H[data]' does NOT flip sign — port heel is still stored positive
        self.assertAlmostEqual(self.v["Heel Angle"]["value"], 20.4, places=1)

    def test_heel_layout(self):
        self.assertEqual(self.v["Heel Angle"]["layout"], "H[data]")

    def test_heel_display_prefix(self):
        # H prefix indicates port side on the instrument display
        self.assertEqual(self.v["Heel Angle"]["display_text"], "H20.4")

    def test_trim_negative_value(self):
        # '-[data]' drives sign negative
        self.assertAlmostEqual(self.v["Fore/Aft Trim"]["value"], -0.9, places=1)

    def test_trim_layout(self):
        self.assertEqual(self.v["Fore/Aft Trim"]["layout"], "-[data]")

    def test_trim_display(self):
        # No suffix; sign is embedded in the formatted number
        self.assertEqual(self.v["Fore/Aft Trim"]["display_text"], "-0.9")

    def test_battery_volts(self):
        self.assertAlmostEqual(self.v["Battery Volts"]["value"], 13.18, places=2)
        self.assertEqual(self.v["Battery Volts"]["display_text"], "13.18")


# ---------------------------------------------------------------------------
# Sea Temperature — format 0x07, unrecognised segment code → layout '?'
# ---------------------------------------------------------------------------

class TestSeaTemperature(unittest.TestCase):
    """
    Stored-log frame also carries sea temperature in Celsius and Fahrenheit.
    Format 0x07 with a segment byte not present in SEGMENT_A → layout '?'.
    Cross-check: 23 °C ≈ 73 °F within 1 degree rounding.
    """
    FRAME = "ff011801e7cd840000acc7cf84ff0000001f17005c00171e17007400494f"

    def setUp(self):
        self.v = _decode(self.FRAME)

    def test_sea_temp_celsius(self):
        self.assertEqual(self.v["Sea Temperature (°C)"]["value"], 23.0)
        self.assertEqual(self.v["Sea Temperature (°C)"]["display_text"], "23")

    def test_sea_temp_fahrenheit(self):
        self.assertEqual(self.v["Sea Temperature (°F)"]["value"], 73.0)
        self.assertEqual(self.v["Sea Temperature (°F)"]["display_text"], "73")

    def test_cross_unit_consistency(self):
        c = self.v["Sea Temperature (°C)"]["value"]
        f = self.v["Sea Temperature (°F)"]["value"]
        self.assertAlmostEqual(c * 9 / 5 + 32, f, delta=1.0)


# ---------------------------------------------------------------------------
# Navigation Log — format 0x04 (3-byte unsigned, divisor 100)
# ---------------------------------------------------------------------------

class TestNavigationLog(unittest.TestCase):
    """
    Stored Log and Trip Log from the same frame as sea temperature.
    Format 0x04: 4-byte payload, value taken from bytes[1:] (big-endian unsigned).
    Divisor 100 → two decimal places.
    """
    FRAME = "ff011801e7cd840000acc7cf84ff0000001f17005c00171e17007400494f"

    def setUp(self):
        self.v = _decode(self.FRAME)

    def test_stored_log_value(self):
        self.assertAlmostEqual(self.v["Stored Log (NM)"]["value"], 442.31, places=2)

    def test_stored_log_display(self):
        self.assertEqual(self.v["Stored Log (NM)"]["display_text"], "442.31")

    def test_trip_log_zero(self):
        self.assertEqual(self.v["Trip Log (NM)"]["value"], 0.0)
        self.assertEqual(self.v["Trip Log (NM)"]["display_text"], "0.00")


# ---------------------------------------------------------------------------
# Timer — format 0x05 (H/M/S bytes → total seconds + HH:MM:SS display)
# ---------------------------------------------------------------------------

class TestTimer(unittest.TestCase):
    """
    Timer channel uses format 0x05: data bytes [unused, H, M, S].
    value = total seconds; display_text = timedelta string (H:MM:SS).
    """
    FRAME = "ff050601f5750501072c064c"

    def setUp(self):
        self.v = _decode(self.FRAME)

    def test_timer_total_seconds(self):
        # 7 h × 3600 + 44 min × 60 + 6 s = 27846
        self.assertEqual(self.v["Timer"]["value"], 27846.0)

    def test_timer_display_hms(self):
        self.assertEqual(self.v["Timer"]["display_text"], "7:44:06")


# ---------------------------------------------------------------------------
# Speed and Course Over Ground — format 0x01, from NMEA FFD frame
# ---------------------------------------------------------------------------

class TestSpeedAndCourseOverGround(unittest.TestCase):
    """
    SOG / COG True / COG Mag from an NMEA FFD broadcast.
    - SOG: format 0x01, divisor 10
    - COG: format 0x01, divisor 1 (integer degrees)
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
        self.assertEqual(self.v["Course Over Ground (Mag)"]["display_text"], "347")

    def test_cog_true_value(self):
        self.assertEqual(self.v["Course Over Ground (True)"]["value"], 0.0)


# ---------------------------------------------------------------------------
# Autopilot modes — format 0x01 raw int mapped to mode name string
# ---------------------------------------------------------------------------

class TestAutopilotModes(unittest.TestCase):
    """
    Autopilot Mode channel (0xB5) uses format 0x01 with a special-case
    lookup: the raw 16-bit integer is mapped to a mode name string.

    Three frames cover Standby, Compass and Wind modes.
    In Standby the companion Target channel is OFF (value=None).
    In Compass/Wind modes, Autopilot Compass Target carries a °M bearing.
    """
    STANDBY_FRAME = "ff121c01d2b5015004a606bee8e800af06bee8e8005306bee8e8007606bee8e80088"
    COMPASS_FRAME = "ff120a01e4b5015101a60700660000e5"
    WIND_FRAME    = "ff120a01e4b5015104a6070066014b96"

    def _v(self, hex_str):
        return _decode(hex_str)

    def test_standby_mode_display(self):
        self.assertEqual(self._v(self.STANDBY_FRAME)["Autopilot Mode"]["display_text"], "Standby")

    def test_standby_target_is_off(self):
        v = self._v(self.STANDBY_FRAME)
        self.assertIsNone(v["Autopilot Compass Target"]["value"])
        self.assertEqual(v["Autopilot Compass Target"]["display_text"], "OFF ")

    def test_compass_mode_display(self):
        self.assertEqual(self._v(self.COMPASS_FRAME)["Autopilot Mode"]["display_text"], "Compass")

    def test_compass_target_value(self):
        v = self._v(self.COMPASS_FRAME)
        self.assertEqual(v["Autopilot Compass Target"]["value"], 0.0)

    def test_compass_target_layout(self):
        v = self._v(self.COMPASS_FRAME)
        self.assertEqual(v["Autopilot Compass Target"]["layout"], "°M")

    def test_compass_target_display(self):
        v = self._v(self.COMPASS_FRAME)
        self.assertEqual(v["Autopilot Compass Target"]["display_text"], "0°M")

    def test_wind_mode_display(self):
        self.assertEqual(self._v(self.WIND_FRAME)["Autopilot Mode"]["display_text"], "Wind")

    def test_wind_target_value(self):
        v = self._v(self.WIND_FRAME)
        self.assertEqual(v["Autopilot Compass Target"]["value"], 331.0)

    def test_wind_target_display(self):
        v = self._v(self.WIND_FRAME)
        self.assertEqual(v["Autopilot Compass Target"]["display_text"], "331°M")


if __name__ == "__main__":
    unittest.main()
