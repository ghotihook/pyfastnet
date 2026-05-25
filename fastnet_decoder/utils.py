

def calculate_checksum(data):
    """
    Calculates the checksum for the given data bytes this one is for Fastnet Checksum
    Args:
        data (bytes): The data bytes to calculate checksum for.
    Returns:
        int: The calculated checksum.
    """
    return (-sum(data)) & 0xFF
