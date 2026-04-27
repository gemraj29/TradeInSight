"""Structured logging configuration for TradeInSight."""

import logging
import sys
from app.core.config import settings


def setup_logging() -> None:
    """Configure root logger with a clean, structured format.

    Call once at application startup (Home.py).
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt=date_fmt))

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger.

    Args:
        name: Typically __name__ of the calling module.

    Returns:
        A configured logging.Logger instance.
    """
    return logging.getLogger(name)
