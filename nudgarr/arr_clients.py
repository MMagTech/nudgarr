"""
nudgarr/arr_clients.py

All outbound HTTP calls to Radarr and Sonarr. No business logic here —
these functions fetch data and trigger commands, nothing else.

  Radarr : radarr_get_cutoff_unmet_movies, radarr_get_missing_movies,
           radarr_search_movies
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

def radarr_get_cutoff_unmet_movies(
    session: requests.Session,
    url: str,
    key: str,
    page_size: int = 100,
    max_pages: int = 5,
) -> List[Dict[str, Any]]:
    """Returns list of dicts: {id:int, title:str, added:str|None} from Wanted→Cutoff Unmet."""
    movies: List[Dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        endpoint = f"{url.rstrip('/')}/api/v3/wanted/cutoff?page={page}&pageSize={page_size}"
        data = req(session, "GET", endpoint, key)
        if not isinstance(data, dict):
            break
        records = data.get("records") or []
        if not records:
            break
        for rec in records:
            # Radarr /wanted/cutoff returns movie objects directly; primary key is "id"
            mid = rec.get("id") or rec.get("movieId")
            added = rec.get("added") or rec.get("addedDate") or rec.get("addedUtc")
            if isinstance(mid, int):
                movies.append({"id": mid, "title": rec.get("title") or f"Movie {mid}", "added": added})
    return movies


def radarr_get_missing_movies(
    session: requests.Session,
    url: str,
    key: str,
    page_size: int = 100,
    max_pages: int = 5,
) -> List[Dict[str, Any]]:
    """Returns list of dicts: {id:int, title:str, added:str|None} from Wanted→Missing."""
    out: List[Dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        endpoint = f"{url.rstrip('/')}/api/v3/wanted/missing?page={page}&pageSize={page_size}"
        data = req(session, "GET", endpoint, key)
        if not isinstance(data, dict):
            break
        records = data.get("records") or []
        if not records:
            break
        for rec in records:
            # Radarr /wanted/missing returns movie objects directly; primary key is "id"
            mid = rec.get("id") or rec.get("movieId")
            added = rec.get("added") or rec.get("addedDate") or rec.get("addedUtc")
            if isinstance(mid, int):
                out.append({"id": mid, "title": rec.get("title") or f"Movie {mid}", "added": added})
    return out


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

def sonarr_get_cutoff_unmet_episodes(
    session: requests.Session,
    url: str,
    key: str,
    page_size: int = 100,
    max_pages: int = 5,
) -> List[Dict[str, Any]]:
    """Returns list of dicts: {id:int, series_id:int, title:str, added:str|None} from Wanted→Cutoff Unmet."""
    # First fetch all series to build id→title map
    series_map: Dict[int, str] = {}
    try:
        series_data = req(session, "GET", f"{url.rstrip('/')}/api/v3/series", key)
        if isinstance(series_data, list):
            for s in series_data:
                if isinstance(s.get("id"), int) and isinstance(s.get("title"), str):
                    series_map[s["id"]] = s["title"]
    except Exception:
        pass

    episodes: List[Dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        endpoint = f"{url.rstrip('/')}/api/v3/wanted/cutoff?page={page}&pageSize={page_size}"
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


def sonarr_get_missing_episodes(
    session: requests.Session,
    url: str,
    key: str,
    page_size: int = 100,
    max_pages: int = 5,
) -> List[Dict[str, Any]]:
    """Returns list of dicts: {id:int, series_id:int, title:str, added:str|None} from Wanted→Missing."""
    # Reuse series map
    series_map: Dict[int, str] = {}
    try:
        series_data = req(session, "GET", f"{url.rstrip('/')}/api/v3/series", key)
        if isinstance(series_data, list):
            for s in series_data:
                if isinstance(s.get("id"), int) and isinstance(s.get("title"), str):
                    series_map[s["id"]] = s["title"]
    except Exception:
        pass

    episodes: List[Dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        endpoint = f"{url.rstrip('/')}/api/v3/wanted/missing?page={page}&pageSize={page_size}"
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

