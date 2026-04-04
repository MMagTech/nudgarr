"""
nudgarr/routes/intel.py

Intel tab -- read-only lifetime performance dashboard route.

  GET  /api/intel       -- return full Intel payload assembled from aggregate
                          and live tables
  POST /api/intel/reset -- clear intel_aggregate and exclusion_events (Danger Zone)

All aggregate writes happen at confirm time in db/entries.py. This route
only reads and resets. Live queries (pipeline search counts, CF Score health,
exclusion cycles) run directly against their source tables on each request.
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify

from nudgarr import db
from nudgarr.auth import requires_auth
from nudgarr.config import load_or_init_config

logger = logging.getLogger(__name__)

bp = Blueprint("intel", __name__)

# Cold start minimum thresholds.
_COLD_START_MIN_IMPORTS = 25
_COLD_START_MIN_RUNS = 50


# ── GET /api/intel ────────────────────────────────────────────────────

@bp.get("/api/intel")
@requires_auth
def api_intel():
    """Assemble and return the full Intel dashboard payload.

    Reads intel_aggregate for protected lifetime metrics, then runs live
    queries for current-state metrics (pipeline search counts, CF Score
    health, exclusion cycles). All computation happens in Python; the
    frontend receives a single flat JSON object.
    """
    logger.debug("[Intel] GET /api/intel called")
    try:
        return _build_intel_payload()
    except Exception:
        logger.exception("[Intel] GET /api/intel failed")
        return {"error": "Intel data unavailable -- check logs for details."}, 500


def _build_intel_payload():
    """Assemble the full Intel payload."""
    cfg = load_or_init_config()
    conn = db.get_connection()

    # ── 1. Aggregate read ─────────────────────────────────────────────
    logger.debug("[Intel] reading intel_aggregate")
    agg = db.get_intel_aggregate()

    # ── 2. Cold start check ───────────────────────────────────────────
    sweep_rows = conn.execute("SELECT SUM(runs) as total_runs FROM sweep_lifetime").fetchone()
    total_runs = (sweep_rows["total_runs"] or 0) if sweep_rows else 0
    cold_start = (
        agg["success_total_imported"] < _COLD_START_MIN_IMPORTS
        and total_runs < _COLD_START_MIN_RUNS
    )
    logger.debug("[Intel] cold_start=%s total_runs=%d imported=%d",
                 cold_start, total_runs, agg["success_total_imported"])

    # ── 3. Import Summary ─────────────────────────────────────────────
    turnaround_avg = 0.0
    if agg["turnaround_count"] > 0:
        turnaround_avg = round(agg["turnaround_sum_days"] / agg["turnaround_count"], 2)

    searches_per_import_avg = 0.0
    if agg["searches_per_import_count"] > 0:
        searches_per_import_avg = round(
            agg["searches_per_import_sum"] / agg["searches_per_import_count"], 2
        )

    # Live pipeline search counts from search_history.sweep_type
    logger.debug("[Intel] fetching pipeline search counts")
    pipeline_searches = db.get_pipeline_search_counts()

    cutoff_imports = agg["cutoff_import_count"]
    backlog_imports = agg["backlog_import_count"]
    cf_imports = agg["cf_score_import_count"]
    total_imports = cutoff_imports + backlog_imports + cf_imports

    # Pipeline enabled state from config for disabled pill in UI
    cutoff_enabled = (
        cfg.get("radarr_cutoff_enabled", True) or cfg.get("sonarr_cutoff_enabled", True)
    )
    backlog_enabled = False
    for app_name in ("radarr", "sonarr"):
        for inst in cfg.get("instances", {}).get(app_name, []):
            if inst.get("enabled", True):
                ov_on = cfg.get("per_instance_overrides_enabled", False)
                ov = inst.get("overrides", {}) if ov_on else {}
                if ov.get("backlog_enabled",
                          cfg.get(f"{app_name}_backlog_enabled", False)):
                    backlog_enabled = True
    cf_enabled = cfg.get("cf_score_enabled", False)

    import_summary = {
        "turnaround_avg_days": turnaround_avg,
        "searches_per_import_avg": searches_per_import_avg,
        "quality_upgrades_count": agg["quality_upgrades_count"],
        "total_imports": total_imports,
        "cutoff_import_count": cutoff_imports,
        "backlog_import_count": backlog_imports,
        "cf_score_import_count": cf_imports,
        "cutoff_search_count": pipeline_searches["cutoff_unmet"],
        "backlog_search_count": pipeline_searches["backlog"],
        "cf_score_search_count": pipeline_searches["cf_score"],
        "cutoff_enabled": cutoff_enabled,
        "backlog_enabled": backlog_enabled,
        "cf_enabled": cf_enabled,
    }

    # ── 4. Instance Performance ───────────────────────────────────────
    logger.debug("[Intel] building instance performance")
    lifetime_rows = conn.execute("SELECT * FROM sweep_lifetime").fetchall()
    per_inst_imports = agg["per_instance_imports"]
    per_inst_ta = agg["per_instance_turnaround"]

    url_to_name = {}
    url_to_app = {}
    url_to_enabled = {}
    for app_name in ("radarr", "sonarr"):
        for inst in cfg.get("instances", {}).get(app_name, []):
            url = inst["url"].rstrip("/")
            url_to_name[url] = inst["name"]
            url_to_app[url] = app_name
            url_to_enabled[url] = inst.get("enabled", True)

    instance_performance = []
    for lr in lifetime_rows:
        inst_url, inst_name, app_name = _parse_instance_key(
            lr["instance_key"], url_to_name, url_to_app
        )

        confirmed = per_inst_imports.get(inst_url, 0)
        inst_ta = per_inst_ta.get(inst_url, {"sum": 0.0, "count": 0})
        inst_turnaround = (
            round(inst_ta["sum"] / inst_ta["count"], 2) if inst_ta["count"] > 0 else 0.0
        )

        sh_count = conn.execute(
            "SELECT SUM(search_count) FROM search_history WHERE instance_url = ?",
            (inst_url,)
        ).fetchone()[0] or 0

        instance_performance.append({
            "instance_url": inst_url,
            "instance_name": inst_name,
            "app": app_name,
            "runs": lr["runs"] or 0,
            "searched": sh_count,
            "confirmed_imports": confirmed,
            "turnaround_avg_days": inst_turnaround,
            "enabled": url_to_enabled.get(inst_url, True),
        })

    # ── 5. Upgrade History ────────────────────────────────────────────
    logger.debug("[Intel] fetching upgrade paths")
    upgrade_paths = _top_upgrade_paths(conn, limit=5)

    upgrade_history = {
        "imported_once": agg["imported_once_count"],
        "upgraded": agg["upgraded_count"],
        "upgrade_paths": upgrade_paths,
    }

    # ── 6. CF Score Health (live -- not in aggregate, not reset by Reset Intel) ──
    cf_score_health = None
    if cf_enabled:
        logger.debug("[Intel] fetching CF Score health")
        cf_score_health = db.get_cf_score_health()

    # ── 7. Exclusion Intel ────────────────────────────────────────────
    logger.debug("[Intel] building exclusion intel")
    excl_counts = conn.execute(
        "SELECT source, COUNT(*) as cnt FROM exclusions GROUP BY source"
    ).fetchall()
    manual_count = 0
    auto_count = 0
    for row in excl_counts:
        if row["source"] == "manual":
            manual_count = row["cnt"]
        elif row["source"] == "auto":
            auto_count = row["cnt"]

    now_utc = datetime.now(timezone.utc)
    first_of_month = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    first_of_month_iso = first_of_month.strftime("%Y-%m-%dT%H:%M:%SZ")
    auto_this_month = conn.execute(
        "SELECT COUNT(*) FROM exclusions WHERE source = 'auto' AND excluded_at >= ?",
        (first_of_month_iso,)
    ).fetchone()[0]

    # Titles cycled through exclusions (excluded then unexcluded at least once).
    # Counts all sources -- manual and auto exclusion cycling both count.
    cycles_row = conn.execute(
        """
        SELECT COUNT(DISTINCT ee_ex.title) AS cycled
        FROM exclusion_events ee_ex
        JOIN exclusion_events ee_un
            ON ee_un.title = ee_ex.title COLLATE NOCASE
           AND ee_un.event_type = 'unexcluded'
           AND ee_un.event_ts > ee_ex.event_ts
        WHERE ee_ex.event_type = 'excluded'
        """
    ).fetchone()
    titles_cycled = cycles_row["cycled"] if cycles_row else 0

    # Titles that were unexcluded and later confirmed imported.
    later_row = conn.execute(
        """
        SELECT COUNT(DISTINCT ee_ex.title) AS later_imported
        FROM exclusion_events ee_ex
        JOIN exclusion_events ee_un
            ON ee_un.title = ee_ex.title COLLATE NOCASE
           AND ee_un.event_type = 'unexcluded'
           AND ee_un.event_ts > ee_ex.event_ts
        LEFT JOIN stat_entries se
            ON se.title = ee_ex.title COLLATE NOCASE
           AND se.imported = 1
           AND se.imported_ts > ee_un.event_ts
        WHERE ee_ex.event_type = 'excluded'
          AND se.id IS NOT NULL
        """
    ).fetchone()
    unexcluded_later_imported = later_row["later_imported"] if later_row else 0

    auto_exclusions_enabled = (
        cfg.get("radarr_auto_exclude_enabled", False)
        or cfg.get("sonarr_auto_exclude_enabled", False)
    )

    exclusion_intel = {
        "total": manual_count + auto_count,
        "manual_count": manual_count,
        "auto_count": auto_count,
        "auto_exclusions_this_month": auto_this_month,
        "titles_cycled": titles_cycled,
        "unexcluded_later_imported": unexcluded_later_imported,
        "auto_enabled": auto_exclusions_enabled,
    }

    logger.debug("[Intel] payload assembled successfully")
    return jsonify({
        "cold_start": cold_start,
        "total_runs": total_runs,
        "import_summary": import_summary,
        "instance_performance": instance_performance,
        "upgrade_history": upgrade_history,
        "cf_score_health": cf_score_health,
        "exclusion_intel": exclusion_intel,
    })


# ── POST /api/intel/reset ─────────────────────────────────────────────

@bp.post("/api/intel/reset")
@requires_auth
def api_intel_reset():
    """Reset all Intel aggregate data to a clean slate.

    Clears intel_aggregate back to zero defaults and deletes all rows from
    exclusion_events. Called exclusively by the Reset Intel button in the
    Danger Zone. Clear History, Clear Imports, and Clear Log do not call
    this endpoint -- all four destructive operations are fully independent.
    CF Score Health is not affected as it reads live from cf_score_entries.
    """
    db.reset_intel()
    logger.info("[Intel] Intel data reset via Danger Zone")
    return jsonify({"ok": True})


# ── Helpers ───────────────────────────────────────────────────────────

def _top_upgrade_paths(conn, limit: int = 5):
    """Return the top N quality upgrade paths across all apps by count."""
    rows = conn.execute(
        """
        SELECT qh.quality_from, qh.quality_to, COUNT(*) as count
        FROM quality_history qh
        WHERE qh.quality_from IS NOT NULL
          AND qh.quality_from != ''
        GROUP BY qh.quality_from, qh.quality_to
        ORDER BY count DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()
    return [
        {"from": r["quality_from"], "to": r["quality_to"], "count": r["count"]}
        for r in rows
    ]


def _parse_instance_key(instance_key, url_to_name, url_to_app):
    """Parse a sweep_lifetime instance_key into (inst_url, inst_name, app_name).

    instance_key format is 'app|name|url' (set in sweep.py as
    f"{app}|{state_key(name, url)}"). Split on | with maxsplit=2 to
    correctly separate the three components. Falls back gracefully if the
    key is in an older format.
    """
    parts = instance_key.split("|", 2)
    if len(parts) == 3:
        app_from_key = parts[0]
        name_from_key = parts[1]
        inst_url = parts[2].rstrip("/")
    elif len(parts) == 2:
        app_from_key = None
        name_from_key = parts[0]
        inst_url = parts[1].rstrip("/")
    else:
        app_from_key = None
        name_from_key = instance_key
        inst_url = instance_key.rstrip("/")

    inst_name = url_to_name.get(inst_url, name_from_key)
    app_name = url_to_app.get(inst_url, app_from_key or "unknown")
    return inst_url, inst_name, app_name
