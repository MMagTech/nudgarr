"""
nudgarr/arr_clients.py

All outbound HTTP calls to Radarr and Sonarr. No business logic here —
these functions fetch data and trigger commands, nothing else.

  Shared  : arr_get_tag_map, arr_get_profile_map
  Radarr  : radarr_get_cutoff_unmet_movies, radarr_get_missing_movies,
            radarr_search_movies, radarr_get_queued_movie_ids,
            radarr_get_movie_quality
  Sonarr  : sonarr_get_cutoff_unmet_episodes, sonarr_get_missing_episodes,
            sonarr_search_episodes, sonarr_get_episode_quality

All functions accept a requests.Session and the instance url + key.
Pagination is handled internally; callers receive a flat list.

To add a new arr (Lidarr, Readarr, etc.) add its functions here and
wire them into sweep.py.

Imports from within the package: utils only.
"""

import logging
from typing import Any, Dict, List

import requests

from nudgarr.utils import mask_url, req

logger = logging.getLogger(__name__)


# ── Radarr ────────────────────────────────────────────────────────────

def _radarr_movies_from_wanted(
    session: requests.Session,
    url: str,
    key: str,
    endpoint_path: str,
    page_size: int = 500,
) -> List[Dict[str, Any]]:
    """Shared pagination helper for Radarr wanted endpoints.

    Fetches all pages until the API returns an empty records list.
    page_size=500 minimises round-trips for large libraries without
    any behavioural change — all sample modes operate on the full set.
    """
    movies: List[Dict[str, Any]] = []
    page = 1
    while True:
        endpoint = f"{url.rstrip('/')}{endpoint_path}?page={page}&pageSize={page_size}"
        data = req(session, "GET", endpoint, key)
        if not isinstance(data, dict):
            break
        records = data.get("records") or []
        if not records:
            break
        for rec in records:
            # Radarr wanted endpoints return movie objects directly; primary key is "id"
            mid = rec.get("id") or rec.get("movieId")
            added = rec.get("added") or rec.get("addedDate") or rec.get("addedUtc")
            if isinstance(mid, int):
                min_avail = rec.get("minimumAvailability", "")
                release_date = rec.get("physicalRelease") or rec.get("digitalRelease") or rec.get("inCinemas") or ""
                quality_from = ""
                try:
                    quality_from = rec["movieFile"]["quality"]["quality"]["name"] or ""
                except (KeyError, TypeError):
                    pass
                movies.append({"id": mid, "title": rec.get("title") or f"Movie {mid}", "added": added, "isAvailable": rec.get("isAvailable", True), "minimumAvailability": min_avail, "releaseDate": release_date, "quality_from": quality_from, "qualityProfileId": rec.get("qualityProfileId"), "tagIds": rec.get("tags") or []})
        page += 1
    return movies


def radarr_get_cutoff_unmet_movies(
    session: requests.Session,
    url: str,
    key: str,
    page_size: int = 500,
) -> List[Dict[str, Any]]:
    """Returns all cutoff-unmet movies from Radarr Wanted->Cutoff Unmet."""
    return _radarr_movies_from_wanted(
        session, url, key, "/api/v3/wanted/cutoff", page_size
    )


def radarr_get_missing_movies(
    session: requests.Session,
    url: str,
    key: str,
    page_size: int = 500,
) -> List[Dict[str, Any]]:
    """Returns all missing movies from Radarr Wanted->Missing."""
    return _radarr_movies_from_wanted(
        session, url, key, "/api/v3/wanted/missing", page_size
    )


def radarr_get_queued_movie_ids(
    session: requests.Session,
    url: str,
    key: str,
) -> set:
    """Returns a set of movieId integers currently in the Radarr download queue."""
    queued: set = set()
    try:
        endpoint = f"{url.rstrip('/')}/api/v3/queue?pageSize=1000&includeUnknownMovieItems=false"
        data = req(session, "GET", endpoint, key)
        if isinstance(data, dict):
            for rec in data.get("records") or []:
                mid = rec.get("movieId")
                if isinstance(mid, int):
                    queued.add(mid)
    except Exception:
        # L-F4: warn with traceback so queue failures are diagnosable without being fatal
        logger.warning("[Radarr] radarr_get_queued_movie_ids failed — queued IDs unavailable", exc_info=True)
    return queued


def radarr_search_movies(
    session: requests.Session,
    url: str,
    key: str,
    movie_ids: List[int],
    instance_name: str = "",
) -> None:
    """Trigger a MoviesSearch command for the given movie IDs. Returns None.
    No-op if movie_ids is empty."""
    if not movie_ids:
        return
    cmd = f"{url.rstrip('/')}/api/v3/command"
    payload = {"name": "MoviesSearch", "movieIds": movie_ids}
    req(session, "POST", cmd, key, payload)
    # L-F13: include instance name so multiple Radarr instances are distinguishable in logs
    label = f"Radarr:{instance_name}" if instance_name else "Radarr"
    logger.info("[%s] Started MoviesSearch for %d movie(s)", label, len(movie_ids))


# ── Shared ────────────────────────────────────────────────────────────

def arr_get_tag_map(
    session: requests.Session,
    url: str,
    key: str,
) -> Dict[int, str]:
    """Fetch all tags from a Radarr or Sonarr instance and return {tag_id: label}.

    Both apps share the same /api/v3/tag endpoint. Returns an empty dict on
    failure so callers degrade gracefully (numeric IDs shown instead of labels).
    """
    tag_map: Dict[int, str] = {}
    try:
        data = req(session, "GET", f"{url.rstrip('/')}/api/v3/tag", key)
        if isinstance(data, list):
            for t in data:
                if isinstance(t.get("id"), int) and isinstance(t.get("label"), str):
                    tag_map[t["id"]] = t["label"]
    except Exception:
        # L-F4: warn with traceback — failure here means filter logging falls back
        # to numeric IDs rather than labels, which is acceptable but worth flagging
        logger.warning("arr_get_tag_map failed for %s — tag labels unavailable", mask_url(url), exc_info=True)
    return tag_map


def arr_get_profile_map(
    session: requests.Session,
    url: str,
    key: str,
) -> Dict[int, str]:
    """Fetch all quality profiles from a Radarr or Sonarr instance and return {profile_id: name}.

    Both apps share the same /api/v3/qualityProfile endpoint. Returns an empty dict on
    failure so callers degrade gracefully (numeric IDs shown instead of names).
    """
    profile_map: Dict[int, str] = {}
    try:
        data = req(session, "GET", f"{url.rstrip('/')}/api/v3/qualityProfile", key)
        if isinstance(data, list):
            for p in data:
                if isinstance(p.get("id"), int) and isinstance(p.get("name"), str):
                    profile_map[p["id"]] = p["name"]
    except Exception:
        # L-F4: warn with traceback — failure here means filter logging falls back
        # to numeric IDs rather than names, which is acceptable but worth flagging
        logger.warning("arr_get_profile_map failed for %s — profile names unavailable", mask_url(url), exc_info=True)
    return profile_map


def _sonarr_get_series_meta(
    session: requests.Session,
    url: str,
    key: str,
) -> Dict[int, Dict[str, Any]]:
    """Fetch all series from Sonarr and return {series_id: {title, qualityProfileId, tagIds}} map."""
    series_meta: Dict[int, Dict[str, Any]] = {}
    try:
        series_data = req(session, "GET", f"{url.rstrip('/')}/api/v3/series", key)
        if isinstance(series_data, list):
            for s in series_data:
                if isinstance(s.get("id"), int) and isinstance(s.get("title"), str):
                    series_meta[s["id"]] = {
                        "title": s["title"],
                        "qualityProfileId": s.get("qualityProfileId"),
                        "tagIds": s.get("tags") or [],
                    }
    except Exception:
        # L-F4: warn with traceback — a failure here causes every episode to show
        # as "Episode {id}" for the entire sweep run, which is a data quality issue
        logger.warning("[Sonarr] _sonarr_get_series_meta failed — episode titles will fall back to ID-based names", exc_info=True)
    return series_meta


def _sonarr_episodes_from_wanted(
    session: requests.Session,
    url: str,
    key: str,
    endpoint_path: str,
    series_meta: Dict[int, Dict[str, Any]],
    page_size: int = 500,
) -> List[Dict[str, Any]]:
    """Shared pagination helper for Sonarr wanted endpoints.

    Fetches all pages until the API returns an empty records list.
    page_size=500 minimises round-trips for large libraries without
    any behavioural change — all sample modes operate on the full set.
    """
    episodes: List[Dict[str, Any]] = []
    page = 1
    while True:
        endpoint = f"{url.rstrip('/')}{endpoint_path}?page={page}&pageSize={page_size}"
        data = req(session, "GET", endpoint, key)
        if not isinstance(data, dict):
            break
        records = data.get("records") or []
        if not records:
            break
        for rec in records:
            eid = rec.get("id") or rec.get("episodeId")
            if isinstance(eid, int):
                series_id = rec.get("seriesId")
                meta = series_meta.get(series_id) if series_id else None
                series_title = meta.get("title") if meta else None
                season = rec.get("seasonNumber")
                ep_num = rec.get("episodeNumber")
                ep_title = rec.get("title")
                added = rec.get("airDateUtc") or rec.get("added")
                if series_title and season is not None and ep_num is not None:
                    title = f"{series_title} S{season:02d}E{ep_num:02d}"
                    if ep_title:
                        title += f" · {ep_title}"
                else:
                    title = ep_title or f"Episode {eid}"
                quality_from = ""
                try:
                    quality_from = rec["episodeFile"]["quality"]["quality"]["name"] or ""
                except (KeyError, TypeError):
                    pass
                episodes.append({
                    "id": eid,
                    "series_id": series_id,
                    "title": title,
                    "added": added,
                    "quality_from": quality_from,
                    "qualityProfileId": meta.get("qualityProfileId") if meta else None,
                    "tagIds": meta.get("tagIds") or [] if meta else [],
                })
        page += 1
    return episodes


def sonarr_get_cutoff_unmet_episodes(
    session: requests.Session,
    url: str,
    key: str,
    page_size: int = 500,
    series_meta: Dict[int, Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Returns all cutoff-unmet episodes from Sonarr Wanted->Cutoff Unmet.

    series_meta is optional. If provided, the series list fetch is skipped — pass it when
    calling both cutoff and missing in the same sweep to avoid fetching /api/v3/series twice.
    """
    if series_meta is None:
        series_meta = _sonarr_get_series_meta(session, url, key)
    return _sonarr_episodes_from_wanted(
        session, url, key, "/api/v3/wanted/cutoff", series_meta, page_size
    )


def sonarr_get_missing_episodes(
    session: requests.Session,
    url: str,
    key: str,
    page_size: int = 500,
    series_meta: Dict[int, Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Returns all missing episodes from Sonarr Wanted->Missing.

    series_meta is optional. If provided, the series list fetch is skipped — pass it when
    calling both cutoff and missing in the same sweep to avoid fetching /api/v3/series twice.
    """
    if series_meta is None:
        series_meta = _sonarr_get_series_meta(session, url, key)
    return _sonarr_episodes_from_wanted(
        session, url, key, "/api/v3/wanted/missing", series_meta, page_size
    )


def sonarr_get_queued_episode_ids(
    session: requests.Session,
    url: str,
    key: str,
) -> set:
    """Returns a set of episodeId integers currently in the Sonarr download queue."""
    queued: set = set()
    try:
        endpoint = f"{url.rstrip('/')}/api/v3/queue?pageSize=1000&includeUnknownSeriesItems=false"
        data = req(session, "GET", endpoint, key)
        if isinstance(data, dict):
            for rec in data.get("records") or []:
                eid = rec.get("episodeId")
                if isinstance(eid, int):
                    queued.add(eid)
    except Exception:
        # L-F4: warn with traceback so queue failures are diagnosable without being fatal
        logger.warning("[Sonarr] sonarr_get_queued_episode_ids failed — queued IDs unavailable", exc_info=True)
    return queued


def sonarr_search_episodes(
    session: requests.Session,
    url: str,
    key: str,
    episode_ids: List[int],
    instance_name: str = "",
) -> None:
    """Trigger an EpisodeSearch command for the given episode IDs. Returns None.
    No-op if episode_ids is empty."""
    if not episode_ids:
        return
    cmd = f"{url.rstrip('/')}/api/v3/command"
    payload = {"name": "EpisodeSearch", "episodeIds": episode_ids}
    req(session, "POST", cmd, key, payload)
    # L-F13: include instance name so multiple Sonarr instances are distinguishable in logs
    label = f"Sonarr:{instance_name}" if instance_name else "Sonarr"
    logger.info("[%s] Started EpisodeSearch for %d episode(s)", label, len(episode_ids))


def radarr_get_movie_quality(
    session: requests.Session,
    url: str,
    key: str,
    movie_id: int,
) -> str:
    """Return the current file quality name for a Radarr movie, or empty string
    if no file exists or the request fails. Used by the backlog sweep to capture
    quality_from for items that already have a file despite appearing in the
    missing list."""
    try:
        endpoint = f"{url.rstrip('/')}/api/v3/movie/{movie_id}"
        data = req(session, "GET", endpoint, key)
        if isinstance(data, dict):
            return data["movieFile"]["quality"]["quality"]["name"] or ""
    except (KeyError, TypeError):
        pass
    except Exception:
        # L-F5: debug level — repeated failures produce blank quality_from values
        # which is acceptable; this makes the pattern diagnosable at debug level
        logger.debug("[Radarr] quality fetch failed for movie_id=%d — quality_from will be empty", movie_id)
    return ""


def sonarr_get_episode_quality(
    session: requests.Session,
    url: str,
    key: str,
    episode_id: int,
) -> str:
    """Return the current file quality name for a Sonarr episode, or empty string
    if no file exists or the request fails. Used by the backlog sweep to capture
    quality_from for items that already have a file despite appearing in the
    missing list."""
    try:
        endpoint = f"{url.rstrip('/')}/api/v3/episode/{episode_id}"
        data = req(session, "GET", endpoint, key)
        if isinstance(data, dict):
            return data["episodeFile"]["quality"]["quality"]["name"] or ""
    except (KeyError, TypeError):
        pass
    except Exception:
        # L-F5: debug level — repeated failures produce blank quality_from values
        logger.debug("[Sonarr] quality fetch failed for episode_id=%d — quality_from will be empty", episode_id)
    return ""


# ── CF Score Scan API calls (v4.2.0) ──────────────────────────────────
#
# These functions are used exclusively by CustomFormatScoreSyncer.
# They are intentionally separate from the sweep-facing functions above
# to keep the responsibility boundary clear: syncer fetches library-wide
# data for index building; sweep functions fetch targeted candidate lists.

def cf_get_quality_profiles(
    session: requests.Session,
    url: str,
    key: str,
) -> Dict[int, Dict[str, Any]]:
    """Fetch all quality profiles and return a profile_id -> profile dict.

    Called once per instance at the start of each sync run.  The returned
    dict is used to look up cutoffFormatScore and minUpgradeFormatScore
    per profile when evaluating whether a movie or episode file qualifies
    for the CF score index.

    Works identically for both Radarr and Sonarr since both expose the
    same GET /api/v3/qualityprofile endpoint and response structure.

    Returns empty dict on any API error so the caller can skip the instance
    gracefully rather than crashing the sync run.

    Args:
        session: Shared requests.Session for connection reuse
        url:     Instance base URL
        key:     API key

    Returns:
        Dict mapping profile ID (int) to the full profile dict.
        Relevant keys: cutoffFormatScore, minUpgradeFormatScore, name, id
    """
    endpoint = f"{url.rstrip('/')}/api/v3/qualityprofile"
    try:
        data = req(session, "GET", endpoint, key)
        if not isinstance(data, list):
            logger.warning("[CF Sync] qualityprofile returned unexpected type from %s", mask_url(url))
            return {}
        return {p["id"]: p for p in data if isinstance(p, dict) and "id" in p}
    except Exception:
        logger.exception("[CF Sync] Failed to fetch quality profiles from %s", mask_url(url))
        return {}


def cf_radarr_get_all_movies(
    session: requests.Session,
    url: str,
    key: str,
) -> List[Dict[str, Any]]:
    """Fetch all Radarr movies and return those eligible for CF score syncing.

    Filters to monitored movies that have a file and where qualityCutoffNotMet
    is False -- meaning the quality tier is already satisfied and the movie is
    therefore invisible to the standard Cutoff Unmet pipeline.  These are the
    only movies where CF score scanning adds value.

    Returns a list of minimal dicts containing just the fields the syncer needs:
      id, title, movieFileId, qualityProfileId, monitored, qualityCutoffNotMet

    Returns empty list on any API error.

    Args:
        session: Shared requests.Session
        url:     Radarr base URL
        key:     Radarr API key
    """
    endpoint = f"{url.rstrip('/')}/api/v3/movie"
    try:
        data = req(session, "GET", endpoint, key)
        if not isinstance(data, list):
            logger.warning("[CF Sync] /api/v3/movie returned unexpected type from %s", mask_url(url))
            return []
        result = []
        for rec in data:
            if not isinstance(rec, dict):
                continue
            # Only monitored movies with a file where quality tier is met
            if not rec.get("monitored", False):
                continue
            if not rec.get("hasFile", False):
                continue
            if rec.get("qualityCutoffNotMet", True):
                # Quality tier is not met -- owned by Cutoff Unmet pipeline
                continue
            if not rec.get("isAvailable", True):
                # Not yet available -- consistent with Cutoff Unmet availability filter
                continue
            movie_file = rec.get("movieFile") or {}
            file_id = movie_file.get("id", 0)
            if not file_id:
                continue
            result.append({
                "id": rec["id"],
                "title": rec.get("title") or f"Movie {rec['id']}",
                "file_id": file_id,
                "quality_profile_id": rec.get("qualityProfileId", 0),
                "monitored": rec.get("monitored", True),
                "tag_ids": set(int(t) for t in (rec.get("tags") or [])),
            })
        logger.debug("[CF Sync] Radarr %s: %d eligible movies (hasFile, monitored, cutoff met)",
                     mask_url(url), len(result))
        return result
    except Exception:
        logger.exception("[CF Sync] Failed to fetch movies from %s", mask_url(url))
        return []


def cf_radarr_get_movie_files_batch(
    session: requests.Session,
    url: str,
    key: str,
    file_ids: List[int],
) -> Dict[int, int]:
    """Fetch customFormatScore for a batch of Radarr movie file IDs.

    Calls GET /api/v3/moviefile with up to 100 movieFileIds per request
    (enforced by callers -- this function accepts whatever list is passed).
    Returns a dict mapping file_id -> customFormatScore.

    The 100-ID limit per request is a Radarr URL length constraint; callers
    (CustomFormatScoreSyncer) are responsible for chunking before calling this.

    Returns empty dict on any API error so the caller can skip the batch.

    Args:
        session:  Shared requests.Session
        url:      Radarr base URL
        key:      Radarr API key
        file_ids: List of movie file IDs to fetch (max 100 per call)

    Returns:
        Dict mapping file_id (int) to customFormatScore (int)
    """
    if not file_ids:
        return {}
    endpoint = f"{url.rstrip('/')}/api/v3/moviefile"
    # Build repeated movieFileIds query params as a list of tuples.
    # requests encodes these correctly as ?movieFileIds=1&movieFileIds=2...
    params = [("movieFileIds", fid) for fid in file_ids]
    try:
        headers = {"X-Api-Key": key}
        r = session.get(endpoint, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json() if r.text else []
        if not isinstance(data, list):
            return {}
        return {
            rec["id"]: rec.get("customFormatScore", 0)
            for rec in data
            if isinstance(rec, dict) and "id" in rec
        }
    except Exception:
        logger.exception(
            "[CF Sync] Failed to fetch movie file batch (%d ids) from %s",
            len(file_ids), mask_url(url),
        )
        return {}


def cf_sonarr_get_all_series(
    session: requests.Session,
    url: str,
    key: str,
) -> List[Dict[str, Any]]:
    """Fetch all Sonarr series and return a minimal list for CF sync iteration.

    Returns a list of dicts with id, title, qualityProfileId, monitored,
    and tag_ids.  The syncer uses tag_ids and quality_profile_id to apply
    sweep_filters (excluded tags and excluded profiles) before iterating
    episode files, consistent with how the main sweep filters Sonarr items.

    Only monitored series are returned -- unmonitored series are invisible
    to all Nudgarr pipelines by design.

    Returns empty list on any API error.

    Args:
        session: Shared requests.Session
        url:     Sonarr base URL
        key:     Sonarr API key
    """
    endpoint = f"{url.rstrip('/')}/api/v3/series"
    try:
        data = req(session, "GET", endpoint, key)
        if not isinstance(data, list):
            logger.warning("[CF Sync] /api/v3/series returned unexpected type from %s", mask_url(url))
            return []
        result = []
        for rec in data:
            if not isinstance(rec, dict):
                continue
            if not rec.get("monitored", False):
                continue
            result.append({
                "id": rec["id"],
                "title": rec.get("title") or f"Series {rec['id']}",
                "quality_profile_id": rec.get("qualityProfileId", 0),
                "monitored": rec.get("monitored", True),
                "tag_ids": set(int(t) for t in (rec.get("tags") or [])),
            })
        return result
    except Exception:
        logger.exception("[CF Sync] Failed to fetch series from %s", mask_url(url))
        return []


def cf_sonarr_get_episode_files(
    session: requests.Session,
    url: str,
    key: str,
    series_id: int,
) -> List[Dict[str, Any]]:
    """Fetch all episode files for one Sonarr series.

    Calls GET /api/v3/episodefile?seriesId=X.  The customFormatScore is
    present directly on each episode file object -- no extra batch call
    is needed unlike the Radarr implementation.

    Returns a list of minimal dicts with episodeId, id (file_id), and
    customFormatScore.  Returns empty list on any API error.

    Args:
        session:   Shared requests.Session
        url:       Sonarr base URL
        key:       Sonarr API key
        series_id: Sonarr series database ID

    Returns:
        List of dicts with: id (file_id), customFormatScore
    """
    endpoint = f"{url.rstrip('/')}/api/v3/episodefile"
    try:
        data = req(session, "GET", endpoint, key, params={"seriesId": series_id})
        if not isinstance(data, list):
            return []
        result = []
        for rec in data:
            if not isinstance(rec, dict) or "id" not in rec:
                continue
            result.append({
                "file_id": rec["id"],
                "custom_format_score": rec.get("customFormatScore", 0),
            })
        return result
    except Exception:
        logger.exception(
            "[CF Sync] Failed to fetch episode files for series_id=%d from %s",
            series_id, mask_url(url),
        )
        return []


def cf_sonarr_get_episodes_for_series(
    session: requests.Session,
    url: str,
    key: str,
    series_id: int,
) -> List[Dict[str, Any]]:
    """Fetch all episodes for one Sonarr series.

    Calls GET /api/v3/episode?seriesId=X.  Used alongside
    cf_sonarr_get_episode_files to match episodes to their file scores
    and check qualityCutoffNotMet per episode.

    Only returns monitored episodes that have a file and where
    qualityCutoffNotMet is False -- same eligibility logic as the Radarr
    movie fetch.  Returns empty list on any API error.

    Args:
        session:   Shared requests.Session
        url:       Sonarr base URL
        key:       Sonarr API key
        series_id: Sonarr series database ID
    """
    endpoint = f"{url.rstrip('/')}/api/v3/episode"
    try:
        data = req(session, "GET", endpoint, key, params={"seriesId": series_id})
        if not isinstance(data, list):
            return []
        result = []
        for rec in data:
            if not isinstance(rec, dict) or "id" not in rec:
                continue
            if not rec.get("monitored", False):
                continue
            if not rec.get("hasFile", False):
                continue
            if rec.get("qualityCutoffNotMet", True):
                # Quality tier not met -- owned by Cutoff Unmet pipeline
                continue
            result.append({
                "id": rec["id"],
                "series_id": series_id,
                "episode_file_id": rec.get("episodeFileId", 0),
                "title": rec.get("title") or f"Episode {rec['id']}",
                "monitored": rec.get("monitored", True),
            })
        return result
    except Exception:
        logger.exception(
            "[CF Sync] Failed to fetch episodes for series_id=%d from %s",
            series_id, mask_url(url),
        )
        return []
