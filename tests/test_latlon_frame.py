import unittest
from fastnet_decoder.decode_fastnet import decode_ascii_frame


class TestLatLonFrame(unittest.TestCase):
    """
    Tests for LatLon (position) command frames (command 0x03).

    These frames are dispatched to decode_ascii_frame, which carries the raw
    coordinate string in display_text. The entry is named from the command
    ("LatLon") — NOT from body[0]. body[0] is a per-source marker byte that
    varies by GPS unit (0x4E, 0x47, ...) and is not a generic channel id, so
    it must not be looked up in CHANNEL_LOOKUP (doing so previously mislabelled
    positions as "Apparent Wind Speed (Raw)").
    """

    # Real frame, from_address 0x60 (External Compass NMEA FFD 60).
    # body[0] = 0x4E. Position: 33°52.450'S, 151°13.920'E (Sydney).
    FRAME_4E = "ff601503894e50333335322e3435305331353131332e3932304572"

    # Real frame, from_address 0x62 (External Compass NMEA FFD 62).
    # body[0] = 0x47. Position: 16°46.61'S, 179°20.23'E.
    FRAME_47 = "ff621503874750313634362e3631205331373932302e3233204595"

    def test_4e_source_keyed_latlon(self):
        values = decode_ascii_frame(bytes.fromhex(self.FRAME_4E))["values"]
        self.assertIn("LatLon", values)
        self.assertNotIn("Apparent Wind Speed (Raw)", values)
        entry = values["LatLon"]
        self.assertEqual(entry["channel_id"], "0x4E")
        self.assertEqual(entry["display_text"], "3352.450S15113.920E")
        self.assertIsNone(entry["value"])

    def test_47_source_keyed_latlon(self):
        values = decode_ascii_frame(bytes.fromhex(self.FRAME_47))["values"]
        self.assertIn("LatLon", values)
        entry = values["LatLon"]
        self.assertEqual(entry["channel_id"], "0x47")
        self.assertEqual(entry["display_text"], "1646.61 S17920.23 E")
        self.assertIsNone(entry["value"])

    def test_both_sources_share_one_key(self):
        # The fix normalises differing source bytes to a single consistent key.
        keys_4e = set(decode_ascii_frame(bytes.fromhex(self.FRAME_4E))["values"])
        keys_47 = set(decode_ascii_frame(bytes.fromhex(self.FRAME_47))["values"])
        self.assertEqual(keys_4e, keys_47, {"LatLon"})

    def test_command_metadata(self):
        decoded = decode_ascii_frame(bytes.fromhex(self.FRAME_4E))
        self.assertNotIn("error", decoded)
        self.assertEqual(decoded["command"], "LatLon")
        self.assertEqual(decoded["from_address"], "External Compass (NMEA FFD 60)")


if __name__ == "__main__":
    unittest.main()
