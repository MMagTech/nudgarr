#!/usr/bin/env python3
import os
import time
import json
import random
import signal
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

VERSION = "1.0.0"

def utcnow():
    return datetime.now(timezone.utc)

def isoformat(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def env_bool(name, default=False):
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1","true","yes","y","on")

def env_int(name, default):
    v = os.getenv(name)
    if v is None or not v.strip():
        return default
    return int(v)

def load_instances():
    raw = os.getenv("ARR_INSTANCES","").strip()
    if raw:
        return json.loads(raw)
    inst = {"radarr":[], "sonarr":[]}
    if os.getenv("RADARR_URL") and os.getenv("RADARR_KEY"):
        inst["radarr"].append({
            "name":"radarr-1",
            "url":os.getenv("RADARR_URL"),
            "key":os.getenv("RADARR_KEY")
        })
    if os.getenv("SONARR_URL") and os.getenv("SONARR_KEY"):
        inst["sonarr"].append({
            "name":"sonarr-1",
            "url":os.getenv("SONARR_URL"),
            "key":os.getenv("SONARR_KEY")
        })
    return inst

def req(session, method, url, key, body=None):
    headers={"X-Api-Key":key}
    r=session.request(method,url,headers=headers,json=body,timeout=30)
    r.raise_for_status()
    return r.json() if r.text else None

def radarr_sweep(session, inst, dry_run):
    url=f"{inst['url'].rstrip('/')}/api/v3/command"
    payload={"name":"CutOffUnmetMoviesSearch"}
    if dry_run:
        print(f"[Radarr] DRY_RUN would trigger sweep on {inst['name']}")
    else:
        req(session,"POST",url,inst["key"],payload)
        print(f"[Radarr] Sweep triggered on {inst['name']}")

def sonarr_sweep(session, inst, max_eps, dry_run):
    url=f"{inst['url'].rstrip('/')}/api/v3/wanted/cutoff?page=1&pageSize=100"
    data=req(session,"GET",url,inst["key"])
    records=data.get("records",[])
    ids=[r["episodeId"] for r in records if "episodeId" in r]
    chosen=ids[:max_eps]
    print(f"[Sonarr] {inst['name']} total={len(ids)} searching={len(chosen)}")
    if not dry_run and chosen:
        cmd=f"{inst['url'].rstrip('/')}/api/v3/command"
        req(session,"POST",cmd,inst["key"],{"name":"EpisodeSearch","episodeIds":chosen})

def main():
    print("====================================")
    print(f" Nudgarr v{VERSION}")
    print(" Because RSS sometimes needs a nudge.")
    print("====================================\n")

    run_mode=os.getenv("RUN_MODE","loop")
    interval=env_int("RUN_INTERVAL_MINUTES",360)
    dry_run=env_bool("DRY_RUN",True)
    max_eps=env_int("SONARR_MAX_EPISODES_PER_RUN",50)

    print(f"Mode: {run_mode}")
    if run_mode=="loop":
        print(f"Interval: {interval} minutes\n")

    instances=load_instances()
    session=requests.Session()

    stop=False
    def handler(sig,frame):
        nonlocal stop
        print("Shutdown requested...")
        stop=True
    signal.signal(signal.SIGINT,handler)
    signal.signal(signal.SIGTERM,handler)

    cycle=0
    while True:
        cycle+=1
        print(f"--- Sweep Cycle #{cycle} ---")
        print(f"Started: {utcnow().isoformat()}")

        for r in instances.get("radarr",[]):
            radarr_sweep(session,r,dry_run)

        for s in instances.get("sonarr",[]):
            sonarr_sweep(session,s,max_eps,dry_run)

        if run_mode=="once" or stop:
            break

        print(f"Sleeping {interval} minutes...\n")
        for _ in range(interval*60):
            if stop:
                break
            time.sleep(1)

        if stop:
            break

    print("Nudgarr exiting.")

if __name__=="__main__":
    main()
