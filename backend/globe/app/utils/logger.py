import logging
import sys
from pathlib import Path
from app.config import get_settings

settings = get_settings()


class SafeStreamHandler(logging.StreamHandler):
    """Handles Unicode characters that Windows cp1252 console can't encode."""
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            stream.write(msg + self.terminator)
            self.flush()
        except UnicodeEncodeError:
            # Replace unencodable chars with '?' and retry
            msg = self.format(record).encode(
                sys.stdout.encoding or "ascii", errors="replace"
            ).decode(sys.stdout.encoding or "ascii")
            self.stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


def get_logger(name: str) -> logging.Logger:
    Path(settings.LOG_DIR).mkdir(exist_ok=True)

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Safe console handler - won't crash on Windows emoji/arrows
    ch = SafeStreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File handler with explicit UTF-8
    fh = logging.FileHandler(f"{settings.LOG_DIR}/globe.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
