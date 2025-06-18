import unittest
from fastnet_decoder.decode_fastnet import decode_frame

class TestCustomFrame(unittest.TestCase):
    def test_custom_frame(self):
        """
        Test decoding a custom frame using the provided hex string.
        """
        # Hex string provided by the user

        hex_string = "ff051401e78d8105263b3101fb344700f300c59b4700a00009a1" #heel to port
        #hex_string = "ff051401e78d8105213b3101fb3447007301529b4700a0000899" #heel to stb
     
        
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
