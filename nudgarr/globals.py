"""
nudgarr/globals.py

Shared mutable objects that cross module boundaries at runtime.

  app      -- Flask application instance
  STATUS   -- runtime status dict, written by scheduler, read by routes
  RUN_LOCK -- mutex for run-now requests between routes and scheduler

IMPORTANT: This module imports only from constants and stdlib.
Nothing else in the package should be imported here — that is the rule
that prevents circular imports. If you find yourself wanting to import
from config, state, or any other nudgarr module here, don't.
"""

import logging
import os
import secrets
import threading
from typing import Any, Dict

from flask import Flask

from nudgarr.constants import VERSION

# ── Flask app ─────────────────────────────────────────────────────────

app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
# Note: secret_key is regenerated on restart if not set via env var.
# Sessions will be invalidated on container restart — expected behaviour for local tool.
app.config["SESSION_COOKIE_HTTPONLY"] = True
# SESSION_COOKIE_SAMESITE intentionally not set.
# SameSite=Lax breaks session cookies in reverse-proxy and iframe
# environments (Unraid, Synology) because POST requests are treated as
# cross-site. This can be revisited when HTTPS support is added, at
# which point SameSite=None; Secure becomes viable.
logging.getLogger("werkzeug").setLevel(logging.ERROR)

# ── Runtime status ────────────────────────────────────────────────────

STATUS: Dict[str, Any] = {
    "version": VERSION,
    "last_run_utc": None,
    "next_run_utc": None,
    "last_summary": None,
    "scheduler_running": False,
    "run_in_progress": False,
    "run_requested": False,
    "last_error": None,
    "instance_health": {},  # {"radarr|name": "ok"|"bad"|"disabled", ...}
}

# ── Sweep lock ────────────────────────────────────────────────────────

RUN_LOCK = threading.Lock()
