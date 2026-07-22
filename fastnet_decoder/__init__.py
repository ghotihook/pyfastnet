__version__ = "3.1.0"

from .frame_buffer import FrameBuffer
from .decode_fastnet import decode_frame, decode_ascii_frame, decode_light_frame
from .signalk_map import project, unit_for, channel_map  # projection + units + master map
from .logger import logger, set_log_level  # Import set_log_level for user control

__all__ = ["FrameBuffer", "decode_frame", "decode_ascii_frame", "decode_light_frame",
           "project", "unit_for", "channel_map", "logger", "set_log_level"]