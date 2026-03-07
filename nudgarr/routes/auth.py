"""
nudgarr/routes/auth.py

Page renders and authentication endpoints.

  GET  /           -- main UI (requires auth)
  GET  /login      -- login page
  GET  /setup      -- first-run setup page
  POST /api/setup  -- create initial credentials
  POST /api/auth/login  -- authenticate
  POST /api/auth/logout -- clear session
"""

from datetime import datetime

from flask import Blueprint, jsonify, redirect, render_template, request, session

from nudgarr.auth import (
    check_auth_lockout,
    clear_auth_failures,
    hash_password,
    is_authenticated,
    is_setup_needed,
    record_auth_failure,
    requires_auth,
    verify_password,
)
from nudgarr.config import load_or_init_config
from nudgarr.constants import CONFIG_FILE
from nudgarr.utils import save_json_atomic

bp = Blueprint("auth", __name__)


@bp.get("/")
@requires_auth
def index():
    return render_template("ui.html")


@bp.get("/login")
def login_page():
    if is_authenticated():
        return redirect("/")
    return render_template("login.html")


@bp.get("/setup")
def setup_page():
    if not is_setup_needed():
        return redirect("/")
    return render_template("setup.html")


@bp.post("/api/setup")
def api_setup():
    if not is_setup_needed():
        return jsonify({"ok": False, "error": "Setup already complete"}), 400
    data = request.get_json(force=True, silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if not username:
        return jsonify({"ok": False, "error": "Username is required"}), 400
    if len(password) < 6:
        return jsonify({"ok": False, "error": "Password must be at least 6 characters"}), 400
    cfg = load_or_init_config()
    cfg["auth_username"] = username
    cfg["auth_password_hash"] = hash_password(password)  # salted PBKDF2
    cfg["auth_enabled"] = True
    save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    session["authenticated"] = True
    session["last_active"] = datetime.now().timestamp()
    return jsonify({"ok": True})


@bp.post("/api/auth/login")
def api_login():
    ip = request.remote_addr or "unknown"
    locked, remaining = check_auth_lockout(ip)
    if locked:
        return jsonify({"ok": False, "error": f"Too many failed attempts. Try again in {remaining}s."}), 429
    data = request.get_json(force=True, silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    cfg = load_or_init_config()
    stored_hash = cfg.get("auth_password_hash", "")
    valid = verify_password(password, stored_hash) and username == cfg.get("auth_username", "")
    if not valid:
        duration = record_auth_failure(ip)
        msg = "Invalid credentials"
        if duration:
            msg = f"Too many failed attempts. Try again in {duration}s."
        return jsonify({"ok": False, "error": msg}), 401
    # Auto-migrate legacy sha256 hash to salted PBKDF2 on successful login
    if ":" not in stored_hash:
        cfg["auth_password_hash"] = hash_password(password)
        save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    clear_auth_failures(ip)
    session["authenticated"] = True
    session["last_active"] = datetime.now().timestamp()
    return jsonify({"ok": True})


@bp.post("/api/auth/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})
