"""
nudgarr/routes/notifications.py

Notification test endpoint.

  POST /api/notifications/test -- send a test notification via Apprise
"""

from flask import Blueprint, jsonify, request

from nudgarr.auth import requires_auth
from nudgarr.notifications import APPRISE_AVAILABLE

bp = Blueprint("notifications", __name__)


@bp.post("/api/notifications/test")
@requires_auth
def api_test_notification():
    data = request.get_json(force=True, silent=True) or {}
    url = str(data.get("url", "")).strip()
    if not url:
        return jsonify({"ok": False, "error": "No URL provided"}), 400
    if not APPRISE_AVAILABLE:
        return jsonify({"ok": False, "error": "Apprise is not installed in this container"}), 500
    try:
        import apprise
        ap = apprise.Apprise()
        if not ap.add(url):
            return jsonify({"ok": False, "error": "Invalid notification URL — check the format"}), 400
        result = ap.notify(
            title="Nudgarr — Test Notification",
            body="Your notification setup is working correctly.",
        )
        if result:
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "Notification sent but delivery failed — check your service settings"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
