"""
nudgarr/arr_clients.py

All outbound HTTP calls to Radarr and Sonarr. No business logic here —
these functions fetch data and trigger commands, nothing else.

  Radarr : radarr_get_cutoff_unmet_movies, radarr_get_missing_movies,
           radarr_search_movies, radarr_get_queued_movie_ids,
           radarr_get_movie_quality
  Sonarr : sonarr_get_cutoff_unmet_episodes, sonarr_get_missing_episodes,
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

from nudgarr.utils import req

logger = logging.getLogger(__name__)


# ── Radarr ────────────────────────────────────────────────────────────

def _radarr_movies_from_wanted(
    session: requests.Session,
    url: str,
    key: str,
    endpoint_path: str,
    page_size: int = 100,
    max_pages: int = 5,
) -> List[Dict[str, Any]]:
    """Shared pagination helper for Radarr wanted endpoints."""
    movies: List[Dict[str, Any]] = []
    for page in range(1, max_pages + 1):
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
                movies.append({"id": mid, "title": rec.get("title") or f"Movie {mid}", "added": added, "isAvailable": rec.get("isAvailable", True), "minimumAvailability": min_avail, "releaseDate": release_date, "quality_from": quality_from})
    return movies


def radarr_get_cutoff_unmet_movies(
    session: requests.Session,
    url: str,
    key: str,
    page_size: int = 100,
    max_pages: int = 5,
) -> List[Dict[str, Any]]:
    """Returns list of dicts: {id:int, title:str, added:str|None} from Wanted->Cutoff Unmet."""
    return _radarr_movies_from_wanted(
        session, url, key, "/api/v3/wanted/cutoff", page_size, max_pages
    )


def radarr_get_missing_movies(
    session: requests.Session,
    url: str,
    key: str,
    page_size: int = 100,
    max_pages: int = 5,
) -> List[Dict[str, Any]]:
    """Returns list of dicts: {id:int, title:str, added:str|None} from Wanted->Missing."""
    return _radarr_movies_from_wanted(
        session, url, key, "/api/v3/wanted/missing", page_size, max_pages
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


# ── Sonarr ────────────────────────────────────────────────────────────

def _sonarr_get_series_map(
    session: requests.Session,
    url: str,
    key: str,
) -> Dict[int, str]:
    """Fetch all series from Sonarr and return {series_id: title} map."""
    series_map: Dict[int, str] = {}
    try:
        series_data = req(session, "GET", f"{url.rstrip('/')}/api/v3/series", key)
        if isinstance(series_data, list):
            for s in series_data:
                if isinstance(s.get("id"), int) and isinstance(s.get("title"), str):
                    series_map[s["id"]] = s["title"]
    except Exception:
        # L-F4: warn with traceback — a failure here causes every episode to show
        # as "Episode {id}" for the entire sweep run, which is a data quality issue
        logger.warning("[Sonarr] _sonarr_get_series_map failed — episode titles will fall back to ID-based names", exc_info=True)
    return series_map


def _sonarr_episodes_from_wanted(
    session: requests.Session,
    url: str,
    key: str,
    endpoint_path: str,
    series_map: Dict[int, str],
    page_size: int = 100,
    max_pages: int = 5,
) -> List[Dict[str, Any]]:
    """Shared pagination helper for Sonarr wanted endpoints."""
    episodes: List[Dict[str, Any]] = []
    for page in range(1, max_pages + 1):
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
                series_title = series_map.get(series_id) if series_id else None
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
                episodes.append({"id": eid, "series_id": series_id, "title": title, "added": added, "quality_from": quality_from})
    return episodes


def sonarr_get_cutoff_unmet_episodes(
    session: requests.Session,
    url: str,
    key: str,
    page_size: int = 100,
    max_pages: int = 5,
    series_map: Dict[int, str] = None,
) -> List[Dict[str, Any]]:
    """Returns list of dicts: {id:int, series_id:int, title:str, added:str|None} from Wanted->Cutoff Unmet.

    series_map is optional. If provided, the series list fetch is skipped — pass it when
    calling both cutoff and missing in the same sweep to avoid fetching /api/v3/series twice.
    """
    if series_map is None:
        series_map = _sonarr_get_series_map(session, url, key)
    return _sonarr_episodes_from_wanted(
        session, url, key, "/api/v3/wanted/cutoff", series_map, page_size, max_pages
    )


def sonarr_get_missing_episodes(
    session: requests.Session,
    url: str,
    key: str,
    page_size: int = 100,
    max_pages: int = 5,
    series_map: Dict[int, str] = None,
) -> List[Dict[str, Any]]:
    """Returns list of dicts: {id:int, series_id:int, title:str, added:str|None} from Wanted->Missing.

    series_map is optional. If provided, the series list fetch is skipped — pass it when
    calling both cutoff and missing in the same sweep to avoid fetching /api/v3/series twice.
    """
    if series_map is None:
        series_map = _sonarr_get_series_map(session, url, key)
    return _sonarr_episodes_from_wanted(
        session, url, key, "/api/v3/wanted/missing", series_map, page_size, max_pages
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
