"""
nudgarr/arr_clients.py

All outbound HTTP calls to Radarr and Sonarr. No business logic here —
these functions fetch data and trigger commands, nothing else.

  Radarr : radarr_get_cutoff_unmet_movies, radarr_get_missing_movies,
           radarr_search_movies, radarr_get_queued_movie_ids
  Sonarr : sonarr_get_cutoff_unmet_episodes, sonarr_get_missing_episodes,
           sonarr_search_episodes

All functions accept a requests.Session and the instance url + key.
Pagination is handled internally; callers receive a flat list.

To add a new arr (Lidarr, Readarr, etc.) add its functions here and
wire them into sweep.py.

Imports from within the package: utils only.
"""

from typing import Any, Dict, List

import requests

from nudgarr.utils import req


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
                movies.append({"id": mid, "title": rec.get("title") or f"Movie {mid}", "added": added, "isAvailable": rec.get("isAvailable", True), "minimumAvailability": min_avail, "releaseDate": release_date})
    return movies


def radarr_get_cutoff_unmet_movies(
    session: requests.Session,
    url: str,
    key: str,
    page_size: int = 100,
    max_pages: int = 5,
) -> List[Dict[str, Any]]:
    """Returns list of dicts: {id:int, title:str, added:str|None} from Wanted→Cutoff Unmet."""
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
    """Returns list of dicts: {id:int, title:str, added:str|None} from Wanted→Missing."""
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
        pass
    return queued


def radarr_search_movies(
    session: requests.Session,
    url: str,
    key: str,
    movie_ids: List[int],
) -> None:
    if not movie_ids:
        return
    cmd = f"{url.rstrip('/')}/api/v3/command"
    payload = {"name": "MoviesSearch", "movieIds": movie_ids}
    req(session, "POST", cmd, key, payload)
    print(f"[Radarr] Started MoviesSearch for {len(movie_ids)} movie(s)")


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
        pass
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
                episodes.append({"id": eid, "series_id": series_id, "title": title, "added": added})
    return episodes


def sonarr_get_cutoff_unmet_episodes(
    session: requests.Session,
    url: str,
    key: str,
    page_size: int = 100,
    max_pages: int = 5,
) -> List[Dict[str, Any]]:
    """Returns list of dicts: {id:int, series_id:int, title:str, added:str|None} from Wanted→Cutoff Unmet."""
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
) -> List[Dict[str, Any]]:
    """Returns list of dicts: {id:int, series_id:int, title:str, added:str|None} from Wanted→Missing."""
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
        pass
    return queued


def sonarr_search_episodes(
    session: requests.Session,
    url: str,
    key: str,
    episode_ids: List[int],
) -> None:
    if not episode_ids:
        return
    cmd = f"{url.rstrip('/')}/api/v3/command"
    payload = {"name": "EpisodeSearch", "episodeIds": episode_ids}
    req(session, "POST", cmd, key, payload)
    print(f"[Sonarr] Started EpisodeSearch for {len(episode_ids)} episode(s)")
