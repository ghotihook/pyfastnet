import logging
from .utils import calculate_checksum
from .interpreter import COMMAND_LOOKUP, IGNORED_COMMANDS
from .interpreter import decode_frame, decode_ascii_frame, decode_light_frame, probe_frame
from . import interpreter
from .logger import logger
from queue import Queue, Full


class FrameBuffer:
    """
    Manages an incoming byte stream, extracts valid FastNet frames,
    decodes them, and queues the results.

    Typical workflow:
        1. Feed raw bytes via add_to_buffer()
        2. Call get_complete_frames() to process the buffer
        3. Pull decoded frames from frame_queue
    """

    def __init__(self, max_buffer_size=8192, max_queue_size=1000, project=True):
        self.buffer = bytearray()
        self.max_buffer_size = max_buffer_size
        self.frame_queue = Queue(maxsize=max_queue_size)
        # v3: queue the {signalk_path: SI_value} projection by default. project=False
        # queues the complete (rich) decode instead — for the golden guard / debugging.
        self.project = project

    def add_to_buffer(self, new_data):
        if not isinstance(new_data, (bytes, bytearray)):
            logger.error("Invalid data type passed to add_to_buffer. Expected bytes or bytearray.")
            return

        self.buffer.extend(new_data)
        logger.debug(f"BUF   +{len(new_data)}B  total={len(self.buffer)}B")

        if len(self.buffer) > self.max_buffer_size:
            logger.warning("Buffer size exceeded maximum limit. Trimming the oldest data.")
            self.buffer = self.buffer[-self.max_buffer_size:]

    def get_complete_frames(self):
        """Extract, validate, and queue complete frames from the buffer."""
        while len(self.buffer) >= 6:
            to_address      = self.buffer[0]
            from_address    = self.buffer[1]
            body_size       = self.buffer[2]
            command         = self.buffer[3]
            header_checksum = self.buffer[4]

            command_name     = COMMAND_LOOKUP.get(command, f"Unknown (0x{command:02X})")
            full_frame_length = 5 + body_size + 1

            if len(self.buffer) < full_frame_length:
                logger.debug(f"FRAME wait    need={full_frame_length}B  have={len(self.buffer)}B")
                break

            frame         = self.buffer[:full_frame_length]
            body          = self.buffer[5:full_frame_length - 1]
            body_checksum = self.buffer[full_frame_length - 1]

            debug = logger.isEnabledFor(logging.DEBUG)

            if calculate_checksum(self.buffer[:4]) != header_checksum:
                if debug:
                    logger.debug(f"FRAME discard  header-checksum  [{bytes(frame).hex()}]")
                self.buffer = self.buffer[1:]
                continue

            if calculate_checksum(body) != body_checksum:
                if debug:
                    logger.debug(f"FRAME discard  body-checksum  [{bytes(frame).hex()}]")
                self.buffer = self.buffer[1:]
                continue

            self.buffer = self.buffer[full_frame_length:]

            if command_name in IGNORED_COMMANDS:
                if debug:
                    logger.debug(f"FRAME skip    cmd={command_name}")
                continue

            if debug:
                logger.debug(
                    f"FRAME cmd={command_name}  "
                    f"0x{to_address:02X}←0x{from_address:02X}  "
                    f"body={body_size}B  [{bytes(frame).hex()}]"
                )
            self.decode_and_queue_frame(frame, command_name)

    def decode_and_queue_frame(self, frame, command_name):
        """
        Decode a frame and add it to the queue if valid.

        Broadcast frames carry the channel-record body layout, LatLon frames
        carry ASCII, and Light Intensity frames carry a backlight level byte;
        those are decoded and queued. Every other command (pilot messages,
        NMEA-sourced data, etc.) has an unknown body structure, so it is never
        queued — it is only probed speculatively for debugging.
        """
        if command_name == "Broadcast":
            decoded_frame = decode_frame(frame)
        elif command_name == "LatLon":
            decoded_frame = decode_ascii_frame(frame)
        elif command_name == "Light Intensity":
            decoded_frame = decode_light_frame(frame)
        else:
            probe_frame(frame)
            return

        if not (decoded_frame and "values" in decoded_frame):
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"  QUEUE fail    decode error  [{frame.hex()}]")
            return

        if self.project:
            values = interpreter.project(decoded_frame)
            if not values:
                # every channel dropped / unmapped (e.g. Backlight, protocol) — nothing to emit
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"  QUEUE skip    no mapped paths  cmd={command_name}")
                return
            queued = {
                "to_address":   decoded_frame.get("to_address"),
                "from_address": decoded_frame.get("from_address"),
                "command":      decoded_frame.get("command"),
                "values":       values,
            }
        else:
            queued = decoded_frame

        try:
            self.frame_queue.put_nowait(queued)
            if logger.isEnabledFor(logging.DEBUG):
                keys = list(queued["values"].keys())
                names_str = ", ".join(keys[:4])
                if len(keys) > 4:
                    names_str += f", +{len(keys) - 4} more"
                logger.debug(f"  QUEUE {len(keys)} value(s)  [{names_str}]")
        except Full:
            logger.warning("Frame queue full, dropping frame.")

    def get_buffer_size(self):
        return len(self.buffer)

    def get_buffer_contents(self):
        hex_contents = self.buffer.hex()
        logger.debug(f"BUF   contents  [{hex_contents}]")
        return hex_contents
