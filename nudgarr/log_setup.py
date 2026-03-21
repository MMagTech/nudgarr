"""
nudgarr/log_setup.py

Logging initialisation and runtime level control.

  setup_logging   -- configure the nudgarr root logger with stdout + rotating file handlers
  apply_log_level -- update the log level on the running nudgarr logger without restart

Called from main.py at startup. apply_log_level is called from routes/config.py
when the user saves a new log_level value in Advanced Settings.

The nudgarr logger is the package root — all child loggers (nudgarr.sweep,
nudgarr.arr_clients, etc.) propagate to it and share its handlers and level.
Werkzeug noise suppression lives in globals.py and is unaffected by this module.

Imports from within the package: constants only.
"""

import logging
import os
import time
from logging.handlers import RotatingFileHandler

from nudgarr.constants import DB_FILE

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Derived from DB_FILE so the log directory is always alongside the database.
LOG_DIR = os.path.join(os.path.dirname(DB_FILE) or "/config", "logs")
LOG_FILE = os.path.join(LOG_DIR, "nudgarr.log")

VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def setup_logging(log_level_str: str = "INFO") -> None:
    """Configure the nudgarr root logger with stdout and rotating file handlers.

    Creates LOG_DIR (/config/logs/) if it does not exist. Both handlers share
    the same formatter. The rotating file handler caps at 5 MB per file with
    3 backups (20 MB total). Call once at startup before other nudgarr imports log.

    Calling this more than once is safe — guard prevents duplicate handler
    registration on repeat calls.
    """
    level = getattr(logging, log_level_str.upper(), logging.INFO)

    os.makedirs(LOG_DIR, exist_ok=True)

    fmt = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)
    fmt.converter = time.localtime

    root = logging.getLogger("nudgarr")

    # Guard against duplicate handlers if called more than once.
    if root.handlers:
        root.setLevel(level)
        return

    root.setLevel(level)
    root.propagate = False

    # stdout handler — feeds Docker log driver and Unraid log viewer
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)

    # Rotating file handler — 5 MB per file, 3 backups (20 MB total cap)
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)


def apply_log_level(log_level_str: str) -> None:
    """Update the log level on the running nudgarr logger without restart.

    Called from routes/config.py after the user saves a new log_level value.
    Invalid level strings fall back to INFO.
    """
    level = getattr(logging, (log_level_str or "INFO").upper(), logging.INFO)
    logging.getLogger("nudgarr").setLevel(level)
