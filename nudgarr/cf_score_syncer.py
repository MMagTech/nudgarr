"""
nudgarr/cf_score_syncer.py

CustomFormatScoreSyncer -- builds and maintains the CF score index.

The syncer runs on its own schedule independent of the sweep pipeline.
It performs a full library pass across all configured Radarr and Sonarr
instances, writing entries to cf_score_entries for any monitored item where:
  - hasFile is True and isAvailable is True (Radarr)
  - customFormatScore >= minFormatScore (not penalised below the floor)
  - customFormatScore < cutoffFormatScore from the quality profile

The minFormatScore floor is the only score-based filter applied at sync time.
It excludes files penalised below the minimum custom format score threshold --
Radarr and Sonarr will not grab any release that scores below this floor, so
searching such items serves no purpose.

minUpgradeFormatScore is intentionally NOT applied at sync time. Whether a
found release clears the minimum increment is Radarr/Sonarr's decision at
grab time -- not Nudgarr's. This keeps CF Score Scan consistent with the
Cutoff Unmet and Backlog pipelines which also delegate grab decisions to the
arr apps. Cooldown handles the case where no qualifying release is found.

The sweep pipeline reads from cf_score_entries (worst gap first) and never
needs to understand any of this logic.  The syncer is the sole writer;
the sweep is a read-only consumer.

"""

# API batch sizes:
#   Radarr movie files: 100 IDs per request (URL length constraint)
#   DB upserts:         200 rows per transaction (throughput vs overhead balance)
#
# Delay between batches: random 100-500ms to avoid burdening the arr instance,
# especially important on underpowered hardware.
#
# The syncer defers its run if a sweep is currently in progress so the two
# jobs never hammer the arr instances simultaneously.
#
# Public:
#   CustomFormatScoreSyncer       -- class; call .run(cfg, session) to sync
#   CF_SCORE_API_BATCH_SIZE       -- 100 (Radarr moviefile endpoint limit)

import json
import logging
import random
import time
from typing import Any, Dict, List

import requests

from nudgarr import db
from nudgarr.arr_clients import (
    cf_get_quality_profiles,
    cf_radarr_get_all_movies,
    cf_radarr_get_movie_files_batch,
    cf_sonarr_get_all_series,
    cf_sonarr_get_episode_files,
    cf_sonarr_get_episodes_for_series,
)
from nudgarr.globals import STATUS
from nudgarr.utils import iso_z, utcnow

logger = logging.getLogger(__name__)

# Maximum movie file IDs per Radarr /api/v3/moviefile request.
# This is a URL length constraint -- exceeding it causes 414 errors on some
# reverse proxy configurations.  Do not increase without testing against your
# Radarr instance directly.
CF_SCORE_API_BATCH_SIZE = 100

# nudgarr_state key prefix for per-instance sync progress.
# Full key: CF_SYNC_PROGRESS_PREFIX + instance_id
# Value: JSON string {"processed": N, "total": M, "in_progress": bool}
CF_SYNC_PROGRESS_PREFIX = "cf_sync_progress|"


def _write_sync_progress(instance_id: str, processed: int, total: int, in_progress: bool) -> None:
    """Write sync progress for one instance to nudgarr_state.

    The status route reads this to populate the ring chart percentage in the
    CF Score tab.  Writes are fire-and-forget -- exceptions are swallowed so a
    failed state write never aborts a sync run.

    Args:
        instance_id:  Composite key from _make_instance_id (e.g. 'radarr|http://...')
        processed:    Items processed so far in this run
        total:        Total eligible items for this instance
        in_progress:  True while the sync is running, False when complete
    """
    try:
        db.set_state(
            CF_SYNC_PROGRESS_PREFIX + instance_id,
            json.dumps({"processed": processed, "total": total, "in_progress": in_progress}),
        )
    except Exception:
        logger.debug("[CF Sync] Failed to write progress for %s -- non-fatal", instance_id)


def _random_delay() -> None:
    """Sleep 100-500ms between API batches.

    The random range avoids predictable request patterns and reduces
    perceived load on underpowered hardware (Raspberry Pi, low-power NAS).
    Called between Radarr file batches and between Sonarr series iterations.
    """
    time.sleep(random.uniform(0.1, 0.5))


def _make_instance_id(app: str, url: str) -> str:
    """Build a stable composite key for an arr instance.

    The key is used as arr_instance_id in cf_score_entries and must be
    consistent between the syncer (writer) and the sweep pipeline (reader).
    Format: 'app|normalised_url', e.g. 'radarr|http://192.168.1.10:7878'

    Args:
        app: 'radarr' or 'sonarr'
        url: Instance base URL (trailing slash stripped for consistency)

    Returns:
        Composite string key
    """
    return f"{app}|{url.rstrip('/')}"


class CustomFormatScoreSyncer:
    """Builds and maintains the persistent CF score index.

    One instance of this class is created at startup and reused for the
    lifetime of the process.  Call run(cfg, session) to perform a full
    sync across all configured instances.

    The syncer is self-contained -- it reads cfg directly rather than
    accepting resolved values so it can be called both from the scheduled
    loop and from the manual Scan Library route.
    """

    def run(self, cfg: Dict[str, Any], session: requests.Session) -> Dict[str, Any]:
        """Perform a full CF score sync across all configured instances.

        Steps per instance:
          1. Fetch quality profiles once -- builds profile_id -> profile dict
          2. Fetch eligible library items (monitored, hasFile, isAvailable)
          3. Apply sweep filters (tags, profiles) at write time
          4. Fetch CF scores for those files in batches of 100 (Radarr) or
             read scores directly from episode file objects (Sonarr)
          5. Skip items where current_score < minFormatScore (penalised floor)
          6. Skip items where current_score >= cutoffFormatScore (already done)
          7. Batch-upsert qualifying entries (200 per DB transaction)
          8. Prune stale entries (not visited in this run)
          9. Write sync progress to nudgarr_state for ring chart animation

        Defers the entire run if a sweep is currently in progress to avoid
        simultaneous API load on underpowered hardware.

        Args:
            cfg:     Current Nudgarr config dict
            session: Shared requests.Session for connection reuse

        Returns:
            Summary dict with per-instance results for logging
        """
        if not cfg.get("cf_score_enabled", False):
            # Feature is disabled -- nothing to do
            return {}

        if STATUS.get("run_in_progress", False):
            logger.info("[CF Sync] Sweep in progress -- deferring sync run")
            return {}

        logger.info("[CF Sync] Starting library sync")
        sync_started_at = iso_z(utcnow())
        summary: Dict[str, Any] = {"radarr": [], "sonarr": []}

        radarr_instances = cfg.get("instances", {}).get("radarr", [])
        sonarr_instances = cfg.get("instances", {}).get("sonarr", [])

        for inst in radarr_instances:
            if not inst.get("enabled", True):
                continue
            result = self._sync_radarr_instance(inst, session, sync_started_at)
            summary["radarr"].append(result)

        for inst in sonarr_instances:
            if not inst.get("enabled", True):
                continue
            result = self._sync_sonarr_instance(inst, session, sync_started_at)
            summary["sonarr"].append(result)

        total_written = sum(r.get("written", 0) for r in summary["radarr"] + summary["sonarr"])
        total_pruned = sum(r.get("pruned", 0) for r in summary["radarr"] + summary["sonarr"])
        logger.info(
            "[CF Sync] Complete -- written=%d pruned=%d",
            total_written, total_pruned,
        )
        return summary

    def _sync_radarr_instance(
        self,
        inst: Dict[str, Any],
        session: requests.Session,
        sync_started_at: str,
    ) -> Dict[str, Any]:
        """Sync one Radarr instance.

        Fetches quality profiles, then all eligible movies (monitored, hasFile,
        isAvailable), applies sweep filters (tags, profiles), then batch-fetches
        CF scores. Skips files where current_score < minFormatScore (penalised
        below the floor Radarr will never grab from) or where current_score
        >= cutoffFormatScore (already at or above target).
        minUpgradeFormatScore is not applied -- that decision belongs to Radarr
        at grab time, consistent with Cutoff Unmet and Backlog pipeline behaviour.

        On any API error during profile or movie fetch the instance is skipped
        entirely and existing entries are left untouched (stale-safe).
        On batch-level errors the batch is skipped and the run continues.

        Args:
            inst:            Instance config dict (name, url, key, enabled)
            session:         Shared requests.Session
            sync_started_at: ISO-Z timestamp for stale prune boundary

        Returns:
            Result dict: name, written, skipped, pruned, error (optional)
        """
        name = inst.get("name", "?")
        url = inst.get("url", "")
        key = inst.get("key", "")
        instance_id = _make_instance_id("radarr", url)

        logger.info("[CF Sync] Radarr:%s starting", name)

        # Step 1: fetch quality profiles
        profiles = cf_get_quality_profiles(session, url, key)
        if not profiles:
            logger.warning(
                "[CF Sync] Radarr:%s -- no quality profiles returned, skipping instance",
                name,
            )
            return {"name": name, "written": 0, "skipped": 0, "pruned": 0,
                    "error": "no quality profiles"}

        # Read per-instance sweep filters -- same filters the main sweep applies to
        # the Cutoff Unmet and Backlog pipelines.  Items with excluded tags or profiles
        # are never written to the index so the sweep never searches them.
        sweep_filters = inst.get("sweep_filters", {})
        excluded_tags = set(int(t) for t in sweep_filters.get("excluded_tags", []))
        excluded_profiles = set(int(p) for p in sweep_filters.get("excluded_profiles", []))

        # Step 2: fetch all eligible movies
        movies = cf_radarr_get_all_movies(session, url, key)
        if not movies:
            logger.info("[CF Sync] Radarr:%s -- no eligible movies found", name)
            pruned = db.prune_stale_cf_scores(instance_id, sync_started_at)
            return {"name": name, "written": 0, "skipped": 0, "pruned": pruned}

        # Apply tag and profile filters -- mirrors the Cutoff Unmet filter logic
        # in sweep.py so CF Score respects the same per-instance filter configuration.
        filtered_movies = []
        filter_skipped = 0
        for movie in movies:
            if excluded_tags and (excluded_tags & movie.get("tag_ids", set())):
                logger.debug("[CF Sync] Radarr:%s skipped_tag: %s", name, movie.get("title", "?"))
                filter_skipped += 1
                continue
            if excluded_profiles and movie.get("quality_profile_id") in excluded_profiles:
                logger.debug("[CF Sync] Radarr:%s skipped_profile: %s", name, movie.get("title", "?"))
                filter_skipped += 1
                continue
            filtered_movies.append(movie)

        if filter_skipped:
            logger.info("[CF Sync] Radarr:%s -- %d movies skipped by tag/profile filter",
                        name, filter_skipped)
        movies = filtered_movies

        # Step 3: batch fetch CF scores for each movie file (100 IDs per request)
        file_id_to_movie: Dict[int, Dict[str, Any]] = {
            m["file_id"]: m for m in movies if m.get("file_id")
        }
        file_ids = list(file_id_to_movie.keys())
        total_files = len(file_ids)

        # Write initial progress -- total is now known, processed starts at 0
        _write_sync_progress(instance_id, 0, total_files, True)

        # Map file_id -> customFormatScore across all batches
        file_scores: Dict[int, int] = {}
        processed_files = 0
        try:
            for i in range(0, len(file_ids), CF_SCORE_API_BATCH_SIZE):
                batch = file_ids[i:i + CF_SCORE_API_BATCH_SIZE]
                batch_scores = cf_radarr_get_movie_files_batch(session, url, key, batch)
                file_scores.update(batch_scores)
                processed_files += len(batch)
                _write_sync_progress(instance_id, processed_files, total_files, True)
                # Courtesy delay between batches -- avoids bursting the Radarr API
                if i + CF_SCORE_API_BATCH_SIZE < len(file_ids):
                    _random_delay()

            # Step 4 & 5: apply gap filter and build upsert batch
            entries_to_write: List[Dict[str, Any]] = []
            skipped = 0

            for file_id, movie in file_id_to_movie.items():
                profile_id = movie.get("quality_profile_id", 0)
                profile = profiles.get(profile_id)
                if not profile:
                    skipped += 1
                    continue

                cutoff_score = profile.get("cutoffFormatScore", 0)
                min_format_score = profile.get("minFormatScore", 0)
                current_score = file_scores.get(file_id, 0)
                gap = cutoff_score - current_score

                # Only write items where the gap exists and the current score
                # is at or above the minimum format score floor.
                if current_score < min_format_score:
                    skipped += 1
                    logger.debug(
                        "[CF Sync] Radarr:%s skipped %s -- current_score=%d below minFormatScore=%d",
                        name, movie.get("title", "?"), current_score, min_format_score,
                    )
                    continue

                if gap <= 0:
                    skipped += 1
                    continue

                entries_to_write.append({
                    "arr_instance_id": instance_id,
                    "item_type": "movie",
                    "external_item_id": movie["id"],
                    "series_id": 0,
                    "file_id": file_id,
                    "title": movie.get("title", ""),
                    "current_score": current_score,
                    "cutoff_score": cutoff_score,
                    "quality_profile_id": profile_id,
                    "quality_profile_name": profile.get("name", ""),
                    "is_monitored": 1 if movie.get("monitored", True) else 0,
                    "added_date": movie.get("added_date", ""),
                })

            # Batch upsert -- 200 rows per DB transaction
            if entries_to_write:
                db.batch_upsert_cf_scores(entries_to_write)

            # Step 6: prune entries not touched in this run (deleted / unmonitored)
            pruned = db.prune_stale_cf_scores(instance_id, sync_started_at)

            # Mark sync complete for the ring chart
            _write_sync_progress(instance_id, total_files, total_files, False)

            logger.info(
                "[CF Sync] Radarr:%s done -- eligible=%d written=%d skipped=%d pruned=%d",
                name, len(movies), len(entries_to_write), skipped, pruned,
            )
            return {
                "name": name,
                "written": len(entries_to_write),
                "skipped": skipped,
                "pruned": pruned,
            }
        except Exception:
            # Ensure progress ring is not left frozen on exception
            _write_sync_progress(instance_id, processed_files, total_files, False)
            raise

    def _sync_sonarr_instance(
        self,
        inst: Dict[str, Any],
        session: requests.Session,
        sync_started_at: str,
    ) -> Dict[str, Any]:
        """Sync one Sonarr instance.

        Fetches quality profiles, then all monitored series, then for each
        series fetches episode files and episodes to match scores.
        A random delay is applied between series to avoid bursting the API.

        customFormatScore is already present on Sonarr episode file objects
        so no extra batch file endpoint is needed (unlike Radarr).

        On API errors at the series level the series is skipped and the run
        continues.  Profile or series list failures skip the whole instance.

        Args:
            inst:            Instance config dict
            session:         Shared requests.Session
            sync_started_at: ISO-Z timestamp for stale prune boundary

        Returns:
            Result dict: name, written, skipped, pruned, error (optional)
        """
        name = inst.get("name", "?")
        url = inst.get("url", "")
        key = inst.get("key", "")
        instance_id = _make_instance_id("sonarr", url)

        logger.info("[CF Sync] Sonarr:%s starting", name)

        # Step 1: fetch quality profiles
        profiles = cf_get_quality_profiles(session, url, key)
        if not profiles:
            logger.warning(
                "[CF Sync] Sonarr:%s -- no quality profiles returned, skipping instance",
                name,
            )
            return {"name": name, "written": 0, "skipped": 0, "pruned": 0,
                    "error": "no quality profiles"}

        # Read per-instance sweep filters -- same filters the main sweep applies.
        # Tag and profile filtering happens at the series level for Sonarr,
        # consistent with how the main sweep handles Sonarr filter logic.
        sweep_filters = inst.get("sweep_filters", {})
        excluded_tags = set(int(t) for t in sweep_filters.get("excluded_tags", []))
        excluded_profiles = set(int(p) for p in sweep_filters.get("excluded_profiles", []))

        # Step 2: fetch all monitored series
        all_series = cf_sonarr_get_all_series(session, url, key)
        if not all_series:
            logger.info("[CF Sync] Sonarr:%s -- no monitored series found", name)
            pruned = db.prune_stale_cf_scores(instance_id, sync_started_at)
            return {"name": name, "written": 0, "skipped": 0, "pruned": pruned}

        # Apply tag and profile filters at the series level
        filtered_series = []
        filter_skipped = 0
        for series in all_series:
            if excluded_tags and (excluded_tags & series.get("tag_ids", set())):
                logger.debug("[CF Sync] Sonarr:%s skipped_tag: %s", name, series.get("title", "?"))
                filter_skipped += 1
                continue
            if excluded_profiles and series.get("quality_profile_id") in excluded_profiles:
                logger.debug("[CF Sync] Sonarr:%s skipped_profile: %s", name, series.get("title", "?"))
                filter_skipped += 1
                continue
            filtered_series.append(series)

        if filter_skipped:
            logger.info("[CF Sync] Sonarr:%s -- %d series skipped by tag/profile filter",
                        name, filter_skipped)
        all_series = filtered_series

        entries_to_write: List[Dict[str, Any]] = []
        total_skipped = 0
        total_series = len(all_series)

        # Write initial progress -- total is series count, processed starts at 0
        _write_sync_progress(instance_id, 0, total_series, True)

        # Step 3: for each series, fetch episodes and episode files
        current_idx = 0
        try:
            for idx, series in enumerate(all_series):
                current_idx = idx
                series_id = series["id"]
                profile_id = series.get("quality_profile_id", 0)
                profile = profiles.get(profile_id)

                if not profile:
                    total_skipped += 1
                    continue

                cutoff_score = profile.get("cutoffFormatScore", 0)
                min_format_score = profile.get("minFormatScore", 0)

                # Fetch episodes (for eligibility: monitored, hasFile)
                episodes = cf_sonarr_get_episodes_for_series(session, url, key, series_id)
                if not episodes:
                    # Delay even on empty to respect the API
                    if idx < len(all_series) - 1:
                        _random_delay()
                    continue

                # Fetch episode files (for customFormatScore)
                ep_files = cf_sonarr_get_episode_files(session, url, key, series_id)
                # Build a lookup: file_id -> customFormatScore
                file_score_map: Dict[int, int] = {
                    ef["file_id"]: ef["custom_format_score"] for ef in ep_files
                }

                for ep in episodes:
                    file_id = ep.get("episode_file_id", 0)
                    if not file_id:
                        total_skipped += 1
                        continue

                    current_score = file_score_map.get(file_id, 0)
                    gap = cutoff_score - current_score

                    # Skip episodes where current score is below the minimum format
                    # score floor -- Radarr/Sonarr won't grab anything below that floor
                    if current_score < min_format_score:
                        total_skipped += 1
                        continue

                    if gap <= 0:
                        total_skipped += 1
                        continue

                    entries_to_write.append({
                        "arr_instance_id": instance_id,
                        "item_type": "episode",
                        "external_item_id": ep["id"],
                        "series_id": series_id,
                        "file_id": file_id,
                        "title": ep.get("title", series.get("title", "")),
                        "current_score": current_score,
                        "cutoff_score": cutoff_score,
                        "quality_profile_id": profile_id,
                        "quality_profile_name": profile.get("name", ""),
                        "is_monitored": 1 if ep.get("monitored", True) else 0,
                        "added_date": "",
                    })

                # Random delay between series -- avoids bursting Sonarr API
                if idx < len(all_series) - 1:
                    _random_delay()

                # Update progress after each series
                _write_sync_progress(instance_id, idx + 1, total_series, True)

            # Batch upsert -- 200 rows per DB transaction
            if entries_to_write:
                db.batch_upsert_cf_scores(entries_to_write)

            # Step 4: prune entries not touched in this run
            pruned = db.prune_stale_cf_scores(instance_id, sync_started_at)

            # Mark sync complete for the ring chart
            _write_sync_progress(instance_id, total_series, total_series, False)

            logger.info(
                "[CF Sync] Sonarr:%s done -- series=%d written=%d skipped=%d pruned=%d",
                name, len(all_series), len(entries_to_write), total_skipped, pruned,
            )
            return {
                "name": name,
                "written": len(entries_to_write),
                "skipped": total_skipped,
                "pruned": pruned,
            }
        except Exception:
            # Ensure progress ring is not left frozen on exception
            _write_sync_progress(instance_id, current_idx, total_series, False)
            raise
