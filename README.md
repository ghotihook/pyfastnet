# pyfastnet
Fastnet is the propriatory protocol used by B&G on some older instruments, tested on Hydra/H2000. It might work on other systems. I developed this for personal use and publishing for general interest only. 

# Purpose
This library can be fed a stream of fastnet data, it will decode and return structured instrument data for further processing

# Example input/output
Byte string from Fastnet including "ff010a01f541910000420a00000000e2ff050c01ef4e0a02750222520a1a4f1a4fdf"

The decoded values from the frame look like this:
```python
values: {'Boatspeed (Knots)': {'channel_id': '0x41', 'format_byte': '0x91', 'data_bytes': '0000', 'divisor': 100, 'digits': 2, 'format_bits': 1, 'raw': 0, 'interpreted': 0.0}, 'Boatspeed (Raw)': {'channel_id': '0x42', 'format_byte': '0x0A', 'data_bytes': '00000000', 'divisor': 1, 'digits': 1, 'format_bits': 10, 'raw': {'first_raw': 0, 'second_raw': 0}, 'interpreted': {'first': 0.0, 'second': 0.0}}, 'Unknown (0xE2)': None, 'Unknown (0x05)': None, 'Unknown (0x01)': None, 'Apparent Wind Speed (Raw)': {'channel_id': '0x4E', 'format_byte': '0x0A', 'data_bytes': '02750222', 'divisor': 1, 'digits': 1, 'format_bits': 10, 'raw': {'first_raw': 629, 'second_raw': 546}, 'interpreted': {'first': 629.0, 'second': 546.0}}, 'Apparent Wind Angle (Raw)': {'channel_id': '0x52', 'format_byte': '0x0A', 'data_bytes': '1a4f1a4f', 'divisor': 1, 'digits': 1, 'format_bits': 10, 'raw': {'first_raw': 6735, 'second_raw': 6735}, 'interpreted': {'first': 6735.0, 'second': 6735.0}}}

# Important library calls
- 'fastnetframebuffer.add_to_buffer(raw_input_data)'
- 'fastnetframebuffer.get_complete_frames()'
- 'set_log_level(DEBUG)'

# Companion App
- [Fastnet to NMEA converter](https://github.com/ghotihook/FN2IP) 

# Installation
pip3 install pyfastnet

On a raspberry pi this is done from with a virtual env
python -m venv --system-site-packages ~/python_environment
source ~/python_environment/bin/activate
pip3 install pyfastnet
deactivate

~/python_environment/bin/python3 myapp.py 



## Acknowledgments / References

- [trlafleur - Collector of significant background](https://github.com/trlafleur) 
- [Oppedijk - Background](https://www.oppedijk.com/bandg/fastnet.html)
- [timmathews - Significant implementation in Cpp](https://github.com/timmathews/bg-fastnet-driver)
- Significant help from chatGPT!