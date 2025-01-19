import queue
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
            max_buffer_size (int): The maximum number of bytes to store in the queue.
        """
        self.buffer = queue.Queue(maxsize=max_buffer_size)  # Thread-safe queue for the buffer
        self.max_buffer_size = max_buffer_size


    def add_to_buffer(self, new_data):
        """
        Adds new data to the buffer.

        Args:
            new_data (bytes): New data from the serial input.
        """
        try:
            for byte in new_data:
                self.buffer.put_nowait(byte)  # Add byte-by-byte to the queue
            logger.debug(f"Added {len(new_data)} bytes to buffer. Current buffer size: {self.buffer.qsize()} bytes.")
        except queue.Full:
            logger.warning("Buffer size exceeded maximum limit. Oldest data will be dropped.")
            # Drop oldest data to accommodate new data
            while not self.buffer.empty() and len(new_data) > 0:
                self.buffer.get_nowait()  # Remove oldest byte
                new_data = new_data[1:]  # Keep remaining bytes
            self.add_to_buffer(new_data)  # Retry adding new data

    def get_complete_frames(self):
        """
        Extract and return complete frames from the buffer.
        """
        complete_frames = bytearray()
        # Retrieve all available data from the queue
        while not self.buffer.empty():
            complete_frames.append(self.buffer.get_nowait())  # Retrieve the data

        frames = []
        while len(complete_frames) >= 6:  # Minimum frame size (5 header + 1 body checksum)
            to_address = complete_frames[0]
            from_address = complete_frames[1]
            body_size = complete_frames[2]
            command = complete_frames[3]
            header_checksum = complete_frames[4]

            command_name = COMMAND_LOOKUP.get(command, f"Unknown (0x{command:02X})")
            full_frame_length = 5 + body_size + 1  # Header (5 bytes) + body + body checksum

            if len(complete_frames) < full_frame_length:
                logger.debug(f"Incomplete frame: waiting for more bytes (needed {full_frame_length}, got {len(complete_frames)})")
                break

            frame = complete_frames[:full_frame_length]
            body = frame[5:full_frame_length - 1]
            body_checksum = frame[full_frame_length - 1]

            # Validate checksums
            if calculate_checksum(frame[:4]) != header_checksum:
                logger.warning("Header checksum mismatch. Dropping first byte.")
                complete_frames.pop(0)  # Drop first byte and continue
                continue

            if calculate_checksum(body) != body_checksum:
                logger.warning("Body checksum mismatch. Dropping first byte.")
                complete_frames.pop(0)
                continue

            # Remove processed frame
            complete_frames = complete_frames[full_frame_length:]

            if command_name in ["Keep Alive", "Light Intensity"]:
                logger.debug(f"Ignoring {command_name} command.")
                continue

            if command_name == "LatLon":
                decoded_frame = decode_ascii_frame(frame)
                if decoded_frame:
                    frames.append(decoded_frame)
            elif command_name == "Broadcast":
                decoded_frame = decode_frame(frame)
                if decoded_frame:
                    frames.append(decoded_frame)

        return frames


    def get_buffer_size(self):
        """
        Returns the current size of the buffer.
        
        Returns:
            int: The number of bytes currently in the buffer.
        """
        buffer_size = self.buffer.qsize()
        logger.debug(f"Buffer size requested: {buffer_size} bytes.")
        return buffer_size


    def get_buffer_contents(self):
        """
        Returns the contents of the buffer as a hex string.
        
        Returns:
            str: The hexadecimal representation of the buffer contents.
        """
        buffer_copy = bytearray()

        # Retrieve all available bytes from the queue
        while not self.buffer.empty():
            buffer_copy.append(self.buffer.get_nowait())

        # Reinsert the data back into the queue to preserve its state
        for byte in buffer_copy:
            self.buffer.put_nowait(byte)

        hex_contents = buffer_copy.hex()
        logger.debug(f"Buffer contents: {hex_contents}")
        return hex_contents