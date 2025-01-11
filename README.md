# pyfastnet
Fastnet is the propriatory protocol used by B&G on some older instruments, tested on Hydra/H2000. It might work on other systems. I developed this for personal use and publishing for general interest only. 

# Purpose
This library can be fed a stream of fastnet data, it will decode and return structured instrument data for further processing. Syncronisation, checksum and decoding is handled by the library.

# Example input/output
Byte string from Fastnet including "FF051601E555610030566100185903A86B7F8700BB00016D08CD0DCB"

to_address: Entire System  
from_address: Normal CPU (Wind Board in H2000)  
command: Broadcast  
- **True Wind Speed (Knots)**:  
  - `channel_id`: `0x55`  
  - `interpreted`: 4.8  

- **True Wind Speed (m/s)**:  
  - `channel_id`: `0x56`  
  - `interpreted`: 2.4  

- **True Wind Angle**:  
  - `channel_id`: `0x59`  
  - `interpreted`: 107.0  

- **Velocity Made Good (Knots)**:  
  - `channel_id`: `0x7F`  
  - `interpreted`: 0.01  

- **True Wind Direction**:  
  - `channel_id`: `0x6D`  
  - `interpreted`: 269.0  


# Important library calls - function
- ```fastnetframebuffer.add_to_buffer(raw_input_data)```
- ```fastnetframebuffer.get_complete_frames()```

# # Important library calls - debug
- ```set_log_level(DEBUG)```
- ```fastnetframebuffer.get_buffer_size()```
- ```fastnetframebuffer.get_buffer_contents()```

# Companion App
- A full implementation can be found here, it takes input from a serial port or dummy file and broadcasts NMEA messages via UDP [fastnet2ip](https://github.com/ghotihook/fastnet2ip) 

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