"""
nudgarr/routes/diagnostics.py

Diagnostic download endpoint.

  GET /api/diagnostic -- download a plain-text diagnostic report
"""

from flask import Blueprint, Response

from nudgarr.auth import requires_auth
from nudgarr.config import load_or_init_config
from nudgarr.constants import CONFIG_FILE, PORT, STATE_FILE, STATS_FILE, VERSION
from nudgarr.globals import STATUS
from nudgarr.state import load_state, state_key

bp = Blueprint("diagnostics", __name__)


@bp.get("/api/diagnostic")
@requires_auth
def api_diagnostic():
    cfg = load_or_init_config()
    radarr_instances = cfg.get("instances", {}).get("radarr", [])
    sonarr_instances = cfg.get("instances", {}).get("sonarr", [])
    radarr_names = [i.get("name") for i in radarr_instances]
    sonarr_names = [i.get("name") for i in sonarr_instances]

    # Build valid key → friendly name map
    name_map = {}
    valid_keys = set()
    for inst in radarr_instances:
        sk = state_key(inst["name"], inst["url"])
        name_map[("radarr", sk)] = inst["name"]
        valid_keys.add(("radarr", sk))
    for inst in sonarr_instances:
        sk = state_key(inst["name"], inst["url"])
        name_map[("sonarr", sk)] = inst["name"]
        valid_keys.add(("sonarr", sk))

    # Per-instance state counts with orphan detection
    st = load_state()
    instance_counts = []
    for app_name in ("radarr", "sonarr"):
        app_obj = st.get(app_name, {})
        if isinstance(app_obj, dict):
            for sk, bucket in app_obj.items():
                count = len(bucket) if isinstance(bucket, dict) else 0
                key_tuple = (app_name, sk)
                if key_tuple in valid_keys:
                    friendly = name_map[key_tuple]
                    instance_counts.append(f"  {app_name}/{friendly}: {count} entries")
                else:
                    instance_counts.append(
                        f"  {app_name}/{sk}: {count} entries (orphaned — no matching instance)"
                    )

    # Last run summary with cutoff/backlog breakdown
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

    lines = [
        f"Nudgarr v{VERSION}",
        f"Port: {PORT}",
        f"Last run: {STATUS.get('last_run_utc') or 'Never'}",
        f"Next run: {STATUS.get('next_run_utc') or 'N/A'}",
        f"Last error: {STATUS.get('last_error') or 'None'}",
        f"Scheduler: {'enabled' if cfg.get('scheduler_enabled') else 'manual'}, interval: {cfg.get('run_interval_minutes')}min",
        f"Cooldown: {cfg.get('cooldown_hours')}h",
        f"Radarr instances ({len(radarr_names)}): {', '.join(radarr_names) or 'none'}",
        f"Sonarr instances ({len(sonarr_names)}): {', '.join(sonarr_names) or 'none'}",
        f"Radarr cap: {cfg.get('radarr_max_movies_per_run')}/run | Backlog cap: {cfg.get('radarr_missing_max', 0)}/run",
        f"Sonarr cap: {cfg.get('sonarr_max_episodes_per_run')}/run | Backlog cap: {cfg.get('sonarr_missing_max', 0)}/run",
        f"History file: {STATE_FILE}",
        f"Config file: {CONFIG_FILE}",
        f"Stats file: {STATS_FILE}",
        "",
        "Last run summary:",
    ] + (summary_lines or ["  No runs yet."]) + [
        "",
        "History entry counts:",
    ] + (instance_counts or ["  No entries."])

    text = "\n".join(lines)
    return Response(
        text,
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=nudgarr-diagnostic.txt"},
    )
