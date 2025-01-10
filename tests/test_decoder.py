---

### **8. `tests/test_decoder.py`**
Basic unit tests for the library.
```python
import unittest
from fastnet_decoder.decode_fastnet import decode_frame

class TestDecoder(unittest.TestCase):
    def test_valid_frame(self):
        frame = b"\xFA\x05\x03\x41\xE8\x42\x01\x10\xD2"
        decoded = decode_frame(frame)
        self.assertIn("Boatspeed (Knots)", decoded["values"])

if __name__ == "__main__":
    unittest.main()