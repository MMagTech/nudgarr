"""
nudgarr/routes/diagnostics.py

Diagnostic download endpoint.

  GET /api/diagnostic -- download a plain-text diagnostic report
"""

from flask import Blueprint, Response

import os

from nudgarr import db
from nudgarr.auth import requires_auth
from nudgarr.config import load_or_init_config
from nudgarr.constants import CONFIG_FILE, DB_FILE, PORT, VERSION
from nudgarr.globals import STATUS

bp = Blueprint("diagnostics", __name__)


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

    summary_rows = db.get_connection().execute(
        """
        SELECT app, instance_url, COUNT(*) as cnt
        FROM search_history
        GROUP BY app, instance_url
        """
    ).fetchall()

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
    total_history = db.get_connection().execute("SELECT COUNT(*) FROM search_history").fetchone()[0]
    total_stats = db.get_connection().execute("SELECT COUNT(*) FROM stat_entries WHERE imported = 1").fetchone()[0]

    lines = [
        f"Nudgarr v{VERSION}",
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
        "",
        "Last run summary:",
    ] + (summary_lines or ["  No runs yet."]) + [
        "",
        "History entry counts by instance:",
    ] + (instance_counts or ["  No entries."])

    text = "\n".join(lines)
    return Response(
        text,
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=nudgarr-diagnostic.txt"},
    )
