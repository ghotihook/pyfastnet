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