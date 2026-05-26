import logging
import sys
import threading
from datetime import datetime
from pathlib import Path

_LOG_DIR = Path(__file__).parent.parent.parent / "logs"
_SESSION_FILE: Path | None = None
_root_logger: logging.Logger | None = None
_logger_lock = threading.Lock()


def _setup_root_logger() -> logging.Logger:
    global _root_logger, _SESSION_FILE

    if _root_logger is not None:
        return _root_logger

    with _logger_lock:
        if _root_logger is not None:
            return _root_logger

        _LOG_DIR.mkdir(exist_ok=True)
        _cleanup_old_sessions(keep=10)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        _SESSION_FILE = _LOG_DIR / f"{timestamp}.log"

        logger = logging.getLogger("claudefm")
        logger.setLevel(logging.DEBUG)

        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )

        file_handler = logging.FileHandler(_SESSION_FILE, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(fmt)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        logger.propagate = False

        _root_logger = logger
        return logger


def _cleanup_old_sessions(keep: int) -> None:
    files = sorted(_LOG_DIR.glob("*.log"), key=lambda f: f.stat().st_mtime)
    for old in files[:-keep]:
        old.unlink(missing_ok=True)


def get_logger(name: str) -> logging.Logger:
    _setup_root_logger()
    return logging.getLogger(f"claudefm.{name}")
