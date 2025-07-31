# pyfastnet
Fastnet is the propriatory protocol used by B&G on some older instruments, tested on Hydra/H2000. It might work on other systems. I developed this for personal use and publishing for general interest only. 

# Purpose
This library can be fed a stream of fastnet data, it will decode and return structured instrument data for further processing. Syncronisation, checksum and decoding is handled by the library.

# Companion App
- A full implementation can be found here, it takes input from a serial port or dummy file and broadcasts NMEA messages via UDP [fastnet2ip](https://github.com/ghotihook/fastnet2ip) Easy to install on a raspberry pi, core mp135, mac, linux.

# Example input/output
Byte string from Fastnet including "ff051801e34e0a02c402754d6100464f610024520af683f6835113a0064b"

to_address: Entire System
from_address: Normal CPU (Wind Board in H2000)
command: Broadcast
values: 
```
{
  'Apparent Wind Speed (Raw)': {'channel_id': '0x4E', 'format_byte': '0x0A', 'data_bytes': '02c40275', 'divisor': 1, 'digits': 1, 'format_bits': 10, 'raw': {'first': 708.0, 'second': 629.0}, 'interpreted': 708.0}, 

  'Apparent Wind Speed (Knots)': {'channel_id': '0x4D', 'format_byte': '0x61', 'data_bytes': '0046', 'divisor': 10, 'digits': 3, 'format_bits': 1, 'raw': 70, 'interpreted': 7.0}, 
  
  'Apparent Wind Speed (m/s)': {'channel_id': '0x4F', 'format_byte': '0x61', 'data_bytes': '0024', 'divisor': 10, 'digits': 3, 'format_bits': 1, 'raw': 36, 'interpreted': 3.6}, 
  
  'Apparent Wind Angle (Raw)': {'channel_id': '0x52', 'format_byte': '0x0A', 'data_bytes': 'f683f683', 'divisor': 1, 'digits': 1, 'format_bits': 10, 'raw': {'first': -2429.0, 'second': -2429.0}, 'interpreted': -2429.0}, 
  
  'Apparent Wind Angle': {'channel_id': '0x51', 'format_byte': '0x13', 'data_bytes': 'a006', 'divisor': 1, 'digits': 2, 'format_bits': 3, 'raw': {'segment_code': '0xa0', 'segment_code_bin': '0b10100000', 'unsigned_value': 6, 'layout': '-[data]'}, 'interpreted': -6.0}}
```

# Example implementation
```
#!/usr/bin/env python3
import serial
import time
from pprint import pprint
from fastnet_decoder import FrameBuffer

def main():
    fb = FrameBuffer()
    # open /dev/ttyUSB0 at 28,800 baud, 8E2, 0.1 s timeout
    ser = serial.Serial(
        port="/dev/ttyUSB0",
        baudrate=28800,
        bytesize=serial.EIGHTBITS,
        stopbits=serial.STOPBITS_TWO,
        parity=serial.PARITY_ODD,
        timeout=0.1
    )

    try:
        while True:
            data = ser.read(256)
            if not data:
                time.sleep(0.01)
                continue

            # 1) feed raw bytes into the frame buffer
            fb.add_to_buffer(data)

            # 2) extract & decode any complete frames
            fb.get_complete_frames()

            # 3) peek at the entire queue as a list
            queue_contents = list(fb.frame_queue.queue)
            if queue_contents:
                print("Current decoded frames in queue:")
                pprint(queue_contents)
            else:
                print("Queue is empty.")

            # 4) (optionally) drain the queue for processing
            while not fb.frame_queue.empty():
                frame = fb.frame_queue.get()
                # replace this with whatever you need
                print("Processing frame:", frame)

    except KeyboardInterrupt:
        print("Stopping…")
    finally:
        ser.close()

if __name__ == "__main__":
    main()
```


# Important library calls - debug
- ```set_log_level(DEBUG)```
- ```fastnetframebuffer.get_buffer_size()```
- ```fastnetframebuffer.get_buffer_contents()```



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