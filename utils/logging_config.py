"""
Structured logging configuration for the medical retrieval pipeline.

Usage:
    from utils.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("message")

Writes to:
    console   — INFO and above
    logs/app.log — DEBUG and above (created automatically)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_LOG_DIR  = Path(__file__).parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "app.log"

_FMT      = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

# Root handler guard — prevent duplicate handlers if module is re-imported
_configured: set[str] = set()


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger with:
      - StreamHandler  → stdout, level INFO
      - FileHandler    → logs/app.log, level DEBUG

    Calling get_logger with the same name twice returns the same logger
    without duplicating handlers.
    """
    logger = logging.getLogger(name)

    if name in _configured:
        return logger

    _configured.add(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False   # don't bubble up to root logger

    formatter = logging.Formatter(_FMT, datefmt=_DATE_FMT)

    # ── Console handler (INFO+) ────────────────────────────────────────────────
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # ── File handler (DEBUG+) ─────────────────────────────────────────────────
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger
