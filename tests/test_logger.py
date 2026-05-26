import logging
from pathlib import Path
from src.utils.logger import get_logger


def test_get_logger_returns_logger():
    log = get_logger("test")
    assert isinstance(log, logging.Logger)


def test_logger_has_correct_name():
    log = get_logger("mymodule")
    assert log.name == "claudefm.mymodule"


def test_logger_does_not_duplicate_handlers():
    log1 = get_logger("dup")
    log2 = get_logger("dup")
    assert log1 is log2
