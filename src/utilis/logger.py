"""
Logger configuration for PersonFinderTool.
Writes structured logs to logs/app.log.
"""

import logging
import os
import sys


def setup_logger(name: str = "person_finder", level: int = logging.INFO) -> logging.Logger:
    """Set up and return a configured logger instance.

    Args:
        name: Logger name identifier.
        level: Logging level (default: INFO).

    Returns:
        Configured logging.Logger instance.
    """
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "logs")
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        # File handler — detailed logs
        file_handler = logging.FileHandler(
            os.path.join(log_dir, "app.log"), encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Console handler — concise logs
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.WARNING)
        console_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger


logger = setup_logger()