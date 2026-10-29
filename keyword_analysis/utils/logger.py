"""
Structured logger for the keyword analysis engine.

Provides a configured logger with consistent formatting across all modules.
Uses Python's built-in logging — no extra deps.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional


_CONFIGURED = False


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """
    Get a named logger with the engine's standard format.

    Args:
        name: Logger name (typically __name__ of the calling module).
        level: Override log level. Defaults to INFO.

    Returns:
        Configured Logger instance.
    """
    global _CONFIGURED

    logger = logging.getLogger(name)

    if not _CONFIGURED:
        _configure_root(level or logging.INFO)
        _CONFIGURED = True

    if level is not None:
        logger.setLevel(level)

    return logger


def _configure_root(level: int) -> None:
    """Set up the root keyword_analysis logger once."""
    root = logging.getLogger("keyword_analysis")
    root.setLevel(level)

    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        fmt = logging.Formatter(
            "[%(asctime)s] %(levelname)-7s %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(fmt)
        root.addHandler(handler)

    # Suppress noisy library loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
