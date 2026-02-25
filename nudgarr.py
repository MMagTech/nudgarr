#!/usr/bin/env python3
"""
Nudgarr v1.2.0 — Because RSS sometimes needs a nudge.

Core:
- Caps per run for Radarr (movies) and Sonarr (episodes)
- Persistent JSON state DB under /config with cooldown
- Loop / once modes

v1.2 UI:
- Clean minimal control panel (Instances / Settings / State / Advanced)
- Per-setting descriptions + safe defaults
- Add/edit/delete multiple Radarr/Sonarr instances
- State viewer (friendly list + raw JSON) + clear/prune
- Run Now button + status (last/next run)

State size control:
- state_retention_days (default 180): prune old entries
- state_pretty (default false): compact JSON by default
"""

import json
import os
import random
import signal
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import Flask, jsonify, request, Response

VERSION = "1.3.0"

CONFIG_FILE = os.getenv("CONFIG_FILE", "/config/nudgarr-config.json")
STATE_FILE = os.getenv("STATE_FILE", "/config/nudgarr-state.json")
PORT = int(os.getenv("PORT", "8085"))

DEFAULT_CONFIG: Dict[str, Any] = {
    "scheduler_enabled": True,        # automatic sweeps on/off (container stays running)
    "run_interval_minutes": 360,
    "dry_run": True,

    "cooldown_hours": 48,
    "sample_mode": "random",           # random | first

    "radarr_max_movies_per_run": 25,
    "sonarr_max_episodes_per_run": 25,

    # Optional Radarr backlog missing nudges (OFF by default)
    "radarr_missing_max": 0,
    "radarr_missing_added_days": 14,

    "batch_size": 20,
    "sleep_seconds": 3,
    "jitter_seconds": 2,

    # State size controls
    "state_retention_days": 180,       # prune entries older than this (0 disables)
    "state_pretty": False,             # compact JSON by default

    "instances": {"radarr": [], "sonarr": []},
}

# -------------------------
# Utilities
# -------------------------

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def parse_iso(s: str) -> Optional[datetime]:
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except Exception:
        return None

def ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)

def load_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        return default

def save_json_atomic(path: str, data: Any, *, pretty: bool) -> None:
    ensure_dir(path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        if pretty:
            json.dump(data, f, indent=2, sort_keys=True)
        else:
            json.dump(data, f, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, path)

def mask_url(url: str) -> str:
    try:
        parts = url.split("://", 1)
        if len(parts) == 2:
            scheme, rest = parts
            host = rest.split("/", 1)[0]
            return f"{scheme}://{host}"
        return url.split("/", 1)[0]
    except Exception:
        return url

def req(session: requests.Session, method: str, url: str, key: str, json_body: Optional[dict] = None, timeout: int = 30):
    headers = {"X-Api-Key": key}
    r = session.request(method, url, headers=headers, json=json_body, timeout=timeout)
    r.raise_for_status()
    if r.text:
        try:
            return r.json()
        except Exception:
            return r.text
    return None

def validate_config(cfg: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errs: List[str] = []    if not isinstance(cfg.get("run_interval_minutes"), int) or cfg["run_interval_minutes"] < 1:
        errs.append("run_interval_minutes must be an int >= 1")
    if cfg.get("sample_mode") not in ("random", "first"):
        errs.append("sample_mode must be 'random' or 'first'")
    for k in ("radarr_max_movies_per_run", "sonarr_max_episodes_per_run", "cooldown_hours", "batch_size", "state_retention_days", "radarr_missing_max", "radarr_missing_added_days"):
        if not isinstance(cfg.get(k), int) or cfg[k] < 0:
            errs.append(f"{k} must be an int >= 0")
    if not isinstance(cfg.get("state_pretty"), bool):
        errs.append("state_pretty must be boolean")
    for k in ("sleep_seconds", "jitter_seconds"):
        try:
            float(cfg.get(k, 0))
        except Exception:
            errs.append(f"{k} must be a number")
    inst = cfg.get("instances", {})
    if not isinstance(inst, dict):
        errs.append("instances must be an object with keys radarr/sonarr")
    else:
        for app in ("radarr", "sonarr"):
            lst = inst.get(app, [])
            if not isinstance(lst, list):
                errs.append(f"instances.{app} must be a list")
            else:
                for i, item in enumerate(lst):
                    if not isinstance(item, dict):
                        errs.append(f"instances.{app}[{i}] must be an object")
                        continue
                    for f in ("name", "url", "key"):
                        if not item.get(f):
                            errs.append(f"instances.{app}[{i}].{f} is required")
    return (len(errs) == 0), errs

def deep_copy(obj: Any) -> Any:
    return json.loads(json.dumps(obj))

def load_or_init_config() -> Dict[str, Any]:
    cfg = load_json(CONFIG_FILE, None)
    if not isinstance(cfg, dict):
        cfg = deep_copy(DEFAULT_CONFIG)
        save_json_atomic(CONFIG_FILE, cfg, pretty=True)
        return cfg

    merged = deep_copy(DEFAULT_CONFIG)
    # merge non-instance keys
    for k, v in cfg.items():
        if k != "instances":
            merged[k] = v
    # merge instances
    merged["instances"]["radarr"] = cfg.get("instances", {}).get("radarr", merged["instances"]["radarr"])
    merged["instances"]["sonarr"] = cfg.get("instances", {}).get("sonarr", merged["instances"]["sonarr"])

    ok, errs = validate_config(merged)
    if not ok:
        print("⚠️ Config validation failed; using defaults for this run:")
        for e in errs:
            print(f"  - {e}")
        return deep_copy(DEFAULT_CONFIG)

    # Normalize & persist
    save_json_atomic(CONFIG_FILE, merged, pretty=True)
    return merged

def state_key(name: str, url: str) -> str:
    return f"{name}|{url.rstrip('/')}"

def load_state() -> Dict[str, Any]:
    st = load_json(STATE_FILE, {})
    return st if isinstance(st, dict) else {}

def ensure_state_structure(state: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    state.setdefault("radarr", {})
    state.setdefault("sonarr", {})
    for inst in cfg.get("instances", {}).get("radarr", []):
        ik = state_key(inst["name"], inst["url"])
        state["radarr"].setdefault(ik, {})
    for inst in cfg.get("instances", {}).get("sonarr", []):
        ik = state_key(inst["name"], inst["url"])
        state["sonarr"].setdefault(ik, {})
    return state

def save_state(state: Dict[str, Any], cfg: Dict[str, Any]) -> None:
    pretty = bool(cfg.get("state_pretty", False))
    save_json_atomic(STATE_FILE, state, pretty=pretty)

def is_allowed_by_cooldown(last_iso: Optional[str], cooldown_hours: int) -> bool:
    if cooldown_hours <= 0:
        return True
    if not last_iso:
        return True
    dt = parse_iso(last_iso)
    if dt is None:
        return True
    return dt < (utcnow() - timedelta(hours=cooldown_hours))

def pick_ids_with_cooldown(ids: List[int], st_bucket: Dict[str, str], prefix: str, cooldown_hours: int, max_per_run: int, sample_mode: str) -> Tuple[List[int], int, int]:
    eligible: List[int] = []
    skipped = 0
    for _id in ids:
        key = f"{prefix}:{_id}"
        last = st_bucket.get(key)
        if is_allowed_by_cooldown(last, cooldown_hours):
            eligible.append(_id)
        else:
            skipped += 1
    if sample_mode == "random":
        random.shuffle(eligible)
    chosen = eligible[:max_per_run] if max_per_run > 0 else []
    return chosen, len(eligible), skipped

def mark_ids_searched(st_bucket: Dict[str, str], prefix: str, ids: List[int]) -> None:
    now_s = iso_z(utcnow())
    for _id in ids:
        st_bucket[f"{prefix}:{_id}"] = now_s

def jitter_sleep(base_s: float, jitter_s: float) -> None:
    delay = base_s + (random.random() * jitter_s if jitter_s > 0 else 0)
    if delay > 0:
        time.sleep(delay)

def prune_state_by_retention(state: Dict[str, Any], retention_days: int) -> int:
    """Remove entries older than retention_days. Returns number removed."""
    if retention_days <= 0:
        return 0
    cutoff = utcnow() - timedelta(days=retention_days)
    removed = 0
    for app in ("radarr", "sonarr"):
        app_obj = state.get(app, {})
        if not isinstance(app_obj, dict):
            continue
        for inst_key, bucket in list(app_obj.items()):
            if not isinstance(bucket, dict):
                continue
            for item_key, ts in list(bucket.items()):
                dt = parse_iso(ts) if isinstance(ts, str) else None
                if dt is not None and dt < cutoff:
                    bucket.pop(item_key, None)
                    removed += 1
    return removed

# -------------------------
# Arr API helpers
# -------------------------

def radarr_get_cutoff_unmet_movie_ids(session: requests.Session, url: str, key: str, page_size: int = 100, max_pages: int = 5) -> List[int]:
    movie_ids: List[int] = []
    for page in range(1, max_pages + 1):
        endpoint = f"{url.rstrip('/')}/api/v3/wanted/cutoff?page={page}&pageSize={page_size}"
        data = req(session, "GET", endpoint, key)
        if not isinstance(data, dict):
            break
        records = data.get("records") or []
        if not records:
            break
        for rec in records:
            mid = rec.get("movieId")
            if isinstance(mid, int):
                movie_ids.append(mid)
    return movie_ids

def radarr_get_missing_movie_ids(session: requests.Session, url: str, key: str, page_size: int = 100, max_pages: int = 5) -> List[Dict[str, Any]]:
    """Returns list of dicts: {movieId:int, added:str|None} from Wanted->Missing."""
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
            mid = rec.get("movieId")
            added = rec.get("added") or rec.get("addedDate") or rec.get("addedUtc")  # best effort across versions
            if isinstance(mid, int):
                out.append({"movieId": mid, "added": added})
    return out


def radarr_search_movies(session: requests.Session, url: str, key: str, movie_ids: List[int], dry_run: bool) -> None:
    if not movie_ids:
        return
    cmd = f"{url.rstrip('/')}/api/v3/command"
    payload = {"name": "MoviesSearch", "movieIds": movie_ids}
    if dry_run:
        print(f"[Radarr] DRY_RUN would search {len(movie_ids)} movie(s)")
    else:
        req(session, "POST", cmd, key, payload)
        print(f"[Radarr] Started MoviesSearch for {len(movie_ids)} movie(s)")

def sonarr_get_cutoff_unmet_episode_ids(session: requests.Session, url: str, key: str, page_size: int = 100, max_pages: int = 5) -> List[int]:
    ep_ids: List[int] = []
    for page in range(1, max_pages + 1):
        endpoint = f"{url.rstrip('/')}/api/v3/wanted/cutoff?page={page}&pageSize={page_size}"
        data = req(session, "GET", endpoint, key)
        if not isinstance(data, dict):
            break
        records = data.get("records") or []
        if not records:
            break
        for rec in records:
            eid = rec.get("episodeId")
            if isinstance(eid, int):
                ep_ids.append(eid)
    return ep_ids

def sonarr_search_episodes(session: requests.Session, url: str, key: str, episode_ids: List[int], dry_run: bool) -> None:
    if not episode_ids:
        return
    cmd = f"{url.rstrip('/')}/api/v3/command"
    payload = {"name": "EpisodeSearch", "episodeIds": episode_ids}
    if dry_run:
        print(f"[Sonarr] DRY_RUN would search {len(episode_ids)} episode(s)")
    else:
        req(session, "POST", cmd, key, payload)
        print(f"[Sonarr] Started EpisodeSearch for {len(episode_ids)} episode(s)")

# -------------------------
# Sweep
# -------------------------

def run_sweep(cfg: Dict[str, Any], state: Dict[str, Any], session: requests.Session) -> Dict[str, Any]:
    dry_run = bool(cfg.get("dry_run", True))
    cooldown_hours = int(cfg.get("cooldown_hours", 48))
    sample_mode = str(cfg.get("sample_mode", "random")).lower()

    radarr_max = int(cfg.get("radarr_max_movies_per_run", 25))
    sonarr_max = int(cfg.get("sonarr_max_episodes_per_run", 25))

    batch_size = max(1, int(cfg.get("batch_size", 20)))
    sleep_seconds = float(cfg.get("sleep_seconds", 3))
    jitter_seconds = float(cfg.get("jitter_seconds", 2))

    retention_days = int(cfg.get("state_retention_days", 180))

    state = ensure_state_structure(state, cfg)
    pruned = prune_state_by_retention(state, retention_days)

    summary = {
        "dry_run": dry_run,
        "pruned_entries": pruned,
        "radarr": [],
        "sonarr": [],
    }

    print(f"Started: {utcnow().isoformat()}  dry_run={dry_run}")

    # RADARR
    for inst in cfg.get("instances", {}).get("radarr", []):
        name, url, key = inst["name"], inst["url"], inst["key"]
        ik = state_key(name, url)
        st_bucket = state.setdefault("radarr", {}).setdefault(ik, {})
        try:
            all_ids = radarr_get_cutoff_unmet_movie_ids(session, url, key)
            chosen, eligible, skipped = pick_ids_with_cooldown(all_ids, st_bucket, "movie", cooldown_hours, radarr_max, sample_mode)
            print(f"[Radarr:{name}] cutoff_unmet_total={len(all_ids)} eligible={eligible} skipped_cooldown={skipped} will_search={len(chosen)} limit={radarr_max}")

            searched = 0
            for i in range(0, len(chosen), batch_size):
                batch = chosen[i:i+batch_size]
                radarr_search_movies(session, url, key, batch, dry_run)
                if not dry_run:
                    mark_ids_searched(st_bucket, "movie", batch)
                searched += len(batch)
                if i + batch_size < len(chosen):
                    jitter_sleep(sleep_seconds, jitter_seconds)

            summary["radarr"].append({
                "name": name, "url": mask_url(url),
                "cutoff_unmet_total": len(all_ids),
                "eligible": eligible, "skipped_cooldown": skipped,
                "will_search": len(chosen), "searched": searched,
                "limit": radarr_max
            })
        
            # Optional: Missing backlog nudges (Radarr only)
            missing_max = int(cfg.get("radarr_missing_max", 0))
            missing_added_days = int(cfg.get("radarr_missing_added_days", 14))
            if missing_max > 0:
                missing_records = radarr_get_missing_movie_ids(session, url, key)
                # Filter: only items added more than N days ago (best-effort if added timestamp missing)
                min_added_dt = utcnow() - timedelta(days=missing_added_days)
                missing_ids: List[int] = []
                for rec in missing_records:
                    mid = rec.get("movieId")
                    added_s = rec.get("added")
                    ok_old = True
                    if isinstance(added_s, str):
                        dt = parse_iso(added_s)
                        if dt is not None:
                            ok_old = dt < min_added_dt
                    # if we can't parse added, treat as old (so it can still be nudged if desired)
                    if ok_old and isinstance(mid, int):
                        missing_ids.append(mid)

                chosen_m, eligible_m, skipped_m = pick_ids_with_cooldown(
                    missing_ids, st_bucket, "missing_movie", cooldown_hours, missing_max, sample_mode
                )
                print(f"[Radarr:{name}] missing_total={len(missing_records)} eligible_missing={eligible_m} skipped_missing_cooldown={skipped_m} will_search_missing={len(chosen_m)} limit_missing={missing_max} older_than_days={missing_added_days}")

                searched_m = 0
                for i in range(0, len(chosen_m), batch_size):
                    batch = chosen_m[i:i+batch_size]
                    radarr_search_movies(session, url, key, batch, dry_run)
                    if not dry_run:
                        mark_ids_searched(st_bucket, "missing_movie", batch)
                    searched_m += len(batch)
                    if i + batch_size < len(chosen_m):
                        jitter_sleep(sleep_seconds, jitter_seconds)

                # record in summary
                summary["radarr"][-1].update({
                    "missing_total": len(missing_records),
                    "eligible_missing": eligible_m,
                    "skipped_missing_cooldown": skipped_m,
                    "will_search_missing": len(chosen_m),
                    "searched_missing": searched_m,
                    "limit_missing": missing_max,
                    "missing_added_days": missing_added_days,
                })
except Exception as e:
            print(f"[Radarr:{name}] ERROR: {e}")
            summary["radarr"].append({"name": name, "url": mask_url(url), "error": str(e)})

    # SONARR
    for inst in cfg.get("instances", {}).get("sonarr", []):
        name, url, key = inst["name"], inst["url"], inst["key"]
        ik = state_key(name, url)
        st_bucket = state.setdefault("sonarr", {}).setdefault(ik, {})
        try:
            all_ids = sonarr_get_cutoff_unmet_episode_ids(session, url, key)
            chosen, eligible, skipped = pick_ids_with_cooldown(all_ids, st_bucket, "episode", cooldown_hours, sonarr_max, sample_mode)
            print(f"[Sonarr:{name}] cutoff_unmet_total={len(all_ids)} eligible={eligible} skipped_cooldown={skipped} will_search={len(chosen)} limit={sonarr_max}")

            searched = 0
            for i in range(0, len(chosen), batch_size):
                batch = chosen[i:i+batch_size]
                sonarr_search_episodes(session, url, key, batch, dry_run)
                if not dry_run:
                    mark_ids_searched(st_bucket, "episode", batch)
                searched += len(batch)
                if i + batch_size < len(chosen):
                    jitter_sleep(sleep_seconds, jitter_seconds)

            summary["sonarr"].append({
                "name": name, "url": mask_url(url),
                "cutoff_unmet_total": len(all_ids),
                "eligible": eligible, "skipped_cooldown": skipped,
                "will_search": len(chosen), "searched": searched,
                "limit": sonarr_max
            })
        except Exception as e:
            print(f"[Sonarr:{name}] ERROR: {e}")
            summary["sonarr"].append({"name": name, "url": mask_url(url), "error": str(e)})

    # Persist state (even on dry run, so pruning/structure changes persist)
    save_state(state, cfg)
    print(f"State saved: {STATE_FILE} (pretty={bool(cfg.get('state_pretty', False))}) pruned={pruned}")

    return summary

# -------------------------
# Web UI
# -------------------------

app = Flask(__name__)

# Silence default Flask request logging (werkzeug)
import logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)


STATUS: Dict[str, Any] = {
    "version": VERSION,
    "last_run_utc": None,
    "next_run_utc": None,
    "last_summary": None,
    "scheduler_running": False,
    "run_in_progress": False,
    "run_requested": False,
    "last_error": None,
}

UI_HTML = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Nudgarr</title>
  <style>
    :root{
      --bg:#0b1220; --card:#0f1a2f; --muted:#9aa5b1; --text:#e6edf3; --line:rgba(255,255,255,.10);
      --ok:#22c55e; --warn:#f59e0b; --bad:#ef4444; --btn:#111827;
    }
    body{margin:0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; background: linear-gradient(180deg,var(--bg), #080d18); color:var(--text);}
    .wrap{max-width:1100px; margin:0 auto; padding:18px;}
    .top{display:flex; gap:12px; align-items:center; justify-content:space-between; flex-wrap:wrap;}
    .brand h1{font-size:20px; margin:0;}
    .brand p{margin:4px 0 0; color:var(--muted); font-size:13px;}
    .pill{display:inline-flex; align-items:center; gap:8px; padding:8px 10px; border:1px solid var(--line); border-radius:999px; background:rgba(255,255,255,.03); font-size:12px; color:var(--muted);}
    .dot{width:8px;height:8px;border-radius:50%;}
    .btn{border:1px solid var(--line); background:rgba(255,255,255,.05); color:var(--text); padding:10px 12px; border-radius:12px; cursor:pointer; font-size:13px;}
    .btn.primary{background:var(--btn);}
    .btn.danger{background:rgba(239,68,68,.14); border-color:rgba(239,68,68,.35);}
    .grid{display:grid; gap:12px;}
    .cards{grid-template-columns: repeat(12, 1fr);}
    .card{grid-column: span 12; border:1px solid var(--line); background:rgba(255,255,255,.03); border-radius:18px; padding:14px;}
    @media(min-width:900px){ .card.half{grid-column: span 6;} }
    .tabs{display:flex; gap:8px; flex-wrap:wrap; margin-top:14px;}
    .tab{padding:9px 12px; border:1px solid var(--line); border-radius:999px; cursor:pointer; font-size:13px; color:var(--muted); background:rgba(255,255,255,.02);}
    .tab.active{color:var(--text); background:rgba(255,255,255,.07);}
    .section{display:none; margin-top:12px;}
    .section.active{display:block;}
    .row{display:flex; gap:10px; flex-wrap:wrap; align-items:center;}
    .field{display:flex; flex-direction:column; gap:6px; min-width:220px; flex:1;}
    label{font-size:12px; color:var(--muted);}
    input,select,textarea{padding:10px 10px; border-radius:12px; border:1px solid var(--line); background:rgba(0,0,0,.25); color:var(--text); outline:none;}
    textarea{min-height:160px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size:12px;}
    .help{font-size:12px; color:var(--muted); line-height:1.35;}
    .hr{height:1px;background:var(--line);margin:14px 0;}
    table{width:100%; border-collapse:collapse; font-size:13px;}
    th,td{border-bottom:1px solid var(--line); padding:10px 8px; text-align:left; color:var(--text);}
    th{color:var(--muted); font-weight:600; font-size:12px;}
    .mono{font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;}
    .kpi{display:flex; gap:10px; flex-wrap:wrap;}
    .kpi .pill{padding:10px 12px;}
    .right{margin-left:auto;}
    .small{font-size:12px;color:var(--muted);}
    .hide{display:none;}
  </style>
</head>
<body>
<div class="wrap">

  <div class="top">
    <div class="brand">
      <h1>Nudgarr <span class="small">v<span id="ver"></span></span></h1>
      <p>Because RSS sometimes needs a nudge.</p>
    </div>

    <div class="row">
      <div class="pill" id="pill-live"><span class="dot" id="dot-live"></span><span id="txt-live">Loading…</span></div>
      <div class="pill"><span class="dot" style="background:rgba(255,255,255,.35)"></span><span>Last: <span id="lastRun">—</span></span></div>
      <div class="pill"><span class="dot" style="background:rgba(255,255,255,.35)"></span><span>Next: <span id="nextRun">—</span></span></div>
      <button class="btn primary" onclick="runNow()">Run now</button>
    </div>
  </div>

  <div class="tabs">
    <div class="tab active" data-tab="instances" onclick="showTab('instances')">Instances</div>
    <div class="tab" data-tab="settings" onclick="showTab('settings')">Settings</div>
    <div class="tab" data-tab="state" onclick="showTab('state')">State</div>
    <div class="tab" data-tab="advanced" onclick="showTab('advanced')">Advanced</div>
  </div>

  <div class="section active" id="tab-instances">
    <div class="grid cards">
      <div class="card half">
        <div class="row">
          <h3 style="margin:0">Radarr instances</h3>
          <div class="right"></div>
          <button class="btn" onclick="addInstance('radarr')">+ Add</button>
        </div>
        <p class="help">Add one or more Radarr instances. Nudgarr will only search up to your per-run cap.</p>
        <div id="radarrList"></div>
      </div>

      <div class="card half">
        <div class="row">
          <h3 style="margin:0">Sonarr instances</h3>
          <div class="right"></div>
          <button class="btn" onclick="addInstance('sonarr')">+ Add</button>
        </div>
        <p class="help">Add one or more Sonarr instances. Nudgarr targets <span class="mono">Wanted → Cutoff Unmet</span> and respects cooldown.</p>
        <div id="sonarrList"></div>
      </div>

      <div class="card">
        <div class="row">
          <button class="btn primary" onclick="saveAll()">Save changes</button>
          <button class="btn" onclick="testConnections()">Test connections</button>
          <span class="small" id="saveMsg"></span>
        </div>
        <pre id="testOut" class="mono" style="white-space:pre-wrap; margin:12px 0 0; background:rgba(0,0,0,.25); border-radius:14px; padding:12px; border:1px solid var(--line);">No tests yet.</pre>
      </div>
    </div>
  </div>

  <div class="section" id="tab-settings">
    <div class="grid cards">
      <div class="card half">
        <h3 style="margin:0 0 8px">Run</h3>
        <div class="row">
          <div class="field">
            <label>Automatic sweeps</label>
            <select id="scheduler_enabled" onchange="syncSchedulerUi()">
              <option value="true">enabled</option>
              <option value="false">manual only</option>
            </select>
            <div class="help">When set to <b>manual only</b>, Nudgarr stays running for the UI but will only sweep when you click <b>Run now</b>.</div>
          </div>
          <div class="field">
            <label>Run interval (minutes)</label>
            <input id="run_interval_minutes" type="number" min="1"/>
            <div class="help">How often Nudgarr runs a sweep when automatic sweeps are enabled.</div>
          </div>
        </div>

        <div class="hr"></div>

        <h3 style="margin:0 0 8px">Politeness</h3>
        <div class="row">
          <div class="field">
            <label>Cooldown hours</label>
            <input id="cooldown_hours" type="number" min="0"/>
            <div class="help">How long before the same movie/episode can be searched again. (0 disables cooldown.)</div>
          </div>
          <div class="field">
            <label>Sample mode</label>
            <select id="sample_mode">
              <option value="random">random</option>
              <option value="first">first</option>
            </select>
            <div class="help"><b>random</b> spreads searches across your library. <b>first</b> is predictable.</div>
          </div>
        </div>
      </div>

      <div class="card half">
        <h3 style="margin:0 0 8px">Caps</h3>
        <div class="row">
          <div class="field">
            <label>Radarr max movies per run</label>
            <input id="radarr_max_movies_per_run" type="number" min="0"/>
            <div class="help">Total Radarr upgrade searches per sweep <b>per instance</b>. If you have multiple Radarr instances, each can search up to this limit. (0 disables Radarr upgrades.)</div>
          </div>
          <div class="field">
            <label>Sonarr max episodes per run</label>
            <input id="sonarr_max_episodes_per_run" type="number" min="0"/>
            <div class="help">Total Sonarr upgrade searches per sweep <b>per instance</b>. If you have multiple Sonarr instances, each can search up to this limit. (0 disables Sonarr upgrades.)</div>
          </div>
        </div>

        <div class="hr"></div>

        <h3 style="margin:0 0 8px">Backlog nudges (optional)</h3>
        <div class="row">
          <div class="field">
            <label>Radarr missing max</label>
            <input id="radarr_missing_max" type="number" min="0"/>
            <div class="help">Optional: nudge <b>missing</b> movies for Radarr. Applies <b>per instance</b>. Set to 0 to disable (recommended default).</div>
          </div>
          <div class="field">
            <label>Radarr missing added days</label>
            <input id="radarr_missing_added_days" type="number" min="0"/>
            <div class="help">Only nudge missing movies that were added more than this many days ago (helps avoid interfering with normal RSS behavior).</div>
          </div>
        </div>

        <div class="hr"></div>

        <h3 style="margin:0 0 8px">Throttling</h3>
        <div class="row">
          <div class="field">
            <label>Batch size</label>
            <input id="batch_size" type="number" min="1"/>
            <div class="help">How many IDs are sent per Arr command. Helps avoid large bursts.</div>
          </div>
          <div class="field">
            <label>Sleep seconds (between batches)</label>
            <input id="sleep_seconds" type="number" min="0" step="0.1"/>
            <div class="help">Base pause between batches.</div>
          </div>
          <div class="field">
            <label>Jitter seconds</label>
            <input id="jitter_seconds" type="number" min="0" step="0.1"/>
            <div class="help">Adds a small random delay to avoid spikes.</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="row">
          <div class="pill"><span class="dot" id="dot-dry"></span><span id="txt-dry">DRY_RUN: —</span></div>
          <button class="btn" onclick="toggleDryRun()">Toggle DRY_RUN</button>
          <button class="btn primary" onclick="saveSettings()">Save settings</button>
          <span class="small" id="setMsg"></span>
        </div>
        <p class="help" style="margin:10px 0 0">Tip: Leave DRY_RUN on until connections test cleanly.</p>
      </div>
    </div>
  </div>

  <div class="section" id="tab-state">
    <div class="grid cards">
      <div class="card">
        <div class="kpi" id="kpis"></div>
        <div class="row" style="margin-top:10px">
          <button class="btn" onclick="refreshState()">Refresh</button>
          <button class="btn" onclick="pruneState()">Prune expired</button>
          <button class="btn danger" onclick="clearState()">Clear state</button>
          <div class="right"></div>
          <input id="stateSearch" placeholder="Filter (e.g. movie:123 or episode:456)"/>
        </div>
        <div class="hr"></div>

        <div class="row">
          <div class="field" style="min-width:260px; max-width:360px;">
            <label>View</label>
            <select id="stateView" onchange="refreshState()">
              <option value="radarr">Radarr</option>
              <option value="sonarr">Sonarr</option>
            </select>
          </div>
          <div class="field" style="min-width:260px; max-width:520px;">
            <label>Instance</label>
            <select id="stateInstance" onchange="refreshState()"></select>
          </div>
          <div class="field" style="min-width:200px; max-width:260px;">
            <label>Page size</label>
            <select id="stateLimit" onchange="refreshState()">
              <option>100</option><option>250</option><option>500</option><option>1000</option>
            </select>
          </div>
          <div class="right"></div>
        </div>

        <div id="stateTableWrap" style="margin-top:10px"></div>
        <div class="row" style="margin-top:10px">
          <button class="btn" onclick="prevPage()">Prev</button>
          <button class="btn" onclick="nextPage()">Next</button>
          <span class="small" id="pageInfo"></span>
        </div>
      </div>
    </div>
  </div>

  <div class="section" id="tab-advanced">
    <div class="grid cards">
      <div class="card half">
        <h3 style="margin:0 0 8px">Files</h3>
        <p class="help">Config and state are stored under <span class="mono">/config</span> (map this to Unraid appdata).</p>
        <div class="row">
          <button class="btn" onclick="downloadFile('config')">Download config</button>
          <button class="btn" onclick="downloadFile('state')">Download state</button>
        </div>
        <div class="hr"></div>
        <h3 style="margin:0 0 8px">State size</h3>
        <div class="row">
          <div class="field">
            <label>Retention days</label>
            <input id="state_retention_days" type="number" min="0"/>
            <div class="help">Deletes state entries older than this many days. (0 disables retention pruning.)</div>
          </div>
          <div class="field">
            <label>State format</label>
            <select id="state_pretty">
              <option value="false">compact (recommended)</option>
              <option value="true">pretty</option>
            </select>
            <div class="help">Compact is smaller; pretty is easier to read.</div>
          </div>
        </div>
        <div class="row" style="margin-top:10px">
          <button class="btn primary" onclick="saveAdvanced()">Save</button>
          <span class="small" id="advMsg"></span>
        </div>
      </div>

      <div class="card half">
        <h3 style="margin:0 0 8px">Danger zone</h3>
        <p class="help">These actions are irreversible.</p>
        <div class="row">
          <button class="btn danger" onclick="resetConfig()">Reset config to defaults</button>
          <button class="btn danger" onclick="clearState()">Clear state</button>
        </div>
        <div class="hr"></div>
        <h3 style="margin:0 0 8px">Diagnostics</h3>
        <div class="row">
          <button class="btn" onclick="refreshStatus()">Refresh status</button>
        </div>

        <div class="row" style="margin-top:10px">
          <button class="btn" onclick="toggleRawState()">View raw state</button>
        </div>
        <div id="rawStateWrap" class="hide" style="margin-top:10px">
          <textarea id="rawState" readonly></textarea>
        </div>
        <pre id="diag" class="mono" style="white-space:pre-wrap; margin:12px 0 0; background:rgba(0,0,0,.25); border-radius:14px; padding:12px; border:1px solid var(--line);">—</pre>
      </div>
    </div>
  </div>

</div>

<script>
let CFG = null;
let PAGE = 0;

function showTab(name){
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  if(name === 'state') refreshState();
  if(name === 'advanced') fillAdvanced();
}

function el(id){ return document.getElementById(id); }

function setLivePill(dry){
  const dot = el('dot-live');
  const txt = el('txt-live');
  if(dry){
    dot.style.background = 'var(--warn)';
    txt.textContent = 'DRY_RUN (safe)';
  }else{
    dot.style.background = 'var(--ok)';
    txt.textContent = 'LIVE';
  }
  el('dot-dry').style.background = dry ? 'var(--warn)' : 'var(--ok)';
  el('txt-dry').textContent = 'DRY_RUN: ' + (dry ? 'true' : 'false');
}

function fmtTime(s){
  if(!s) return '—';
  try { return new Date(s).toLocaleString(); } catch(e){ return s; }
}

async function api(path, opts){
  const r = await fetch(path, opts || {});
  const ct = r.headers.get('content-type') || '';
  const data = ct.includes('application/json') ? await r.json() : await r.text();
  if(!r.ok){
    const msg = (typeof data === 'string') ? data : JSON.stringify(data);
    throw new Error(msg);
  }
  return data;
}

async function loadAll(){
  CFG = await api('/api/config');
  const st = await api('/api/status');
  el('ver').textContent = st.version;
  el('lastRun').textContent = fmtTime(st.last_run_utc);
  el('nextRun').textContent = (CFG && CFG.scheduler_enabled) ? fmtTime(st.next_run_utc) : 'Manual mode';
  setLivePill(CFG.dry_run);

  renderInstances('radarr');
  renderInstances('sonarr');
  fillSettings();
  fillAdvanced();
  el('diag').textContent = JSON.stringify(st, null, 2);
}

function renderInstances(kind){
  const box = el(kind + 'List');
  const list = (CFG.instances && CFG.instances[kind]) ? CFG.instances[kind] : [];
  if(!list.length){
    box.innerHTML = '<p class="help">No instances yet. Click <b>+ Add</b>.</p>';
    return;
  }
  box.innerHTML = list.map((it, idx) => `
    <div class="card" style="padding:12px; margin-top:10px">
      <div class="row">
        <div style="font-weight:700">${escapeHtml(it.name || '(unnamed)')}</div>
        <div class="right"></div>
        <button class="btn" onclick="editInstance('${kind}', ${idx})">Edit</button>
        <button class="btn danger" onclick="deleteInstance('${kind}', ${idx})">Delete</button>
      </div>
      <div class="small" style="margin-top:6px">
        <div><span class="mono">${escapeHtml(it.url || '')}</span></div>
        <div>Key: <span class="mono">${(it.key ? '••••••••' : '')}</span></div>
      </div>
    </div>
  `).join('');
}

function escapeHtml(s){
  return (s||'').toString().replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'","&#39;");
}

function addInstance(kind){
  CFG.instances = CFG.instances || {radarr:[], sonarr:[]};
  CFG.instances[kind].push({name: kind, url:'http://', key:''});
  renderInstances(kind);
  el('saveMsg').textContent = 'Added. Click Save changes when ready.';
}

function editInstance(kind, idx){
  const it = CFG.instances[kind][idx];
  const name = prompt('Instance name', it.name || '');
  if(name === null) return;
  const url = prompt('Instance URL (e.g. http://192.168.1.10:7878)', it.url || '');
  if(url === null) return;
  const key = prompt('API key (will be stored in /config)', it.key || '');
  if(key === null) return;

  it.name = name.trim();
  it.url = url.trim();
  it.key = key.trim();
  renderInstances(kind);
  el('saveMsg').textContent = 'Edited. Click Save changes.';
}

function deleteInstance(kind, idx){
  if(!confirm('Delete this instance?')) return;
  CFG.instances[kind].splice(idx, 1);
  renderInstances(kind);
  el('saveMsg').textContent = 'Deleted. Click Save changes.';
}


function syncSchedulerUi(){
  const enabled = (el('scheduler_enabled').value === 'true');
  el('run_interval_minutes').disabled = !enabled;
  el('run_interval_minutes').style.opacity = enabled ? '1' : '0.6';
}

function fillSettings(){
  const set = (id, v) => { el(id).value = v; };
  set('scheduler_enabled', String(!!CFG.scheduler_enabled));
  set('run_interval_minutes', CFG.run_interval_minutes);
  set('cooldown_hours', CFG.cooldown_hours);
  set('sample_mode', CFG.sample_mode);
  set('radarr_max_movies_per_run', CFG.radarr_max_movies_per_run);
  set('sonarr_max_episodes_per_run', CFG.sonarr_max_episodes_per_run);
  set('batch_size', CFG.batch_size);
  set('sleep_seconds', CFG.sleep_seconds);
  set('jitter_seconds', CFG.jitter_seconds);
  syncSchedulerUi();
}

async function saveAll(){
  try{
    await api('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(CFG)});
    el('saveMsg').textContent = 'Saved.';
    await loadAll();
  }catch(e){
    el('saveMsg').textContent = 'Save failed: ' + e.message;
  }
}

async function saveSettings(){
  try{
    // pull values from inputs into CFG
    CFG.scheduler_enabled = (el('scheduler_enabled').value === 'true');
    CFG.run_interval_minutes = parseInt(el('run_interval_minutes').value || '360', 10);
    CFG.cooldown_hours = parseInt(el('cooldown_hours').value || '48', 10);
    CFG.sample_mode = el('sample_mode').value;
    CFG.radarr_max_movies_per_run = parseInt(el('radarr_max_movies_per_run').value || '25', 10);
    CFG.sonarr_max_episodes_per_run = parseInt(el('sonarr_max_episodes_per_run').value || '25', 10);
    CFG.radarr_missing_max = parseInt(el('radarr_missing_max').value || '0', 10);
    CFG.radarr_missing_added_days = parseInt(el('radarr_missing_added_days').value || '14', 10);
    CFG.batch_size = parseInt(el('batch_size').value || '20', 10);
    CFG.sleep_seconds = parseFloat(el('sleep_seconds').value || '3');
    CFG.jitter_seconds = parseFloat(el('jitter_seconds').value || '2');
    await api('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(CFG)});
    el('setMsg').textContent = 'Saved.';
    await loadAll();
  }catch(e){
    el('setMsg').textContent = 'Save failed: ' + e.message;
  }
}

async function fillAdvanced(){
  el('state_retention_days').value = CFG.state_retention_days;
  el('state_pretty').value = String(!!CFG.state_pretty);
}

async function saveAdvanced(){
  try{
    CFG.state_retention_days = parseInt(el('state_retention_days').value || '180', 10);
    CFG.state_pretty = (el('state_pretty').value === 'true');
    await api('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(CFG)});
    el('advMsg').textContent = 'Saved.';
    await loadAll();
  }catch(e){
    el('advMsg').textContent = 'Save failed: ' + e.message;
  }
}

async function toggleDryRun(){
  try{
    const out = await api('/api/toggle-dry-run', {method:'POST'});
    el('setMsg').textContent = 'DRY_RUN now ' + out.dry_run;
    await loadAll();
  }catch(e){
    el('setMsg').textContent = 'Failed: ' + e.message;
  }
}

async function testConnections(){
  try{
    const out = await api('/api/test', {method:'POST'});
    el('testOut').textContent = JSON.stringify(out, null, 2);
  }catch(e){
    el('testOut').textContent = 'Test failed: ' + e.message;
  }
}

async function runNow(){
  try{
    await api('/api/run-now', {method:'POST'});
    await refreshStatus();
    alert('Run requested. Check logs for progress.');
  }catch(e){
    alert('Run request failed: ' + e.message);
  }
}

async function refreshStatus(){
  const st = await api('/api/status');
  el('ver').textContent = st.version;
  el('lastRun').textContent = fmtTime(st.last_run_utc);
  el('nextRun').textContent = (CFG && CFG.scheduler_enabled) ? fmtTime(st.next_run_utc) : 'Manual mode';
  el('diag').textContent = JSON.stringify(st, null, 2);
}

function toggleRaw(){
  RAW = !RAW;
    refreshState();
}

async function refreshState(){
  try{
    const sum = await api('/api/state/summary');
    // KPIs
    el('kpis').innerHTML = `
      <div class="pill"><span class="dot" style="background:rgba(255,255,255,.35)"></span><span>File: ${sum.file_size_human}</span></div>
      <div class="pill"><span class="dot" style="background:rgba(255,255,255,.35)"></span><span>Radarr tracked: ${sum.radarr_entries}</span></div>
      <div class="pill"><span class="dot" style="background:rgba(255,255,255,.35)"></span><span>Sonarr tracked: ${sum.sonarr_entries}</span></div>
      <div class="pill"><span class="dot" style="background:rgba(255,255,255,.35)"></span><span>Retention: ${sum.retention_days} day(s)</span></div>
    `;

    // Instances dropdown
    const view = el('stateView').value;
    const insts = sum.instances[view] || [];
    const sel = el('stateInstance');
    const prev = sel.value;
    sel.innerHTML = insts.map(x => `<option value="${escapeHtml(x)}">${escapeHtml(x)}</option>`).join('');
    if(insts.includes(prev)) sel.value = prev;
    if(!sel.value && insts.length) sel.value = insts[0];

    const q = el('stateSearch').value || '';
    const limit = parseInt(el('stateLimit').value || '250', 10);
    const inst = sel.value || '';
    const items = await api(`/api/state/items?app=${encodeURIComponent(view)}&instance=${encodeURIComponent(inst)}&offset=${PAGE*limit}&limit=${limit}&q=${encodeURIComponent(q)}`);

    el('pageInfo').textContent = `Page ${PAGE+1} • Showing ${items.items.length} of ${items.total} • Instance: ${inst || '—'}`;

    // table
    const rows = items.items.map(it => {
      const ts = it.last_searched || '';
      const eligible = it.eligible_again || '';
      return `<tr><td class="mono">${escapeHtml(it.key)}</td><td>${escapeHtml(ts)}</td><td>${escapeHtml(eligible)}</td></tr>`;
    }).join('');
    el('stateTableWrap').innerHTML = `
      <table>
        <thead><tr><th>Key</th><th>Last searched (UTC)</th><th>Eligible again (UTC)</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="3" class="small">No items.</td></tr>'}</tbody>
      </table>
    `;

  }catch(e){
    el('stateTableWrap').innerHTML = `<p class="help">Failed to load state: ${escapeHtml(e.message)}</p>`;
  }
}

function prevPage(){ if(PAGE>0){ PAGE--; refreshState(); } }
function nextPage(){ PAGE++; refreshState(); }

el('stateSearch').addEventListener('input', () => { PAGE=0; refreshState(); });

async function pruneState(){
  if(!confirm('Prune expired state entries now?')) return;
  const out = await api('/api/state/prune', {method:'POST'});
  alert('Pruned ' + out.removed + ' entries.');
  PAGE=0; refreshState();
}

async function clearState(){
  if(!confirm('Clear state? This removes cooldown history.')) return;
  const out = await api('/api/state/clear', {method:'POST'});
  alert('State cleared.');
  PAGE=0; refreshState();
}

async function resetConfig(){
  if(!confirm('Reset config to defaults?')) return;
  await api('/api/config/reset', {method:'POST'});
  alert('Config reset.');
  await loadAll();
}

async function downloadFile(which){
  const a = document.createElement('a');
  a.href = which === 'config' ? '/api/file/config' : '/api/file/state';
  a.download = which === 'config' ? 'nudgarr-config.json' : 'nudgarr-state.json';
  document.body.appendChild(a);
  a.click();
  a.remove();
}


async function toggleRawState(){
  const wrap = el('rawStateWrap');
  const opening = wrap.classList.contains('hide');
  wrap.classList.toggle('hide');
  if(opening){
    try{
      const raw = await api('/api/state/raw');
      el('rawState').value = JSON.stringify(raw, null, 2);
    }catch(e){
      el('rawState').value = 'Failed to load raw state: ' + e.message;
    }
  }
}

loadAll();
setInterval(refreshStatus, 5000);
</script>
</body>
</html>
"""

@app.get("/")
def index():
    return Response(UI_HTML, mimetype="text/html")

@app.get("/api/status")
def api_status():
    return jsonify(STATUS)

@app.get("/api/config")
def api_get_config():
    return jsonify(load_or_init_config())

@app.post("/api/config")
def api_set_config():
    cfg = request.get_json(force=True, silent=True)
    if not isinstance(cfg, dict):
        return jsonify({"ok": False, "error": "Body must be JSON object"}), 400
    ok, errs = validate_config(cfg)
    if not ok:
        return jsonify({"ok": False, "errors": errs}), 400
    save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    return jsonify({"ok": True, "message": "Config saved", "config_file": CONFIG_FILE})

@app.post("/api/config/reset")
def api_reset_config():
    cfg = deep_copy(DEFAULT_CONFIG)
    save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    return jsonify({"ok": True})

@app.post("/api/toggle-dry-run")
def api_toggle_dryrun():
    cfg = load_or_init_config()
    cfg["dry_run"] = not bool(cfg.get("dry_run", True))
    save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    return jsonify({"ok": True, "dry_run": cfg["dry_run"]})

@app.post("/api/test")
def api_test():
    cfg = load_or_init_config()
    session = requests.Session()
    results = {"radarr": [], "sonarr": []}

    for inst in cfg.get("instances", {}).get("radarr", []):
        try:
            url = f"{inst['url'].rstrip('/')}/api/v3/system/status"
            data = req(session, "GET", url, inst["key"])
            results["radarr"].append({"name": inst["name"], "url": mask_url(inst["url"]), "ok": True, "version": data.get("version") if isinstance(data, dict) else None})
        except Exception as e:
            results["radarr"].append({"name": inst.get("name"), "url": mask_url(inst.get("url","")), "ok": False, "error": str(e)})

    for inst in cfg.get("instances", {}).get("sonarr", []):
        try:
            url = f"{inst['url'].rstrip('/')}/api/v3/system/status"
            data = req(session, "GET", url, inst["key"])
            results["sonarr"].append({"name": inst["name"], "url": mask_url(inst["url"]), "ok": True, "version": data.get("version") if isinstance(data, dict) else None})
        except Exception as e:
            results["sonarr"].append({"name": inst.get("name"), "url": mask_url(inst.get("url","")), "ok": False, "error": str(e)})

    return jsonify({"ok": True, "results": results})

# State endpoints
def _file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except Exception:
        return 0

def _human_bytes(n: int) -> str:
    for unit in ["B","KB","MB","GB","TB"]:
        if n < 1024:
            return f"{n:.0f} {unit}" if unit=="B" else f"{n/1:.0f} {unit}" if unit=="KB" else f"{n/1024/1024:.1f} MB" if unit=="MB" else f"{n/1024/1024/1024:.1f} GB"
        n /= 1024
    return f"{n:.1f} PB"

@app.get("/api/state/summary")
def api_state_summary():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    # Count entries
    radarr_entries = 0
    sonarr_entries = 0
    instances = {"radarr": [], "sonarr": []}
    for app in ("radarr", "sonarr"):
        app_obj = st.get(app, {})
        if isinstance(app_obj, dict):
            instances[app] = sorted(list(app_obj.keys()))
            for _, bucket in app_obj.items():
                if isinstance(bucket, dict):
                    if app == "radarr":
                        radarr_entries += len(bucket)
                    else:
                        sonarr_entries += len(bucket)

    size = _file_size(STATE_FILE)
    return jsonify({
        "file_size_bytes": size,
        "file_size_human": _human_bytes(size),
        "radarr_entries": radarr_entries,
        "sonarr_entries": sonarr_entries,
        "instances": instances,
        "retention_days": int(cfg.get("state_retention_days", 180)),
    })

@app.get("/api/state/raw")
def api_state_raw():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    return jsonify(st)

@app.get("/api/state/items")
def api_state_items():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    app_name = request.args.get("app", "radarr")
    inst = request.args.get("instance", "")
    q = (request.args.get("q") or "").strip().lower()
    offset = int(request.args.get("offset", "0"))
    limit = int(request.args.get("limit", "250"))
    cooldown_hours = int(cfg.get("cooldown_hours", 48))

    app_obj = st.get(app_name, {})
    bucket = app_obj.get(inst, {}) if isinstance(app_obj, dict) else {}
    if not isinstance(bucket, dict):
        bucket = {}

    items = []
    for k, ts in bucket.items():
        if not isinstance(k, str) or not isinstance(ts, str):
            continue
        if q and (q not in k.lower()):
            continue
        # eligible again time
        dt = parse_iso(ts)
        eligible = ""
        if dt is not None:
            eligible_dt = dt + timedelta(hours=cooldown_hours)
            eligible = iso_z(eligible_dt)
        items.append({"key": k, "last_searched": ts, "eligible_again": eligible})

    # newest first
    items.sort(key=lambda x: x.get("last_searched",""), reverse=True)
    total = len(items)
    items = items[offset: offset+limit]
    return jsonify({"total": total, "items": items})

@app.post("/api/state/prune")
def api_state_prune():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    removed = prune_state_by_retention(st, int(cfg.get("state_retention_days", 180)))
    save_state(st, cfg)
    return jsonify({"ok": True, "removed": removed})

@app.post("/api/state/clear")
def api_state_clear():
    cfg = load_or_init_config()
    st = {"radarr": {}, "sonarr": {}}
    st = ensure_state_structure(st, cfg)
    save_state(st, cfg)
    return jsonify({"ok": True})

# File download endpoints
@app.get("/api/file/config")
def api_file_config():
    cfg = load_or_init_config()
    return Response(json.dumps(cfg, indent=2), mimetype="application/json")

@app.get("/api/file/state")
def api_file_state():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    pretty = True
    return Response(json.dumps(st, indent=2 if pretty else None), mimetype="application/json")

# Run-now endpoint
RUN_LOCK = threading.Lock()

@app.post("/api/run-now")
def api_run_now():
    with RUN_LOCK:
        STATUS["run_requested"] = True
    return jsonify({"ok": True})

# -------------------------
# Scheduler / Service runner
# -------------------------

def print_banner(cfg: Dict[str, Any]) -> None:
    print("")
    print("====================================")
    print(f" Nudgarr v{VERSION}")
    print(" Because RSS sometimes needs a nudge.")
    print("====================================")
    print(f"Config: {CONFIG_FILE}")
    print(f"State:  {STATE_FILE}")
    print(f"UI:     http://<host>:{PORT}/")
    print("")
    print(f"Scheduler: {'enabled' if cfg.get('scheduler_enabled') else 'manual'}  Interval: {cfg.get('run_interval_minutes')} minute(s)  DRY_RUN: {cfg.get('dry_run')}")
    print("")

def start_ui_server() -> None:
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

def scheduler_loop(stop_flag: Dict[str, bool]) -> None:
    STATUS["scheduler_running"] = True
    session = requests.Session()
    cycle = 0

    while not stop_flag["stop"]:
        cfg = load_or_init_config()
        # Ensure state file exists/structured even before first run
        st = ensure_state_structure(load_state(), cfg)
        save_state(st, cfg)

        now = utcnow()
        interval_min = int(cfg.get("run_interval_minutes", 360))
        scheduler_enabled = bool(cfg.get("scheduler_enabled", True))
        next_run = now + timedelta(minutes=interval_min)
        STATUS["next_run_utc"] = iso_z(next_run) if scheduler_enabled else None

        scheduler_enabled = bool(cfg.get("scheduler_enabled", True))
        # If scheduler is enabled: run on startup and then on interval.
        # If disabled: only run when explicitly requested (Run now).
        should_run = (scheduler_enabled and cycle == 0)


        with RUN_LOCK:
            if STATUS.get("run_requested"):
                should_run = True
                STATUS["run_requested"] = False

        if should_run:
            cycle += 1
            STATUS["run_in_progress"] = True
            try:
                print(f"--- Sweep Cycle #{cycle} ---")
                summary = run_sweep(cfg, st, session)
                STATUS["last_summary"] = summary
                STATUS["last_run_utc"] = iso_z(utcnow())
                STATUS["last_error"] = None
            except Exception as e:
                STATUS["last_error"] = str(e)
                print(f"ERROR (sweep): {e}")
            finally:
                STATUS["run_in_progress"] = False

        if stop_flag["stop"]:
            break

        # sleep until next run (when scheduler enabled), but check stop/request once a second.
        # In manual mode (scheduler disabled), we just wait for a run request.
        sleep_seconds = interval_min * 60 if scheduler_enabled else 365 * 24 * 60 * 60
        for _ in range(sleep_seconds):
            if stop_flag["stop"]:
                break
            with RUN_LOCK:
                if STATUS.get("run_requested"):
                    break
            time.sleep(1)

    STATUS["scheduler_running"] = False

def main() -> None:
    stop_flag = {"stop": False}

    def handle_signal(signum, frame):
        print("\nShutdown signal received. Stopping…")
        stop_flag["stop"] = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    cfg = load_or_init_config()
    print_banner(cfg)

    # Start UI
    threading.Thread(target=start_ui_server, daemon=True).start()

    # Run scheduler loop in main thread
    scheduler_loop(stop_flag)

    print("Nudgarr exiting.")

if __name__ == "__main__":
    main()
