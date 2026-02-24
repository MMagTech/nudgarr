#!/usr/bin/env python3
"""Nudgarr v1.1.0 — Because RSS sometimes needs a nudge.

Adds:
- Caps per run for BOTH Radarr (movies) and Sonarr (episodes)
- Persistent JSON state DB under /config to avoid re-searching too often (cooldown)
- Minimal web UI to edit /config/nudgarr-config.json and test connectivity
- Loop mode (service) + once mode
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

VERSION = "1.1.0"

CONFIG_FILE = os.getenv("CONFIG_FILE", "/config/nudgarr-config.json")
STATE_FILE = os.getenv("STATE_FILE", "/config/nudgarr-state.json")
PORT = int(os.getenv("PORT", "8085"))

DEFAULT_CONFIG: Dict[str, Any] = {
    "run_mode": "loop",
    "run_interval_minutes": 360,
    "dry_run": True,
    "cooldown_hours": 48,
    "sample_mode": "random",  # random | first
    "radarr_max_movies_per_run": 25,
    "sonarr_max_episodes_per_run": 25,
    "batch_size": 20,
    "sleep_seconds": 3,
    "jitter_seconds": 2,
    "instances": {"radarr": [], "sonarr": []},
}

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

def save_json_atomic(path: str, data: Any) -> None:
    ensure_dir(path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
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
    errs: List[str] = []
    if cfg.get("run_mode") not in ("once", "loop"):
        errs.append("run_mode must be 'once' or 'loop'")
    if not isinstance(cfg.get("run_interval_minutes"), int) or cfg["run_interval_minutes"] < 1:
        errs.append("run_interval_minutes must be an int >= 1")
    if cfg.get("sample_mode") not in ("random", "first"):
        errs.append("sample_mode must be 'random' or 'first'")
    for k in ("radarr_max_movies_per_run", "sonarr_max_episodes_per_run", "cooldown_hours", "batch_size"):
        if not isinstance(cfg.get(k), int) or cfg[k] < 0:
            errs.append(f"{k} must be an int >= 0")
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

def load_or_init_config() -> Dict[str, Any]:
    cfg = load_json(CONFIG_FILE, None)
    if not isinstance(cfg, dict):
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        save_json_atomic(CONFIG_FILE, cfg)
        return cfg

    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    for k, v in cfg.items():
        if k != "instances":
            merged[k] = v
    merged["instances"]["radarr"] = cfg.get("instances", {}).get("radarr", merged["instances"]["radarr"])
    merged["instances"]["sonarr"] = cfg.get("instances", {}).get("sonarr", merged["instances"]["sonarr"])

    ok, errs = validate_config(merged)
    if not ok:
        print("⚠️ Config validation failed; using defaults for this run:")
        for e in errs:
            print(f"  - {e}")
        return json.loads(json.dumps(DEFAULT_CONFIG))

    save_json_atomic(CONFIG_FILE, merged)
    return merged

def load_state() -> Dict[str, Any]:
    st = load_json(STATE_FILE, {})
    return st if isinstance(st, dict) else {}

def save_state(state: Dict[str, Any]) -> None:
    save_json_atomic(STATE_FILE, state)

def state_key(name: str, url: str) -> str:
    return f"{name}|{url.rstrip('/')}"

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

def run_sweep(cfg: Dict[str, Any], state: Dict[str, Any], session: requests.Session) -> None:
    dry_run = bool(cfg.get("dry_run", True))
    cooldown_hours = int(cfg.get("cooldown_hours", 48))
    sample_mode = str(cfg.get("sample_mode", "random")).lower()

    radarr_max = int(cfg.get("radarr_max_movies_per_run", 25))
    sonarr_max = int(cfg.get("sonarr_max_episodes_per_run", 25))

    batch_size = max(1, int(cfg.get("batch_size", 20)))
    sleep_seconds = float(cfg.get("sleep_seconds", 3))
    jitter_seconds = float(cfg.get("jitter_seconds", 2))

    print(f"Started: {utcnow().isoformat()}  dry_run={dry_run}")

    for inst in cfg.get("instances", {}).get("radarr", []):
        name, url, key = inst["name"], inst["url"], inst["key"]
        ik = state_key(name, url)
        st_bucket = state.setdefault("radarr", {}).setdefault(ik, {})
        try:
            all_ids = radarr_get_cutoff_unmet_movie_ids(session, url, key)
            chosen, eligible, skipped = pick_ids_with_cooldown(all_ids, st_bucket, "movie", cooldown_hours, radarr_max, sample_mode)
            print(f"[Radarr:{name}] cutoff_unmet_total={len(all_ids)} eligible={eligible} skipped_cooldown={skipped} will_search={len(chosen)} limit={radarr_max}")
            for i in range(0, len(chosen), batch_size):
                batch = chosen[i:i+batch_size]
                radarr_search_movies(session, url, key, batch, dry_run)
                if not dry_run:
                    mark_ids_searched(st_bucket, "movie", batch)
                if i + batch_size < len(chosen):
                    jitter_sleep(sleep_seconds, jitter_seconds)
        except Exception as e:
            print(f"[Radarr:{name}] ERROR: {e}")

    for inst in cfg.get("instances", {}).get("sonarr", []):
        name, url, key = inst["name"], inst["url"], inst["key"]
        ik = state_key(name, url)
        st_bucket = state.setdefault("sonarr", {}).setdefault(ik, {})
        try:
            all_ids = sonarr_get_cutoff_unmet_episode_ids(session, url, key)
            chosen, eligible, skipped = pick_ids_with_cooldown(all_ids, st_bucket, "episode", cooldown_hours, sonarr_max, sample_mode)
            print(f"[Sonarr:{name}] cutoff_unmet_total={len(all_ids)} eligible={eligible} skipped_cooldown={skipped} will_search={len(chosen)} limit={sonarr_max}")
            for i in range(0, len(chosen), batch_size):
                batch = chosen[i:i+batch_size]
                sonarr_search_episodes(session, url, key, batch, dry_run)
                if not dry_run:
                    mark_ids_searched(st_bucket, "episode", batch)
                if i + batch_size < len(chosen):
                    jitter_sleep(sleep_seconds, jitter_seconds)
        except Exception as e:
            print(f"[Sonarr:{name}] ERROR: {e}")

    if not dry_run:
        save_state(state)
        print(f"State updated: {STATE_FILE}")

app = Flask(__name__)

HTML = """<!doctype html>
<html>
<head>
<meta charset=\"utf-8\"/>
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"/>
<title>Nudgarr</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;margin:20px;max-width:1100px}
textarea{width:100%;min-height:420px;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:13px}
.row{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}
button{padding:10px 12px;cursor:pointer;border-radius:10px;border:1px solid #ccc;background:#f8f8f8}
button.primary{background:#111;color:#fff;border-color:#111}
pre{background:#f6f6f6;padding:12px;border-radius:12px;overflow-x:auto}
</style>
</head>
<body>
<h1>Nudgarr</h1>
<p>Because RSS sometimes needs a nudge. <span style=\"color:#666\">v{{VERSION}}</span></p>
<div class=\"row\">
  <button class=\"primary\" onclick=\"save()\">Save Config</button>
  <button onclick=\"reloadCfg()\">Reload</button>
  <button onclick=\"test()\">Test Connections</button>
  <button onclick=\"toggleDryRun()\">Toggle DRY_RUN</button>
</div>
<p style=\"color:#666\">Edits <code>/config/nudgarr-config.json</code>. Keep this UI behind LAN or Auth.</p>
<textarea id=\"cfg\"></textarea>
<h3>Status</h3>
<pre id=\"out\">Loading...</pre>
<script>
async function reloadCfg(){const r=await fetch('/api/config');const j=await r.json();document.getElementById('cfg').value=JSON.stringify(j,null,2);document.getElementById('out').textContent='Config loaded.';}
async function save(){try{const obj=JSON.parse(document.getElementById('cfg').value);const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(obj)});const j=await r.json();document.getElementById('out').textContent=JSON.stringify(j,null,2);}catch(e){document.getElementById('out').textContent='Error: '+e;}}
async function test(){const r=await fetch('/api/test',{method:'POST'});const j=await r.json();document.getElementById('out').textContent=JSON.stringify(j,null,2);}
async function toggleDryRun(){const r=await fetch('/api/toggle-dry-run',{method:'POST'});const j=await r.json();document.getElementById('out').textContent=JSON.stringify(j,null,2);await reloadCfg();}
reloadCfg();
</script>
</body></html>"""

@app.get("/")
def index():
    return Response(HTML.replace("{{VERSION}}", VERSION), mimetype="text/html")

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
    save_json_atomic(CONFIG_FILE, cfg)
    return jsonify({"ok": True, "message": "Config saved", "config_file": CONFIG_FILE})

@app.post("/api/toggle-dry-run")
def api_toggle_dryrun():
    cfg = load_or_init_config()
    cfg["dry_run"] = not bool(cfg.get("dry_run", True))
    save_json_atomic(CONFIG_FILE, cfg)
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
    print(f"Mode: {cfg.get('run_mode')}  Interval: {cfg.get('run_interval_minutes')} minute(s)  DRY_RUN: {cfg.get('dry_run')}")
    print("")

def start_ui_server() -> None:
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

def main() -> None:
    stop = {"requested": False}

    def handle_signal(signum, frame):
        print("\nShutdown signal received. Finishing current cycle...")
        stop["requested"] = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    cfg = load_or_init_config()
    print_banner(cfg)

    threading.Thread(target=start_ui_server, daemon=True).start()

    session = requests.Session()
    cycle = 0
    while True:
        cycle += 1
        cfg = load_or_init_config()
        print(f"--- Sweep Cycle #{cycle} ---")
        try:
            state = load_state()
            run_sweep(cfg, state, session)
        except Exception as e:
            print(f"ERROR (sweep): {e}")

        if stop["requested"] or str(cfg.get("run_mode", "loop")).lower() == "once":
            break

        interval_min = int(cfg.get("run_interval_minutes", 360))
        print(f"Sleeping {interval_min} minute(s)...\n")
        for _ in range(interval_min * 60):
            if stop["requested"]:
                break
            time.sleep(1)
        if stop["requested"]:
            break

    print("Nudgarr exiting.")

if __name__ == "__main__":
    main()
