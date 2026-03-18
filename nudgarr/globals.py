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

from flask import Flask, Response

from nudgarr.constants import VERSION

# ── Flask app ─────────────────────────────────────────────────────────

app = Flask(__name__, template_folder="templates", static_folder="static", static_url_path="/static")


# ── M1: Persistent secret key ─────────────────────────────────────────
# Load from /config/nudgarr-secret.key if present, otherwise generate
# and persist it so sessions survive container restarts. Falls back to
# a random ephemeral key if the config directory isn't writable.
def _load_or_create_secret_key() -> str:
    env_key = os.getenv("SECRET_KEY")
    if env_key:
        return env_key
    config_dir = os.path.dirname(
        os.getenv("CONFIG_FILE", "/config/nudgarr-config.json")
    )
    key_path = os.path.join(config_dir, "nudgarr-secret.key")
    try:
        if os.path.exists(key_path):
            key = open(key_path).read().strip()
            if len(key) >= 32:
                return key
        key = secrets.token_hex(32)
        os.makedirs(config_dir, exist_ok=True)
        with open(key_path, "w") as f:
            f.write(key)
        return key
    except Exception:
        # Config dir not writable — fall back to ephemeral key.
        # Sessions will be invalidated on container restart.
        return secrets.token_hex(32)


app.secret_key = _load_or_create_secret_key()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_REFRESH_EACH_REQUEST"] = False
# SESSION_COOKIE_SAMESITE intentionally not set.
# SameSite=Lax breaks session cookies in reverse-proxy and iframe
# environments (Unraid, Synology) because POST requests are treated as
# cross-site. HTTPS is not planned for this LAN-only tool.
logging.getLogger("werkzeug").setLevel(logging.ERROR)


# ── L1: Security response headers ─────────────────────────────────────
@app.after_request
def _security_headers(response: Response) -> Response:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ── L2: Release DB connection at end of each request context ──────────
@app.teardown_appcontext
def _close_db_connection(exc: object) -> None:
    from nudgarr import db
    db.close_connection()


# ── L3: JSON error handlers for 400, 404, 500 ─────────────────────────
# Without these Flask returns HTML error pages which break the frontend's
# api() wrapper (expects JSON) and expose framework internals to the user.
@app.errorhandler(400)
def _error_400(e):
    return __import__("flask").jsonify({"error": "Bad request", "detail": str(e)}), 400


@app.errorhandler(404)
def _error_404(e):
    return __import__("flask").jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def _error_500(e):
    logging.getLogger(__name__).exception("Unhandled 500 error")
    return __import__("flask").jsonify({"error": "Internal server error — check logs"}), 500


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
