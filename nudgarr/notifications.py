"""
nudgarr/notifications.py

Apprise-based push notification dispatch.

  send_notification    -- core dispatcher, returns True on success
  notify_sweep_complete -- called after each sweep cycle
  notify_import        -- called when an import is confirmed
  notify_error         -- called on sweep or instance errors

All notify_* helpers are no-ops when the relevant trigger is disabled
in config, or when Apprise is unavailable.

Imports from within the package: config only (APPRISE_AVAILABLE via
a deferred try/import to avoid hard-failing when apprise is absent).
"""

from typing import Any, Dict, Optional

from nudgarr.config import load_or_init_config

try:
    import apprise
    APPRISE_AVAILABLE = True
except ImportError:
    APPRISE_AVAILABLE = False


# ── Core dispatcher ───────────────────────────────────────────────────

def send_notification(title: str, body: str, cfg: Optional[Dict[str, Any]] = None) -> bool:
    """Send a notification via Apprise. Returns True on success."""
    if not APPRISE_AVAILABLE:
        print("[Notify] Apprise not available")
        return False
    if cfg is None:
        cfg = load_or_init_config()
    if not cfg.get("notify_enabled") or not cfg.get("notify_url", "").strip():
        return False
    try:
        ap = apprise.Apprise()
        ap.add(cfg["notify_url"].strip())
        result = ap.notify(title=title, body=body)
        if result:
            print(f"[Notify] Sent: {title}")
        else:
            print(f"[Notify] Failed to send: {title}")
        return result
    except Exception as e:
        print(f"[Notify] Error: {e}")
        return False


# ── Trigger helpers ───────────────────────────────────────────────────

def notify_sweep_complete(summary: Dict[str, Any], cfg: Dict[str, Any]) -> None:
    if not cfg.get("notify_on_sweep_complete", True):
        return
    searched = 0
    skipped = 0
    for app in ("radarr", "sonarr"):
        for inst in summary.get(app, []):
            searched += inst.get("searched", 0) + inst.get("searched_missing", 0)
            skipped += inst.get("skipped_cooldown", 0) + inst.get("skipped_missing_cooldown", 0)
    send_notification(
        title="Nudgarr — Sweep Complete",
        body=f"{searched} item{'s' if searched != 1 else ''} searched, {skipped} skipped due to cooldown.",
        cfg=cfg
    )


def notify_import(title: str, entry_type: str, instance: str, cfg: Dict[str, Any]) -> None:
    if not cfg.get("notify_on_import", True):
        return
    send_notification(
        title=f"Nudgarr — {entry_type} Imported",
        body=f"{title} was successfully imported via {instance}.",
        cfg=cfg
    )


def notify_error(message: str, cfg: Optional[Dict[str, Any]] = None) -> None:
    if cfg is None:
        cfg = load_or_init_config()
    if not cfg.get("notify_on_error", True):
        return
    send_notification(
        title="Nudgarr — Error",
        body=message,
        cfg=cfg
    )

