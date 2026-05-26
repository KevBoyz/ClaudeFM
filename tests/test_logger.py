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
    get_logger("dup")
    get_logger("dup")
    get_logger("other")
    root = logging.getLogger("claudefm")
    assert root.handlers  # at least one handler exists
    handler_count = len(root.handlers)
    get_logger("another")
    assert len(root.handlers) == handler_count  # no new handlers added
