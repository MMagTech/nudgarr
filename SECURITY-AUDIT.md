# Nudgarr Security Audit

**Audit Date:** 2026-03-06 (references updated 2026-03-07 for v2.8.0 package structure)
**Codebase:** Nudgarr v2.8.0
**Audited By:** Automated analysis (Claude)
**Scope:** Full codebase — backend Python, frontend JavaScript/HTML, configuration, and deployment

> **Context:** Nudgarr is a self-hosted Docker application that nudges Radarr and Sonarr to search
> for missing and cutoff-unmet content. It is a single-container, single-user tool intended for
> personal home server deployments on a local network. HTTPS is not planned — users requiring
> external access are directed to use an external auth layer. This context informs the severity
> ratings throughout this report.

---

## Summary

| Severity | Backend | Frontend | Config/Deploy | Total |
|:---------|:-------:|:--------:|:-------------:|:-----:|
| CRITICAL | 0 | 0 | 0 | **0** |
| HIGH | 2 | 0 | 1 | **3** |
| MEDIUM | 2 | 0 | 1 | **3** |
| LOW | 1 | 0 | 1 | **2** |
| INFO | 0 | 0 | 0 | **0** |

> Note: No CRITICAL findings were identified. Nudgarr's single-user, local-network deployment model
> mitigates many risks that would be severe in multi-user or internet-exposed applications.
> All findings below should still be reviewed and addressed over time.

---

## HIGH Findings

### H1: API Keys Returned in Full via /api/config

- **File:** `nudgarr/routes/config.py:31` — `api_get_config()` → `return jsonify(load_or_init_config())`
- **Impact:** The `GET /api/config` endpoint returns the full config dict including Radarr and Sonarr API keys in plaintext. Any authenticated session can retrieve these keys via the browser, browser history, or any network inspection tool. In a shared household or compromised session scenario this exposes credentials to downstream arr instances.
- **Mitigation:** Mask API keys in the GET response — return only the last 4 characters (e.g. `••••••••a1b2`). The full key should only travel from client to server on save, never back. The frontend already renders `Key: ••••••••` in the instance card but the underlying `/api/config` call returns the real value.
- **Status:** ✅ Closed — v2.9.0.

### H2: SSRF via Instance URL and Notification URL Fields

- **File:** `nudgarr/routes/sweep.py:43` — `api_test()` and `nudgarr/routes/notifications.py:19` — `api_test_notification()`
- **Impact:** Both the Test Connections endpoint (`/api/test`) and the notification test endpoint (`/api/notifications/test`) make outbound HTTP requests to user-supplied URLs without validating the target. An authenticated user — or an attacker who has obtained a session — could supply internal network addresses (e.g. `http://192.168.1.1`, `http://169.254.169.254`) to probe the internal network or cloud metadata services.
- **Mitigation:** Validate supplied URLs against an allowlist of expected patterns before making outbound requests. For instance URLs, verify the host is not a private IP range (RFC 1918 / link-local). For notification URLs, Apprise handles schema validation but does not block internal network targets.
- **Status:** ✅ Closed — v2.9.0. URL validation added; link-local addresses blocked.

### H3: No CSRF Protection on State-Changing Endpoints

- **File:** `nudgarr/routes/*.py` — all 17 `@bp.post` routes across config, state, stats, sweep, notifications, and auth blueprints
- **Impact:** No CSRF tokens are implemented on any POST endpoint. An attacker who can get an authenticated user to visit a malicious page could submit cross-origin requests to `/api/config`, `/api/state/clear`, `/api/config/reset`, or `/api/run-now`. Because the session cookie is sent automatically by the browser, the requests would succeed. In practice this risk is low for a local-only tool since the attacker must know the instance URL and port.
- **Mitigation:** Add CSRF token validation (Flask-WTF or a custom double-submit cookie pattern). At minimum, verify the `Origin` or `Referer` header on all state-changing POST routes.
- **Status:** ✅ Closed — v2.9.0. Origin/Referer header validation added to all authenticated POST routes.

---

## MEDIUM Findings

### M1: Secret Key Regenerated on Every Container Restart

- **File:** `nudgarr/globals.py:29` — `app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)`
- **Impact:** If `SECRET_KEY` is not set as an environment variable, a new random key is generated on every container start. This invalidates all existing sessions on restart — expected behaviour for a local tool but can cause unreliable sessions for users who restart frequently.
- **Mitigation:** Auto-generate a persistent key at first startup and write it to `/config/nudgarr-secret.key`, then load it on subsequent starts. This preserves session continuity without requiring the user to set an environment variable.
- **Status:** ✅ Closed — v2.9.0. Key persisted to `/config/nudgarr-secret.key` on first start.

### M2: Session Cookie Flags Not Explicitly Set

- **File:** `nudgarr/globals.py:32` — Flask app configuration
- **Impact:** Flask session cookies were not explicitly configured with `SameSite` flags. `SameSite=Lax` breaks POST requests in reverse-proxy and iframe environments (Unraid, Synology), causing auth failures on all save operations. Nudgarr is a LAN-only tool and HTTPS is not on the roadmap — users requiring external access are directed to use an external auth layer.
- **Resolution (v2.8.0):** `SESSION_COOKIE_HTTPONLY=True` explicitly set. `SESSION_COOKIE_SAMESITE` will not be configured — HTTPS is not planned, making `SameSite=Lax` harmful and `SameSite=None; Secure` unavailable. This item is closed.
- **Status:** ✅ Closed — v2.8.0.

---

## LOW Findings

### L1: No Security Headers

- **File:** `nudgarr/globals.py` — no `after_request` security header middleware present
- **Impact:** The application does not set `X-Content-Type-Options`, `X-Frame-Options`, or `Referrer-Policy` headers. Without these, browsers apply permissive defaults that marginally increase XSS and clickjacking exposure.
- **Mitigation:** Add an `after_request` hook in `nudgarr/globals.py` that sets: `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`. CSP would require significant refactoring to accommodate inline scripts and is optional.
- **Status:** ✅ Closed — v2.9.0. `after_request` hook added.

### L2: Verbose Exception Messages Returned to Client

- **File:** `nudgarr/routes/sweep.py:66,88`, `nudgarr/routes/notifications.py:39`, `nudgarr/routes/stats.py:82` — multiple `except` blocks returning `str(e)` in JSON responses
- **Impact:** Several API endpoints return raw exception strings to the client. In the notification test and connection test endpoints this could expose internal paths, library versions, or network topology details to the browser.
- **Mitigation:** Log the full exception server-side and return a generic user-facing message. Reserve detailed error strings for the diagnostic download, not inline API responses.
- **Status:** ✅ Closed — v2.9.0. Generic messages returned to client; full detail logged server-side.

---

## Positive Security Findings

- **Strong password hashing:** PBKDF2-HMAC-SHA256 with 260,000 iterations and a random salt — `nudgarr/auth.py`.
- **Constant-time password comparison:** `hmac.compare_digest()` used for hash comparison in `nudgarr/auth.py`, preventing timing attacks.
- **Progressive brute force lockout:** Failed login attempts trigger escalating lockouts (30s → 5m → 30m → 1h) tracked per IP in `nudgarr/auth.py`.
- **Session timeout:** Configurable session expiry (default 30 minutes) implemented in `nudgarr/auth.py` and enforced via `@requires_auth` on all authenticated routes.
- **Consistent XSS prevention:** `escapeHtml()` is applied to all user-supplied data rendered via `innerHTML` in `nudgarr/templates/ui.html`. `textContent` is used for non-HTML DOM updates. No instances of unescaped user data found in DOM rendering.
- **Complete endpoint authentication coverage:** All 26 non-auth API routes are decorated with `@requires_auth` across 6 blueprints. The 5 unauthenticated routes (`/login`, `/setup`, `/api/setup`, `/api/auth/login`, `/api/auth/logout`) are intentionally public and correct.
- **Privilege dropping at runtime:** `entrypoint.sh` uses `su-exec` to drop from root to the configured `PUID/PGID` before starting Python. The container does not run as root at application runtime.
- **Docker hardening:** `docker-compose.yml` includes `read_only` filesystem, `no-new-privileges`, `cap_drop: ALL` (with only `CHOWN`/`SETUID`/`SETGID` added back), `pids_limit`, `mem_limit`, and log rotation.
- **No telemetry or outbound data collection:** No phone-home, analytics, update-check, or external data transmission found in the codebase.
- **Readable, inspectable codebase:** As of v2.8.0 the application is a proper Python package under `nudgarr/`. All logic is split into focused modules and fully inspectable.
- **Atomic config writes:** `save_json_atomic()` in `nudgarr/utils.py` uses write-to-temp then rename, preventing config corruption on crash.
- **API key masking in UI:** Instance cards display `Key: ••••••••` in the UI. `mask_url()` in `nudgarr/utils.py` strips credentials from URLs in test connection results.
- **Alpine security patches at build time:** Dockerfile runs `apk upgrade --no-cache` to pull latest OS-level security patches on every image build.

---

## Recommendations by Priority

### Closed

1. **M2** — `SESSION_COOKIE_HTTPONLY=True` added. `SESSION_COOKIE_SAMESITE` not set — LAN-only, HTTPS not planned. ✅ Closed v2.8.0.
2. **H1** — API keys masked in `GET /api/config` response (`nudgarr/routes/config.py`). ✅ Closed v2.9.0.
3. **H2** — URL validation added to `api_test()` and `api_test_notification()`. Link-local addresses blocked. ✅ Closed v2.9.0.
4. **H3** — Origin/Referer header validation on all authenticated POST routes (`nudgarr/auth.py`). ✅ Closed v2.9.0.
5. **L1** — Security response headers via `after_request` hook in `nudgarr/globals.py`. ✅ Closed v2.9.0.
6. **M1** — Secret key persisted to `/config/nudgarr-secret.key` (`nudgarr/globals.py`). ✅ Closed v2.9.0.
7. **L2** — Raw `str(e)` removed from all route error responses. ✅ Closed v2.9.0.

### Documentation

- Document that the `/config` volume should have restrictive filesystem permissions.
- Add a redaction reminder to the diagnostic output header before sharing publicly.


---

*This audit was performed via automated static analysis and manual code review of the full Nudgarr v2.8.0 package (`main.py`, `nudgarr/`, `nudgarr/routes/`, `nudgarr/templates/`), `Dockerfile`, `entrypoint.sh`, and `docker-compose.yml`. File references updated from v2.7.0-dev single-file format to v2.8.0 package structure. No dynamic testing or penetration testing was performed.*
