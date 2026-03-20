"""
nudgarr/routes/diagnostics.py

Diagnostic download endpoint.

  GET /api/diagnostic -- download a plain-text diagnostic report
"""

import logging
import os
import re

from flask import Blueprint, Response, jsonify

from nudgarr import db
from nudgarr.auth import requires_auth
from nudgarr.config import load_or_init_config
from nudgarr.constants import CONFIG_FILE, DB_FILE, PORT, VERSION
from nudgarr.globals import STATUS
from nudgarr.log_setup import LOG_FILE
from nudgarr.utils import mask_url

logger = logging.getLogger(__name__)

bp = Blueprint("diagnostics", __name__)

# Pattern that identifies a URL in a log line for masking
_URL_RE = re.compile(r'https?://\S+')


def _mask_log_line(line: str) -> str:
    """Apply mask_url() to every URL found in a log line."""
    return _URL_RE.sub(lambda m: mask_url(m.group(0)), line)


def _read_log_tail(n: int = 250) -> list:
    """Return the last n lines of nudgarr.log with URLs masked.
    Returns an empty list if the file does not exist or cannot be read."""
    try:
        with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        tail = lines[-n:] if len(lines) > n else lines
        return [_mask_log_line(ln.rstrip("\n")) for ln in tail]
    except OSError:
        return []


@bp.get("/api/diagnostic")
@requires_auth
def api_diagnostic():
    cfg = load_or_init_config()
    radarr_instances = cfg.get("instances", {}).get("radarr", [])
    sonarr_instances = cfg.get("instances", {}).get("sonarr", [])
    radarr_names = [i.get("name") for i in radarr_instances]
    sonarr_names = [i.get("name") for i in sonarr_instances]

    # Per-instance entry counts from DB
    valid_urls = {}
    for inst in radarr_instances:
        valid_urls[("radarr", inst["url"].rstrip("/"))] = inst["name"]
    for inst in sonarr_instances:
        valid_urls[("sonarr", inst["url"].rstrip("/"))] = inst["name"]

    summary_rows = db.get_search_history_counts()

    instance_counts = []
    for r in summary_rows:
        url = r["instance_url"].rstrip("/")
        key_tuple = (r["app"], url)
        if key_tuple in valid_urls:
            friendly = valid_urls[key_tuple]
            instance_counts.append(f"  {r['app']}/{friendly}: {r['cnt']} entries")
        else:
            instance_counts.append(
                f"  {r['app']}/{url}: {r['cnt']} entries (orphaned — no matching instance)"
            )

    # Last run summary
    last_summary = STATUS.get("last_summary") or {}
    summary_lines = []
    for app_name in ("radarr", "sonarr"):
        for s in last_summary.get(app_name, []):
            if "error" in s:
                summary_lines.append(f"  {s.get('name', '?')}: ERROR — {s.get('error')}")
            else:
                cutoff = s.get("searched", 0)
                backlog = s.get("searched_missing", 0)
                skipped = s.get("skipped_cooldown", 0)
                summary_lines.append(
                    f"  {s.get('name', '?')}: searched={cutoff + backlog} "
                    f"(cutoff={cutoff} backlog={backlog}) skipped_cooldown={skipped}"
                )

    # DB file size
    try:
        db_size_bytes = os.path.getsize(DB_FILE)
        db_size = f"{db_size_bytes / 1024:.1f} KB" if db_size_bytes < 1024 * 1024 else f"{db_size_bytes / 1024 / 1024:.2f} MB"
    except OSError:
        db_size = "unavailable"

    # Total history entry count
    total_history = db.count_search_history()
    total_stats = db.count_confirmed_entries()

    lines = [
        f"Nudgarr v{VERSION}",
        f"Log level: {cfg.get('log_level', 'INFO')}",
        f"Port: {PORT}",
        f"Last run: {STATUS.get('last_run_utc') or 'Never'}",
        f"Next run: {STATUS.get('next_run_utc') or 'N/A'}",
        f"Last error: {STATUS.get('last_error') or 'None'}",
        f"Scheduler: {'enabled' if cfg.get('scheduler_enabled') else 'manual'}, cron: {cfg.get('cron_expression', 'not set')}",
        f"Cooldown: {cfg.get('cooldown_hours')}h",
        f"Session timeout: {cfg.get('auth_session_minutes')}min | Auth: {'enabled' if cfg.get('auth_enabled') else 'disabled'}",
        f"Import check interval: {cfg.get('import_check_minutes')}min",
        f"Radarr instances ({len(radarr_names)}): {', '.join(radarr_names) or 'none'}",
        f"Sonarr instances ({len(sonarr_names)}): {', '.join(sonarr_names) or 'none'}",
        f"Radarr cap: {cfg.get('radarr_max_movies_per_run')}/run | Backlog cap: {cfg.get('radarr_missing_max', 0)}/run",
        f"Sonarr cap: {cfg.get('sonarr_max_episodes_per_run')}/run | Backlog cap: {cfg.get('sonarr_missing_max', 0)}/run",
        f"Database: {DB_FILE} ({db_size})",
        f"Config file: {CONFIG_FILE}",
        f"History entries: {total_history} total | Confirmed imports: {total_stats}",
        f"Per-instance overrides: {'enabled' if cfg.get('per_instance_overrides_enabled') else 'disabled'}",
    ]

    # Per-instance override detail — only shown when feature is enabled and overrides exist
    if cfg.get("per_instance_overrides_enabled"):
        override_lines = []
        for app_name in ("radarr", "sonarr"):
            for inst in cfg.get("instances", {}).get(app_name, []):
                ov = inst.get("overrides", {})
                if ov:
                    fields = ", ".join(f"{k}={v}" for k, v in ov.items())
                    override_lines.append(f"  {app_name}/{inst.get('name', '?')}: {fields}")
        if override_lines:
            lines.append("")
            lines.append("Active per-instance overrides:")
            lines.extend(override_lines)
        else:
            lines.append("  (no overrides applied)")

    lines += [
        "",
        "Last run summary:",
    ] + (summary_lines or ["  No runs yet."]) + [
        "",
        "History entry counts by instance:",
    ] + (instance_counts or ["  No entries."])

    # Log tail — last 250 lines from nudgarr.log with URLs masked.
    # Log output may contain local hostnames and media titles.
    log_tail = _read_log_tail(250)
    lines += [
        "",
        f"--- Recent log (last {len(log_tail)} lines from nudgarr.log) ---",
        "# URLs masked. May contain hostnames and media titles.",
    ] + (log_tail if log_tail else ["  (log file not found or empty)"])

    text = "\n".join(lines)
    return Response(
        text,
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=nudgarr-diagnostic.txt"},
    )


@bp.post("/api/log/clear")
@requires_auth
def api_log_clear():
    """Truncate the active nudgarr.log to zero bytes.
    Rotation backups (.1 .2 .3) are not affected.
    The rotating file handler resumes writing immediately on the next log event.
    """
    try:
        open(LOG_FILE, "w").close()
        logger.info("Log cleared by user via UI")
        return jsonify({"ok": True})
    except OSError as e:
        logger.warning("Log clear failed: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500
