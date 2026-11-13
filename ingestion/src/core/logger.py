"""
Loguru-based logger with a clean, color-coded console format.
Import `logger` from this module everywhere instead of using `print`.
"""

import sys
from loguru import logger

logger.remove()  # remove default handler

logger.add(
    sys.stdout,
    colorize=True,
    format=(
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
        "<level>{message}</level>"
    ),
    level="DEBUG",
)

__all__ = ["logger"]
