"""
nudgarr/auth.py

Authentication, session management, and brute-force lockout.

  Hashing  : hash_password, verify_password
  Lockout  : _AUTH_FAILURES, _AUTH_LOCK, LOCKOUT_SCHEDULE,
             get_lockout_seconds, check_auth_lockout,
             record_auth_failure, clear_auth_failures
  Session  : SESSION_TIMEOUT_MINUTES, auth_required,
             is_setup_needed, is_authenticated
  Decorator: requires_auth

Password hashing uses PBKDF2-HMAC-SHA256 with 260,000 iterations and a
random salt. verify_password also accepts the legacy plain SHA-256 format
and will auto-migrate on the next successful login.

Lockout schedule (failures → lockout duration):
  3  → 30 seconds
  6  → 5 minutes
  10 → 30 minutes
  15 → 1 hour

Imports from within the package: config only.
Flask imports: jsonify, redirect, request, session (no app object needed).
"""

import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime
from functools import wraps
from typing import Any, Dict

from flask import jsonify, redirect, request, session

from nudgarr.config import load_or_init_config

import logging

logger = logging.getLogger(__name__)


# ── Session ───────────────────────────────────────────────────────────

SESSION_TIMEOUT_MINUTES = 30  # default, overridden by config


# ── Password hashing ──────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with a random salt. Returns 'salt:hash'."""
    salt = secrets.token_hex(32)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260000).hex()
    return f"{salt}:{h}"


def verify_password(password: str, stored: str) -> bool:
    """Verify password against stored 'salt:hash' or legacy plain sha256 hash."""
    if ":" in stored:
        salt, h = stored.split(":", 1)
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260000).hex()
        return hmac.compare_digest(expected, h)
    # Legacy sha256 — auto-migrate on next successful login
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)


# ── Progressive brute force lockout ───────────────────────────────────

_AUTH_FAILURES: Dict[str, Any] = {}  # ip -> {"count": int, "locked_until": float}
_AUTH_LOCK = threading.Lock()

LOCKOUT_SCHEDULE = [
    (3, 30),        # 3 failures  → 30 seconds
    (6, 300),       # 6 failures  → 5 minutes
    (10, 1800),     # 10 failures → 30 minutes
    (15, 3600),     # 15+ failures → 1 hour
]


def get_lockout_seconds(count: int) -> int:
    """Return the lockout duration in seconds for the given failure count.
    Iterates LOCKOUT_SCHEDULE and takes the highest matching threshold
    (accumulates, not first-match), so the duration escalates with repeated failures.
    Returns 0 if no threshold has been reached yet."""
    duration = 0
    for threshold, seconds in LOCKOUT_SCHEDULE:
        if count >= threshold:
            duration = seconds
    return duration


def check_auth_lockout(ip: str) -> tuple:
    """Returns (is_locked, seconds_remaining)."""
    with _AUTH_LOCK:
        record = _AUTH_FAILURES.get(ip)
        if not record:
            return False, 0
        if record["locked_until"] and time.time() < record["locked_until"]:
            return True, int(record["locked_until"] - time.time())
        return False, 0


def record_auth_failure(ip: str) -> int:
    """Record a failed attempt. Returns lockout duration in seconds (0 if none)."""
    with _AUTH_LOCK:
        record = _AUTH_FAILURES.get(ip, {"count": 0, "locked_until": 0.0})
        # Reset if previous lockout has expired
        if record["locked_until"] and time.time() >= record["locked_until"]:
            record = {"count": 0, "locked_until": 0.0}
        record["count"] += 1
        duration = get_lockout_seconds(record["count"])
        record["locked_until"] = time.time() + duration if duration else 0.0
        _AUTH_FAILURES[ip] = record
        return duration


def clear_auth_failures(ip: str) -> None:
    """Reset the failure count and lockout timer for the given IP. Called on successful login."""
    with _AUTH_LOCK:
        _AUTH_FAILURES.pop(ip, None)


# ── Session checks ────────────────────────────────────────────────────

def auth_required() -> bool:
    """Returns True if auth is enabled and credentials are configured."""
    cfg = load_or_init_config()
    return bool(cfg.get("auth_enabled", True)) and bool(cfg.get("auth_password_hash", ""))


def is_setup_needed() -> bool:
    """Returns True if auth is enabled but no credentials have been set up yet."""
    cfg = load_or_init_config()
    return bool(cfg.get("auth_enabled", True)) and not bool(cfg.get("auth_password_hash", ""))


def is_authenticated() -> bool:
    """Check if current session is valid and not timed out."""
    if not auth_required():
        return True
    last_active = session.get("last_active")
    if not last_active:
        return False
    cfg = load_or_init_config()
    timeout = int(cfg.get("auth_session_minutes", SESSION_TIMEOUT_MINUTES))
    elapsed = (datetime.now().timestamp() - last_active) / 60
    if elapsed > timeout:
        session.clear()
        return False
    return True


# ── Decorator ─────────────────────────────────────────────────────────

def _csrf_origin_ok() -> bool:
    """
    Basic CSRF mitigation for POST requests — verify Origin or Referer
    header originates from the same host that served the page.
    Allows requests with no origin header (curl, direct API calls from
    the same machine) and same-host browser requests.
    Returns True if the request appears legitimate, False if it looks
    like a cross-origin POST from a third-party page.
    """
    if request.method != "POST":
        return True
    origin = request.headers.get("Origin", "")
    referer = request.headers.get("Referer", "")
    check = origin or referer
    if not check:
        # No origin headers — CLI / curl / same-machine request, allow.
        return True
    host = request.host  # e.g. "192.168.1.10:8085"
    from urllib.parse import urlparse
    parsed_host = urlparse(check).netloc
    return parsed_host == host


def requires_auth(f):
    """Decorator for routes that need authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if is_setup_needed():
            if request.path != "/setup" and not request.path.startswith("/api/setup"):
                return redirect("/setup")
        elif auth_required() and not is_authenticated():
            if request.path != "/login" and not request.path.startswith("/api/auth"):
                if request.path.startswith("/api/"):
                    return jsonify({"ok": False, "error": "Unauthorized"}), 401
                return redirect("/login")
        # H3: CSRF origin check on authenticated POST routes
        if not _csrf_origin_ok():
            return jsonify({"ok": False, "error": "Forbidden"}), 403
        return f(*args, **kwargs)
    return decorated
