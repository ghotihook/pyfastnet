import logging

logger = logging.getLogger("pyfastnet")

DEFAULT_LOG_LEVEL = logging.INFO

if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s [pyfastnet] %(levelname)-5s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

logger.setLevel(DEFAULT_LOG_LEVEL)


def set_log_level(level_name: str):
    """Sets the log level dynamically at runtime."""
    level = logging.getLevelName(level_name.upper())
    if not isinstance(level, int):
        logger.warning(
            f"Unknown log level '{level_name}'; keeping current level."
        )
        return
    logger.setLevel(level)
    logger.info(f"Log level set to {level_name.upper()}.")
