from .utils import calculate_checksum  # Import checksum function from utils.py
from .mappings import COMMAND_LOOKUP, IGNORED_COMMANDS
from .decode_fastnet import decode_frame, decode_ascii_frame
from .logger import logger
from queue import Queue


"""
FrameBuffer Class
=================

The `FrameBuffer` class is responsible for managing a stream of incoming data, validating and extracting complete 
frames, and decoding those frames using the FastNet protocol. It is designed to handle real-time data input, making 
it suitable for scenarios like serial communication with hardware devices.

Core Responsibilities:
-----------------------
1. **Buffer Management**:
   - The class maintains an internal `bytearray` buffer to store incoming raw data.
   - New data can be added to the buffer using the `add_to_buffer` method.
   - The buffer automatically trims its size to a configurable maximum (`max_buffer_size`) to avoid unbounded memory usage.

2. **Frame Extraction**:
   - The `get_complete_frames` method scans the buffer for complete frames based on the FastNet protocol structure:
     - A frame consists of a 5-byte header, a variable-length body, and a checksum.
     - Both the header and body checksums are validated before processing the frame.
   - Frames that are incomplete or fail checksum validation are skipped, and the buffer is adjusted to search for the next valid frame.

3. **Frame Decoding**:
   - After extracting a valid frame, the method determines the appropriate decoder (ASCII or standard) based on the command type.
   - Decoded frames are added to an internal queue (`frame_queue`) for further processing.

4. **Command Filtering**:
   - Certain command types, such as "Keep Alive" or "Light Intensity," can be ignored based on a configurable list of ignored commands 
     (managed in the `mappings.py` file).

Key Features:
-------------
- **Thread-Safe Queue**:
  The `frame_queue` is implemented using Python's `queue.Queue`, enabling safe concurrent access from multiple threads 
  (if needed).

- **Error Handling**:
  - The class is robust against malformed or corrupted data. Frames with invalid checksums are discarded without crashing the application.
  - Warnings and errors are logged for debugging purposes.

- **Modularity**:
  - The decoding logic is separated from the frame extraction, adhering to the single-responsibility principle.
  - The list of ignored commands is managed in `mappings.py`, promoting modularity and ease of configuration.

Typical Workflow:
-----------------
1. Raw data (e.g., from a serial port) is fed into the buffer using the `add_to_buffer` method.
2. The `get_complete_frames` method scans the buffer for valid frames, processes them, and adds decoded frames to the `frame_queue`.
3. Another part of the application (e.g., a main loop) retrieves and processes frames from the queue for further action (e.g., broadcasting NMEA sentences).

Configuration Parameters:
-------------------------
- `max_buffer_size`: Limits the size of the internal buffer. Older data is discarded when the buffer exceeds this size.
- `max_queue_size`: Specifies the maximum number of frames that can be stored in the `frame_queue`.

Use Cases:
----------
The `FrameBuffer` class is ideal for:
- Real-time data processing systems where incoming data must be validated and decoded before use.
- Applications where reliability is critical, such as navigation systems or hardware communication protocols.

Example:
--------
# Initialize the FrameBuffer
frame_buffer = FrameBuffer(max_buffer_size=8192, max_queue_size=1000)

# Add raw data to the buffer
frame_buffer.add_to_buffer(new_data)

# Extract and decode complete frames
frame_buffer.get_complete_frames()

# Process frames from the queue
while not frame_buffer.frame_queue.empty():
    frame = frame_buffer.frame_queue.get()
    # Process the decoded frame
"""


class FrameBuffer:
    """
    A class that manages an incoming data stream, extracts valid frames,
    and decodes them using the FastNet protocol.
    """
    def __init__(self, max_buffer_size=8192, max_queue_size=1000):
        self.buffer = bytearray()
        self.max_buffer_size = max_buffer_size
        self.frame_queue = Queue(maxsize=max_queue_size)  # Shared instance for frames

    def add_to_buffer(self, new_data):
        """
        Adds new data to the buffer.

        Args:
            new_data (bytes): New data from the serial input.
        """
        if not isinstance(new_data, (bytes, bytearray)):
            logger.error("Invalid data type passed to add_to_buffer. Expected bytes or bytearray.")
            return

        self.buffer.extend(new_data)
        logger.debug(f"Added {len(new_data)} bytes to buffer. Buffer size: {len(self.buffer)} bytes.")

        # Prevent the buffer from growing indefinitely
        if len(self.buffer) > self.max_buffer_size:
            logger.warning("Buffer size exceeded maximum limit. Trimming the oldest data.")
            self.buffer = self.buffer[-self.max_buffer_size:]  # Keep the latest data only

  
    def get_complete_frames(self):
        """
        Extract and validate complete frames from the buffer, then add them to the internal queue.
        """
        while len(self.buffer) >= 6:  # Minimum frame size (5 header + 1 body checksum)
            to_address = self.buffer[0]
            from_address = self.buffer[1]
            body_size = self.buffer[2]
            command = self.buffer[3]
            header_checksum = self.buffer[4]

            # Identify command name from lookup
            command_name = COMMAND_LOOKUP.get(command, f"Unknown (0x{command:02X})")

            # Calculate full frame length
            full_frame_length = 5 + body_size + 1  # Header (5 bytes) + body + body checksum
            if len(self.buffer) < full_frame_length:
                logger.debug(f"Incomplete frame: waiting for more bytes (needed {full_frame_length}, got {len(self.buffer)})")
                break

            # Extract frame data
            frame = self.buffer[:full_frame_length]
            body = self.buffer[5:full_frame_length - 1]
            body_checksum = self.buffer[full_frame_length - 1]

            # Verify header and body checksums
            if calculate_checksum(self.buffer[:4]) != header_checksum:
                logger.warning("Header checksum mismatch. Dropping first byte.")
                self.buffer = self.buffer[1:]
                continue

            if calculate_checksum(body) != body_checksum:
                logger.warning("Body checksum mismatch. Dropping first byte.")
                self.buffer = self.buffer[1:]
                continue

            # Remove frame from buffer after validation
            self.buffer = self.buffer[full_frame_length:]

            # Skip ignored commands
            if command_name in IGNORED_COMMANDS:
                logger.debug(f"Skipping ignored command: {command_name}")
                continue

            # Decode the frame
            self.decode_and_queue_frame(frame, command_name)



                
    def get_buffer_size(self):
        """
        Returns the current size of the buffer.
        
        Returns:
            int: The number of bytes currently in the buffer.
        """
        return len(self.buffer)


    def get_buffer_contents(self):
        """
        Returns the contents of the buffer as a hex string.
        
        Returns:
            str: The hexadecimal representation of the buffer contents.
        """
        hex_contents = self.buffer.hex()
        logger.debug(f"Buffer contents: {hex_contents}")
        return hex_contents