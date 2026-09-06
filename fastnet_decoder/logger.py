import logging

logger = logging.getLogger("pyfastnet")

DEFAULT_LOG_LEVEL = logging.INFO

if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s [pyfastnet] %(levelname)-5s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

logger.setLevel(DEFAULT_LOG_LEVEL)


def set_log_level(level_name):
    """Set the log level at runtime.

    Accepts either a name ("DEBUG", "info") or one of the logging module's
    own constants (logging.DEBUG). Both spellings appear in the wild — the
    README documents the constant form — so both are supported.

    Example:
        set_log_level("DEBUG")          # by name
        set_log_level(logging.DEBUG)    # by logging constant
    """
    if isinstance(level_name, int):
        level = level_name
        display = logging.getLevelName(level)
    else:
        display = str(level_name).upper()
        level = logging.getLevelName(display)

    if not isinstance(level, int):
        logger.warning(
            f"Unknown log level '{level_name}'; keeping current level."
        )
        return
    logger.setLevel(level)
    logger.info(f"Log level set to {display}.")
