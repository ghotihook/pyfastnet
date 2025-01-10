from .utils import calculate_checksum  # Import checksum function from utils.py
from .mappings import COMMAND_LOOKUP  # Import your command mappings
from .decode_fastnet import decode_frame, decode_ascii_frame
from .logger import logger

class FrameBuffer:
    """
    A class that manages an incoming data stream, extracts valid frames,
    and decodes them using the FastNet protocol.
    """
    def __init__(self, max_buffer_size=8192):
        """
        Initializes the FrameBuffer.

        Args:
            max_buffer_size (int): The maximum size of the buffer to avoid unbounded growth.
        """
        self.buffer = bytearray()  # Holds incoming data
        self.max_buffer_size = max_buffer_size  # Limit buffer size to prevent memory issues

    def add_to_buffer(self, new_data):
        """
        Adds new data to the buffer.

        Args:
            new_data (bytes): New data from the serial input.
        """
        self.buffer.extend(new_data)
        logger.debug(f"Added {len(new_data)} bytes to buffer. Buffer size: {len(self.buffer)} bytes.")

        # Prevent the buffer from growing indefinitely
        if len(self.buffer) > self.max_buffer_size:
            logger.warning("Buffer size exceeded maximum limit. Trimming the oldest data.")
            self.buffer = self.buffer[-self.max_buffer_size:]  # Keep the latest data only

    def get_complete_frames(self):
        """
        Extract and return complete frames from the buffer.
        """
        complete_frames = []
        while len(self.buffer) >= 6:  # Minimum frame size (5 header + 1 body checksum)
            to_address = self.buffer[0]
            from_address = self.buffer[1]
            body_size = self.buffer[2]
            command = self.buffer[3]
            header_checksum = self.buffer[4]

            # Identify command name from lookup
            command_name = COMMAND_LOOKUP.get(command, f"Unknown (0x{command:02X})")
            #logger.debug(f"Scanning frame. Command: {command_name}, to_address: 0x{to_address:02X}, from_address: 0x{from_address:02X}")

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
                logger.warning(f"Header checksum mismatch. Dropping first byte.")
                self.buffer.pop(0)  # Drop first byte and continue
                continue

            if calculate_checksum(body) != body_checksum:
                logger.warning(f"Body checksum mismatch. Dropping first byte.")
                self.buffer.pop(0)
                continue

            # Remove frame from buffer after validation
            self.buffer = self.buffer[full_frame_length:]

            # Command-based processing
            if command_name == "Keep Alive":
                logger.debug(f"Ignoring Keep Alive command.")
                continue  # Skip adding to complete_frames

            if command_name == "Light Intensity":
                logger.debug(f"Ignoring Light Intensity command.")
                continue  # Skip adding to complete_frames

            if command_name == "LatLon":
                logger.debug(f"Decoding ASCII LatLon frame.")
                decoded_frame = decode_ascii_frame(frame)  # Use a specific decoder for LatLon frames
                if decoded_frame:
                    complete_frames.append(decoded_frame)
            
            elif command_name == "Broadcast":
                logger.debug(f"Processing Broadcast frame.")
                decoded_frame = decode_frame(frame)  # Standard decoder
                if decoded_frame:
                    complete_frames.append(decoded_frame)
            else:
                logger.debug(f"Unknown command {command_name}. Full Frame:{frame.hex()}")

        return complete_frames