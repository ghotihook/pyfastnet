

def calculate_checksum(data):
    """
    Calculates the checksum for the given data bytes.
    Args:
        data (bytes): The data bytes to calculate checksum for.
    Returns:
        int: The calculated checksum.
    """
    return (0x100 - sum(data) % 0x100) & 0xFF


def calculate_nmea_checksum(sentence):
    """
    Calculates the NMEA checksum for a given sentence (excluding '$' and '*').
    Args:
        sentence (str): NMEA sentence string without '$' and checksum '*'.
    Returns:
        str: Hexadecimal checksum as a string.
    """
    checksum = 0
    for char in sentence:
        checksum ^= ord(char)
    return f"{checksum:02X}"


def convert_segment_b_to_char(segment_byte):
    """
    Converts a 7-segment display byte into a human-readable character.
    Args:
        segment_byte (int): The byte representing the 7-segment display.
    Returns:
        str: The corresponding character or '?' if unknown.
    """
    segment_mapping = {
        0xBE: "O",
        0xE8: "F",
        0x62: "n",
        0x72: "o",
        0x40: "-",
        0x00: " ",  # Blank
    }
    return segment_mapping.get(segment_byte, "?")


def parse_format_byte(format_byte):
    """
    Parses the format byte into divisor, digits, and format type.
    Args:
        format_byte (int): The format byte.
    Returns:
        dict: Parsed divisor, digits, and format type.
    """
    divisor_bits = (format_byte >> 6) & 0b11  # First two bits
    digits_bits = (format_byte >> 4) & 0b11   # Next two bits
    format_type = format_byte & 0x0F          # Last 4 bits (format type)

    divisor_map = {0b00: 1, 0b01: 10, 0b10: 100, 0b11: 1000}
    digits_map = {0b00: 1, 0b01: 2, 0b10: 3, 0b11: 4}

    return {
        "divisor": divisor_map.get(divisor_bits, 1),
        "digits": digits_map.get(digits_bits, 1),
        "format_type": format_type,
    }