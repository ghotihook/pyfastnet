"""A record whose format has no known layout must not break the stream.

decode_frame() records such a channel as None. project() used to call .get() on
that None and raise AttributeError - out of FrameBuffer.get_complete_frames(),
killing the caller's read loop. No captured frame contains one (format 0x00 has a
known size but no known layout), so a synthetic frame exercises it.
"""
from fastnet_decoder import FrameBuffer, decode_frame, project
from fastnet_decoder.utils import calculate_checksum


def _frame(body, command=0x01, to_address=0xFF, from_address=0x01):
    header = bytes([to_address, from_address, len(body), command])
    return header + bytes([calculate_checksum(header)]) + body + bytes([calculate_checksum(body)])


# Boatspeed (Knots) in format 0x00 (4 data bytes, layout unknown), followed by a
# real Battery Volts record (format 0x81: signed 16-bit, divisor 100 -> 13.18 V).
FRAME = _frame(bytes([0x41, 0x00, 0x01, 0x02, 0x03, 0x04, 0x8D, 0x81, 0x05, 0x26]))


def test_rich_decode_marks_the_record_undecodable():
    values = decode_frame(FRAME)["values"]
    assert values["Boatspeed (Knots)"] is None
    assert values["Battery Volts"]["value"] == 13.18


def test_project_skips_the_undecodable_record():
    assert project(decode_frame(FRAME)) == {"electrical.batteries.house.voltage": 13.18}


def test_frame_buffer_keeps_running():
    fb = FrameBuffer()
    fb.add_to_buffer(FRAME)
    fb.get_complete_frames()
    queued = fb.frame_queue.get_nowait()
    assert queued["values"] == {"electrical.batteries.house.voltage": 13.18}
