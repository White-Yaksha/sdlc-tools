"""Structured logging setup for SDLC Tools."""

from __future__ import annotations

import logging
import sys

_LOG_FORMAT = "[%(levelname)s] %(message)s"
_LOG_FORMAT_VERBOSE = "[%(levelname)s] %(name)s: %(message)s"

_configured = False


def setup_logging(verbose: bool = False, log_file: str = "") -> None:
    """Configure the root logger for sdlc_tools.

    Call once at CLI startup. Subsequent calls are no-ops.
    """
    global _configured
    if _configured:
        return
    _configured = True

    level = logging.DEBUG if verbose else logging.INFO
    fmt = _LOG_FORMAT_VERBOSE if verbose else _LOG_FORMAT

    root = logging.getLogger("sdlc_tools")
    root.setLevel(level)

    # Console handler.
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(fmt))
    root.addHandler(console)

    # Optional file handler.
    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(fmt))
        root.addHandler(fh)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the sdlc_tools namespace."""
    return logging.getLogger(f"sdlc_tools.{name}")
