"""
nudgarr/utils.py

Stateless helpers used throughout the package.

  Time     : utcnow, iso_z, parse_iso
  File I/O : ensure_dir, load_json, save_json_atomic
  Network  : mask_url, req
  Timing   : jitter_sleep

No imports from within the nudgarr package — stdlib + requests only.
"""

import json
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, Optional

import requests


# ── Time ──────────────────────────────────────────────────────────────

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


# ── File I/O ──────────────────────────────────────────────────────────

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
    # Write tmp file in the same directory as target to ensure os.replace works
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            if pretty:
                json.dump(data, f, indent=2, sort_keys=True)
            else:
                json.dump(data, f, separators=(",", ":"), sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        # Clean up tmp if replace failed
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── Network ───────────────────────────────────────────────────────────

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


def req(session: requests.Session, method: str, url: str, key: str,
        json_body: Optional[dict] = None, timeout: int = 30):
    headers = {"X-Api-Key": key}
    r = session.request(method, url, headers=headers, json=json_body, timeout=timeout)
    r.raise_for_status()
    if r.text:
        try:
            return r.json()
        except Exception:
            return r.text
    return None


# ── Timing ────────────────────────────────────────────────────────────

def jitter_sleep(base_s: float, jitter_s: float) -> None:
    delay = base_s + (random.random() * jitter_s if jitter_s > 0 else 0)
    if delay > 0:
        time.sleep(delay)
