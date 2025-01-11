# pyfastnet
Fastnet is the propriatory protocol used by B&G on some older instruments, tested on Hydra/H2000. It might work on other systems. I developed this for personal use and publishing for general interest only. 

# Purpose
This library can be fed a stream of fastnet data, it will decode and return structured instrument data for further processing. Syncronisation, checksum and decoding is handled by the library.

# Example input/output
Byte string from Fastnet including "FF051601E555610030566100185903A86B7F8700BB00016D08CD0DCB"

The decoded values from the frame look like this:
to_address: Entire System  
from_address: Normal CPU (Wind Board in H2000)  
command: Broadcast  

**values:**  
- **True Wind Speed (Knots)**:  
  - `channel_id`: `0x55`  
  - `format_byte`: `0x61`  
  - `data_bytes`: `0030`  
  - `divisor`: 10  
  - `digits`: 3  
  - `format_bits`: 1  
  - `raw`: 48  
  - `interpreted`: 4.8  

- **True Wind Speed (m/s)**:  
  - `channel_id`: `0x56`  
  - `format_byte`: `0x61`  
  - `data_bytes`: `0018`  
  - `divisor`: 10  
  - `digits`: 3  
  - `format_bits`: 1  
  - `raw`: 24  
  - `interpreted`: 2.4  

- **True Wind Angle**:  
  - `channel_id`: `0x59`  
  - `format_byte`: `0x03`  
  - `data_bytes`: `a86b`  
  - `divisor`: 1  
  - `digits`: 1  
  - `format_bits`: 3  
  - `raw`: `{segment_code: 84, unsigned_value: 107}`  
  - `interpreted`: 107.0  

- **Velocity Made Good (Knots)**:  
  - `channel_id`: `0x7F`  
  - `format_byte`: `0x87`  
  - `data_bytes`: `00bb0001`  
  - `divisor`: 100  
  - `digits`: 1  
  - `format_bits`: 7  
  - `raw`: 1  
  - `interpreted`: 0.01  

- **True Wind Direction**:  
  - `channel_id`: `0x6D`  
  - `format_byte`: `0x08`  
  - `data_bytes`: `cd0d`  
  - `divisor`: 1  
  - `digits`: 1  
  - `format_bits`: 8  
  - `raw`: `{segment_code: 102, unsigned_value: 269}`  
  - `interpreted`: 269.0  


# Important library calls
- ```fastnetframebuffer.add_to_buffer(raw_input_data)```
- ```fastnetframebuffer.get_complete_frames()```
- ```set_log_level(DEBUG)```

# Companion App
- [Fastnet to NMEA converter](https://github.com/ghotihook/FN2IP) 

# Installation
```pip3 install pyfastnet```

On a raspberry pi and some other systems this is done from with a virtual env

```python -m venv --system-site-packages ~/python_environment
source ~/python_environment/bin/activate
pip3 install pyfastnet
deactivate
~/python_environment/bin/python3 pyfastnet.py -h 
```


## Acknowledgments / References

- [trlafleur - Collector of significant background](https://github.com/trlafleur) 
- [Oppedijk - Background](https://www.oppedijk.com/bandg/fastnet.html)
- [timmathews - Significant implementation in Cpp](https://github.com/timmathews/bg-fastnet-driver)
- Significant help from chatGPT!