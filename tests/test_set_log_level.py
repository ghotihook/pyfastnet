"""set_log_level() must accept both spellings that appear in the wild.

The README documents `set_log_level(logging.DEBUG)`; fastnet2ip passes a
string from its --log-level argument. Both have to work.
"""

import logging

import pytest

from fastnet_decoder import logger, set_log_level


@pytest.fixture(autouse=True)
def restore_level():
    original = logger.level
    yield
    logger.setLevel(original)


@pytest.mark.parametrize("value,expected", [
    ("DEBUG", logging.DEBUG),
    ("debug", logging.DEBUG),
    ("Warning", logging.WARNING),
    ("CRITICAL", logging.CRITICAL),
    (logging.DEBUG, logging.DEBUG),
    (logging.ERROR, logging.ERROR),
])
def test_accepts_names_and_constants(value, expected):
    set_log_level(value)
    assert logger.level == expected


def test_unknown_name_keeps_current_level():
    set_log_level("WARNING")
    set_log_level("NOT_A_LEVEL")
    assert logger.level == logging.WARNING
