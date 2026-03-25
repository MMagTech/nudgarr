"""
nudgarr/routes/intel.py

Intel tab -- read-only lifetime performance dashboard route.

  GET  /api/intel       -- return full Intel payload assembled from aggregate
                          and live tables
  POST /api/intel/reset -- clear intel_aggregate and exclusion_events (Danger Zone)

All aggregate writes happen at confirm and exclusion event time in
db/entries.py and db/exclusions.py. This route only reads and resets.
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify

from nudgarr import db
from nudgarr.auth import requires_auth
from nudgarr.config import load_or_init_config

logger = logging.getLogger(__name__)

bp = Blueprint("intel", __name__)

# Calibration thresholds -- ratio of auto-excluded titles that later imported.
_CALIBRATION_HIGH = 0.20
_CALIBRATION_LOW = 0.05

# Cold start minimum thresholds.
_COLD_START_MIN_IMPORTS = 25
_COLD_START_MIN_RUNS = 50


# ── GET /api/intel ────────────────────────────────────────────────────

@bp.get("/api/intel")
@requires_auth
def api_intel():
    """Assemble and return the full Intel dashboard payload.

    Reads intel_aggregate for protected lifetime metrics, then runs a small
    set of live queries for current-state metrics (stuck items, exclusion
    counts, sweep lifetime, upgrade paths, calibration signal). All computation
    happens in Python; the frontend receives a single flat JSON object.
    """
    logger.debug("[Intel] GET /api/intel called")
    try:
        return _build_intel_payload()
    except Exception:
        logger.exception("[Intel] GET /api/intel failed")
        return {"error": "Intel data unavailable -- check logs for details."}, 500


def _build_intel_payload():
    """Assemble the full Intel payload. Separated from the route handler so
    exceptions are caught and logged at the route boundary."""
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

    # ── 3. Library Score ──────────────────────────────────────────────
    library_score = None
    if not cold_start:
        library_score = _compute_library_score(agg, cfg)
        logger.debug("[Intel] library_score=%d", library_score)

    # ── 4. Search Health ──────────────────────────────────────────────
    movies_threshold = int(cfg.get("auto_exclude_movies_threshold", 0))
    shows_threshold = int(cfg.get("auto_exclude_shows_threshold", 0))
    logger.debug("[Intel] fetching stuck items (movies_threshold=%d shows_threshold=%d)",
                 movies_threshold, shows_threshold)
    stuck_rows = db.get_high_search_count_unconfirmed(movies_threshold, shows_threshold)

    success_rate = 0.0
    if agg["success_total_worked"] > 0:
        success_rate = round(agg["success_total_imported"] / agg["success_total_worked"], 4)

    turnaround_avg = 0.0
    if agg["turnaround_count"] > 0:
        turnaround_avg = round(agg["turnaround_sum_days"] / agg["turnaround_count"], 2)

    searches_per_import_avg = 0.0
    if agg["searches_per_import_count"] > 0:
        searches_per_import_avg = round(
            agg["searches_per_import_sum"] / agg["searches_per_import_count"], 2
        )

    stuck_disabled = movies_threshold == 0 and shows_threshold == 0
    stuck_total = len(stuck_rows) if not stuck_disabled else None

    search_health = {
        "success_rate": success_rate,
        "success_total_imported": agg["success_total_imported"],
        "success_total_worked": agg["success_total_worked"],
        "turnaround_avg_days": turnaround_avg,
        "searches_per_import_avg": searches_per_import_avg,
        "stuck_items_total": stuck_total,
        "stuck_items_disabled": stuck_disabled,
        "cutoff_import_count": agg["cutoff_import_count"],
        "backlog_import_count": agg["backlog_import_count"],
        "quality_upgrades_count": agg["quality_upgrades_count"],
    }

    # ── 5. Instance Performance ───────────────────────────────────────
    logger.debug("[Intel] building instance performance")
    lifetime_rows = conn.execute("SELECT * FROM sweep_lifetime").fetchall()
    per_inst_imports = agg["per_instance_imports"]
    per_inst_ta = agg["per_instance_turnaround"]

    url_to_name = {}
    url_to_app = {}
    for app_name in ("radarr", "sonarr"):
        for inst in cfg.get("instances", {}).get(app_name, []):
            url = inst["url"].rstrip("/")
            url_to_name[url] = inst["name"]
            url_to_app[url] = app_name

    stuck_by_url = {}
    for s in stuck_rows:
        u = s["instance_url"].rstrip("/")
        stuck_by_url[u] = stuck_by_url.get(u, 0) + 1

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
            "SELECT COUNT(DISTINCT item_id) FROM search_history WHERE instance_url = ?",
            (inst_url,)
        ).fetchone()[0]
        inst_success_rate = round(confirmed / sh_count, 4) if sh_count > 0 else 0.0

        eligible = lr["eligible"] or 0
        searched = lr["searched"] or 0
        ratio = round(searched / eligible, 4) if eligible > 0 else 0.0
        callout = ratio >= 0.95 and lr["runs"] >= 10

        instance_performance.append({
            "instance_url": inst_url,
            "instance_name": inst_name,
            "app": app_name,
            "runs": lr["runs"] or 0,
            "searched": searched,
            "confirmed_imports": confirmed,
            "success_rate": inst_success_rate,
            "turnaround_avg_days": inst_turnaround,
            "eligible": eligible,
            "eligible_used_ratio": ratio,
            "eligible_used_callout": callout,
            "stuck_items": stuck_by_url.get(inst_url, 0),
        })

    # ── 6. Stuck items detail list (top 20) ───────────────────────────
    stuck_items = []
    for s in sorted(stuck_rows, key=lambda x: x["search_count"], reverse=True)[:20]:
        stuck_items.append({
            "title": s["title"],
            "app": s["app"],
            "instance_name": s["instance_name"],
            "search_count": s["search_count"],
            "first_searched": _sh_field(
                conn, s["app"], s["instance_url"], s["item_id"], "first_searched_ts"
            ),
            "library_added": _sh_field(
                conn, s["app"], s["instance_url"], s["item_id"], "library_added"
            ) or "",
        })

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

    avg_row = conn.execute(
        "SELECT AVG(search_count) as avg FROM exclusions WHERE source = 'auto'"
    ).fetchone()
    avg_searches_at_excl = round(avg_row["avg"] or 0.0, 1)

    now_utc = datetime.now(timezone.utc)
    first_of_month = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    first_of_month_iso = first_of_month.strftime("%Y-%m-%dT%H:%M:%SZ")
    auto_this_month = conn.execute(
        "SELECT COUNT(*) FROM exclusions WHERE source = 'auto' AND excluded_at >= ?",
        (first_of_month_iso,)
    ).fetchone()[0]

    logger.debug("[Intel] running calibration query")
    calibration = _compute_calibration(conn)

    exclusion_intel = {
        "total": manual_count + auto_count,
        "manual_count": manual_count,
        "auto_count": auto_count,
        "avg_searches_at_exclusion": avg_searches_at_excl,
        "auto_exclusions_this_month": auto_this_month,
        "calibration": calibration,
    }

    # ── 8. Sweep Efficiency ───────────────────────────────────────────
    sweep_efficiency = []
    for lr in lifetime_rows:
        inst_url, inst_name, app_name = _parse_instance_key(
            lr["instance_key"], url_to_name, url_to_app
        )
        eligible = lr["eligible"] or 0
        searched = lr["searched"] or 0
        ratio = round(searched / eligible, 4) if eligible > 0 else 0.0
        callout = ratio >= 0.95 and lr["runs"] >= 10
        sweep_efficiency.append({
            "instance_url": inst_url,
            "instance_name": inst_name,
            "app": app_name,
            "runs": lr["runs"] or 0,
            "eligible": eligible,
            "searched": searched,
            "ratio": ratio,
            "callout": callout,
        })

    # ── 9. Library Age ────────────────────────────────────────────────
    logger.debug("[Intel] building library age buckets")
    age_buckets_raw = agg["library_age_buckets"]
    bucket_order = [
        "Under 1 month", "1 to 3 months", "3 to 6 months",
        "6 to 12 months", "12+ months", "Unknown"
    ]
    age_buckets = []
    unknown_count = 0
    for label in bucket_order:
        data = age_buckets_raw.get(label, {"total": 0, "imported": 0})
        if label == "Unknown":
            unknown_count = data.get("total", 0)
        age_buckets.append({
            "label": label,
            "total": data.get("total", 0),
            "imported": data.get("imported", 0),
        })

    unknown_note = ""
    if unknown_count > 0:
        unknown_note = (
            f"{unknown_count} item{'s' if unknown_count != 1 else ''} could not be "
            f"bucketed \u2014 library added date unavailable."
        )

    library_age = {
        "buckets": age_buckets,
        "unknown_count": unknown_count,
        "unknown_note": unknown_note,
    }

    # ── 10. Quality Iteration ─────────────────────────────────────────
    logger.debug("[Intel] fetching upgrade paths")
    upgrade_path_radarr = _most_common_upgrade_path(conn, "radarr")
    upgrade_path_sonarr = _most_common_upgrade_path(conn, "sonarr")

    quality_iteration = {
        "imported_once": agg["imported_once_count"],
        "upgraded": agg["upgraded_count"],
        "upgrade_path_radarr": upgrade_path_radarr,
        "upgrade_path_sonarr": upgrade_path_sonarr,
    }

    logger.debug("[Intel] payload assembled successfully")
    return jsonify({
        "cold_start": cold_start,
        "total_runs": total_runs,
        "library_score": library_score,
        "search_health": search_health,
        "instance_performance": instance_performance,
        "stuck_items": stuck_items,
        "exclusion_intel": exclusion_intel,
        "sweep_efficiency": sweep_efficiency,
        "library_age": library_age,
        "quality_iteration": quality_iteration,
    })


# ── POST /api/intel/reset ─────────────────────────────────────────────

@bp.post("/api/intel/reset")
@requires_auth
def api_intel_reset():
    """Reset all Intel data to a clean slate.

    Clears intel_aggregate back to zero defaults and deletes all rows from
    exclusion_events. Called exclusively by the Reset Intel button in the
    Danger Zone. Clear History and Clear Stats do not call this endpoint.
    """
    db.reset_intel()
    logger.info("[Intel] Intel data reset via Danger Zone")
    return jsonify({"ok": True})


# ── Helpers ───────────────────────────────────────────────────────────

def _compute_library_score(agg, cfg):
    """Compute a 0-100 Library Score from four weighted sub-scores.

    Weights: success rate 40%, turnaround 25%, stuck items 20%,
    sweep efficiency 15%. Each sub-score is normalised to 0-100 before
    weighting. Returns an integer.
    """
    success_score = (
        round((agg["success_total_imported"] / agg["success_total_worked"]) * 100)
        if agg["success_total_worked"] > 0 else 0
    )

    avg_days = (
        agg["turnaround_sum_days"] / agg["turnaround_count"]
        if agg["turnaround_count"] > 0 else 30
    )
    turnaround_score = max(0, round(100 - (avg_days / 30) * 100))

    movies_threshold = int(cfg.get("auto_exclude_movies_threshold", 0))
    shows_threshold = int(cfg.get("auto_exclude_shows_threshold", 0))
    stuck_rows = db.get_high_search_count_unconfirmed(movies_threshold, shows_threshold)
    stuck_count = len(stuck_rows)
    stuck_score = max(0, 100 - stuck_count * 5)

    from nudgarr.db.connection import get_connection
    conn = get_connection()
    eff_rows = conn.execute(
        "SELECT SUM(searched) as s, SUM(eligible) as e FROM sweep_lifetime"
    ).fetchone()
    if eff_rows and eff_rows["e"] and eff_rows["e"] > 0:
        efficiency_score = round((eff_rows["s"] / eff_rows["e"]) * 100)
    else:
        efficiency_score = 50

    score = round(
        success_score * 0.40
        + turnaround_score * 0.25
        + stuck_score * 0.20
        + efficiency_score * 0.15
    )
    return min(100, max(0, score))


def _compute_calibration(conn):
    """Run the calibration signal query and return recommendation text."""
    row = conn.execute(
        """
        SELECT
            COUNT(DISTINCT ee_ex.title) AS total_unexcluded,
            COUNT(DISTINCT se.title)    AS later_imported
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
          AND ee_ex.source = 'auto'
        """
    ).fetchone()

    total = row["total_unexcluded"] if row else 0
    imported = row["later_imported"] if row else 0
    cold_start = total < 5

    if cold_start:
        recommendation = (
            "Not enough auto-unexclude cycles to draw conclusions yet. "
            "This signal will improve over time."
        )
    else:
        ratio = imported / total
        if ratio > _CALIBRATION_HIGH:
            recommendation = (
                "More than 1 in 5 auto-excluded titles eventually imported after "
                "being given another chance. Your threshold may be excluding titles "
                "too early. Consider raising it."
            )
        elif ratio >= _CALIBRATION_LOW:
            recommendation = (
                "Your threshold appears well-calibrated. A small number of "
                "auto-excluded titles imported after unexclusion, which is expected."
            )
        else:
            recommendation = (
                "Very few auto-excluded titles have imported after unexclusion. "
                "Your threshold appears to be working as intended."
            )

    return {
        "total_unexcluded": total,
        "later_imported": imported,
        "recommendation": recommendation,
        "cold_start": cold_start,
    }


def _most_common_upgrade_path(conn, app):
    """Return the most common quality_from -> quality_to upgrade path for an app."""
    row = conn.execute(
        """
        SELECT qh.quality_from, qh.quality_to, COUNT(*) as count
        FROM quality_history qh
        JOIN stat_entries se ON se.id = qh.entry_id
        WHERE qh.quality_from IS NOT NULL
          AND qh.quality_from != ''
          AND se.app = ?
        GROUP BY qh.quality_from, qh.quality_to
        ORDER BY count DESC
        LIMIT 1
        """,
        (app,)
    ).fetchone()
    if not row:
        return {"from": None, "to": None, "count": 0}
    return {
        "from": row["quality_from"],
        "to": row["quality_to"],
        "count": row["count"],
    }


def _sh_field(conn, app, instance_url, item_id, field):
    """Read a single field from search_history for a specific item."""
    row = conn.execute(
        f"SELECT {field} FROM search_history"
        f" WHERE app = ? AND instance_url = ? AND item_id = ? LIMIT 1",
        (app, instance_url, item_id)
    ).fetchone()
    return row[field] if row else ""


def _parse_instance_key(instance_key, url_to_name, url_to_app):
    """Parse a sweep_lifetime instance_key into (inst_url, inst_name, app_name).

    instance_key format is 'app|name|url' (set in sweep.py as
    f"{app}|{state_key(name, url)}"). Split on | with maxsplit=2 to
    correctly separate the three components. Falls back gracefully if the
    key is in an older format.
    """
    parts = instance_key.split("|", 2)
    if len(parts) == 3:
        # Current format: app|name|url
        app_from_key = parts[0]
        name_from_key = parts[1]
        inst_url = parts[2].rstrip("/")
    elif len(parts) == 2:
        # Legacy format: name|url
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
