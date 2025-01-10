import logging

# Create a logger
logger = logging.getLogger("fastnet_decoder")

# Default log level
DEFAULT_LOG_LEVEL = logging.INFO

# Avoid duplicate handlers
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

logger.setLevel(DEFAULT_LOG_LEVEL)

def set_log_level(level_name: str):
    """
    Sets the log level dynamically at runtime.
    Args:
        level_name (str): Name of the log level (e.g., "DEBUG", "INFO", "WARNING").
    """
    level = getattr(logging, level_name.upper(), DEFAULT_LOG_LEVEL)
    logger.setLevel(level)
    logger.info(f"Log level set to {level_name.upper()}.")