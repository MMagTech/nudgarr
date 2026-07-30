"""
tests/test_notification_url.py

Unit tests for notification URL safety checks in nudgarr.utils.

Zero mocking and no apprise import — these tests cover the validation gate
only, not delivery. The gate must accept every Apprise scheme (~180 of them)
while still blocking link-local hosts, and is_safe_url must keep its tighter
http/https rule for arr instance URLs.

Regression guard for the v5.0.5 fix: the notification test endpoint rejected
every non-HTTP scheme, so ntfy://, gotify://, and friends could never be
tested from the UI.
"""

import pytest
from nudgarr.utils import is_safe_notification_url, is_safe_url


# ---------------------------------------------------------------------------
# Notification URLs — schemes Apprise owns
# ---------------------------------------------------------------------------

APPRISE_SCHEME_URLS = [
    # HTTP-based services that use a custom scheme
    "ntfy://172.17.0.1:8091/nudgarr",
    "ntfy://192.168.1.206:8091/nudgarr",
    "ntfy://ntfy.example.com/nudgarr",
    "gotify://192.168.1.5/token",
    "discord://123456789/abcdefghijklmnop",
    "pover://user@token",
    "matrixs://user:pass@matrix.org/#room",
    "slack://token/token/token",
    # Generic webhook wrappers
    "form://192.168.1.9/hook",
    "json://192.168.1.9/hook",
    "xml://192.168.1.9/hook",
    # Non-HTTP transports
    "mailto://user:pass@gmail.com",
    "mailtos://user:pass@smtp.example.com:587",
    # Hostless transports — Apprise supplies the target itself
    "windows://",
    "macosx://",
    "dbus://",
    "gnome://",
    "glib://",
    "syslog://",
]


@pytest.mark.parametrize("url", APPRISE_SCHEME_URLS)
def test_apprise_schemes_are_allowed(url):
    """Every Apprise scheme must pass the gate — validating it is Apprise's job."""
    assert is_safe_notification_url(url) is True


def test_blank_host_is_allowed():
    """ntfys:///topic omits the host and lets Apprise default to ntfy.sh."""
    assert is_safe_notification_url("ntfys:///nudgarr") is True


@pytest.mark.parametrize("url", [
    "https://discord.com/api/webhooks/123456789/abcdefghijklmnop",
    "https://discordapp.com/api/webhooks/123456789/abcdefghijklmnop",
    "https://hooks.slack.com/services/T00/B00/XXXX",
])
def test_native_https_webhooks_still_allowed(url):
    """Native https webhook URLs worked before the fix and must keep working."""
    assert is_safe_notification_url(url) is True


# ---------------------------------------------------------------------------
# Notification URLs — link-local stays blocked
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "ntfy://169.254.169.254/topic",
    "gotify://169.254.169.254/token",
    "http://169.254.169.254/latest/meta-data",
    "https://169.254.169.254/latest/meta-data",
])
def test_link_local_hosts_are_blocked(url):
    """Dropping the scheme allowlist must not weaken metadata-probe protection."""
    assert is_safe_notification_url(url) is False


def test_ipv6_link_local_is_blocked():
    """fe80::/10 is link-local too, not just 169.254.x.x."""
    assert is_safe_notification_url("ntfy://[fe80::1]/topic") is False


def test_private_ranges_are_allowed():
    """RFC 1918 hosts are the normal case for self-hosted notification targets."""
    assert is_safe_notification_url("ntfy://10.0.0.5/topic") is True
    assert is_safe_notification_url("ntfy://192.168.1.5/topic") is True
    assert is_safe_notification_url("ntfy://172.16.0.5/topic") is True


def test_empty_and_garbage_input():
    """Empty input is host-less so it passes the gate; Apprise then rejects it."""
    assert is_safe_notification_url("") is True
    assert is_safe_notification_url("not-a-url") is True


# ---------------------------------------------------------------------------
# arr instance URLs — the tighter rule must stay tight
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "ntfy://192.168.1.206:8091/nudgarr",
    "discord://123/abc",
    "mailto://user:pass@gmail.com",
    "dbus://",
])
def test_is_safe_url_still_rejects_non_http_schemes(url):
    """Radarr and Sonarr only speak http/https — that allowlist must remain."""
    assert is_safe_url(url) is False


@pytest.mark.parametrize("url", [
    "http://192.168.1.10:7878",
    "https://radarr.example.com",
    "http://radarr.local:7878/",
    "http://[::1]:7878",
])
def test_is_safe_url_allows_arr_instances(url):
    """Normal arr instance URLs, including IPv6 and bare hostnames."""
    assert is_safe_url(url) is True


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data",
    "https://169.254.169.254/",
    "http://[fe80::1]/",
])
def test_is_safe_url_blocks_link_local(url):
    """The original H2 hardening behaviour is unchanged."""
    assert is_safe_url(url) is False


# ---------------------------------------------------------------------------
# Structural guard — the endpoint must use the notification-aware check
# ---------------------------------------------------------------------------

def test_notification_route_uses_notification_check():
    """
    Guards against reintroducing the bug by wiring the endpoint back to
    is_safe_url, which would block every Apprise scheme again.
    """
    import inspect
    from nudgarr.routes import notifications

    src = inspect.getsource(notifications)
    assert "is_safe_notification_url(url)" in src
    assert "is_safe_url(url)" not in src
