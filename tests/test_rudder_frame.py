import unittest
from fastnet_decoder.decode_fastnet import decode_frame

class TestCustomFrame(unittest.TestCase):
    def test_custom_frame(self):
        """
        Test decoding a custom frame using the provided hex string.
        """
        # Hex string provided by the user

        hex_string = "ff120e01e00b038c274908cc294a0a1cdd6067e5"
        #hex_string = "ff051801e34e0a02c402754d6100464f610024520af683f6835113a0064b"
        
        # Convert hex string to bytes
        frame_data = bytes.fromhex(hex_string)

        # Decode the frame
        decoded = decode_frame(frame_data)

        # Validate the output
        self.assertIsInstance(decoded, dict, "Decoded frame should return a dictionary")
        self.assertIn("command", decoded, "Decoded frame should have a command field")
        self.assertIn("values", decoded, "Decoded frame should have a values dictionary")

        # Print decoded contents for debugging
        print("Decoded frame contents:")
        for key, value in decoded.items():
            print(f"{key}: {value}")

        # Example assertion: Ensure no error in decoding
        self.assertNotIn("error", decoded, "Frame should not return an error during decoding")

if __name__ == "__main__":
    unittest.main()
