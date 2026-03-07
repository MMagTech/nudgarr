# Nudgarr Security Audit

**Audit Date:** 2026-03-06
**Codebase:** Nudgarr v2.7.0-dev
**Audited By:** Automated analysis (Claude)
**Scope:** Full codebase — backend Python, frontend JavaScript/HTML, configuration, and deployment

> **Context:** Nudgarr is a self-hosted Docker application that nudges Radarr and Sonarr to search
> for missing and cutoff-unmet content. It is a single-container, single-user tool intended for
> personal home server deployments. This context informs the severity ratings throughout this report.

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

- **File:** `nudgarr.py` — `api_get_config()` → `return jsonify(load_or_init_config())`
- **Impact:** The `GET /api/config` endpoint returns the full config dict including Radarr and Sonarr API keys in plaintext. Any authenticated session can retrieve these keys via the browser, browser history, or any network inspection tool. In a shared household or compromised session scenario this exposes credentials to downstream arr instances.
- **Mitigation:** Mask API keys in the GET response — return only the last 4 characters (e.g. `••••••••a1b2`). The full key should only travel from client to server on save, never back. The frontend already renders `Key: ••••••••` in the instance card but the underlying `/api/config` call returns the real value.
- **Status:** Not yet addressed — recommended for v2.8.0.

### H2: SSRF via Instance URL and Notification URL Fields

- **File:** `nudgarr.py` — `api_test()` and `api_test_notification()`
- **Impact:** Both the Test Connections endpoint (`/api/test`) and the notification test endpoint (`/api/notifications/test`) make outbound HTTP requests to user-supplied URLs without validating the target. An authenticated user — or an attacker who has obtained a session — could supply internal network addresses (e.g. `http://192.168.1.1`, `http://169.254.169.254`) to probe the internal network or cloud metadata services.
- **Mitigation:** Validate supplied URLs against an allowlist of expected patterns before making outbound requests. For instance URLs, verify the host is not a private IP range (RFC 1918 / link-local). For notification URLs, Apprise handles schema validation but does not block internal network targets.
- **Status:** Partially mitigated — both endpoints require authentication. Full URL validation recommended for v2.8.0.

### H3: No CSRF Protection on State-Changing Endpoints

- **File:** `nudgarr.py` — all `@app.post` routes
- **Impact:** No CSRF tokens are implemented on any POST endpoint. An attacker who can get an authenticated user to visit a malicious page could submit cross-origin requests to `/api/config`, `/api/state/clear`, `/api/config/reset`, or `/api/run-now`. Because the session cookie is sent automatically by the browser, the requests would succeed. In practice this risk is low for a local-only tool since the attacker must know the instance URL and port.
- **Mitigation:** Add CSRF token validation (Flask-WTF or a custom double-submit cookie pattern). At minimum, verify the `Origin` or `Referer` header on all state-changing POST routes.
- **Status:** Not addressed — acceptable risk for local deployment. Recommended for v2.8.0.

---

## MEDIUM Findings

### M1: Secret Key Regenerated on Every Container Restart

- **File:** `nudgarr.py:1025` — `app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)`
- **Impact:** If `SECRET_KEY` is not set as an environment variable, a new random key is generated on every container start. This invalidates all existing sessions on restart — expected behaviour for a local tool but can cause unreliable sessions for users who restart frequently.
- **Mitigation:** Auto-generate a persistent key at first startup and write it to `/config/nudgarr-secret.key`, then load it on subsequent starts. This preserves session continuity without requiring the user to set an environment variable. The Dockerfile already includes a comment explaining the current behaviour.
- **Status:** Low risk in practice. Enhancement recommended for v2.8.0.

### M2: Session Cookie Flags Not Explicitly Set

- **File:** `nudgarr.py` — Flask app configuration (no `SESSION_COOKIE_*` settings found)
- **Impact:** Flask session cookies are not explicitly configured with `SameSite` flags. Without `SameSite=Lax` the session cookie is sent on cross-site requests, contributing to the CSRF risk identified in H3. Flask defaults `HttpOnly=True` but does not set `SameSite`.
- **Mitigation:** Add to app configuration: `app.config["SESSION_COOKIE_HTTPONLY"] = True` and `app.config["SESSION_COOKIE_SAMESITE"] = "Lax"`. Do not set `SESSION_COOKIE_SECURE=True` as this would break HTTP deployments. `SameSite=Lax` provides meaningful CSRF protection at no cost to usability.
- **Status:** Not addressed — straightforward two-line fix recommended before v2.7.0 release.

---

## LOW Findings

### L1: No Security Headers

- **File:** `nudgarr.py` — no `after_request` security header middleware
- **Impact:** The application does not set `X-Content-Type-Options`, `X-Frame-Options`, or `Referrer-Policy` headers. Without these, browsers apply permissive defaults that marginally increase XSS and clickjacking exposure.
- **Mitigation:** Add an `after_request` hook that sets: `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`. CSP would require significant refactoring to accommodate inline scripts and is optional.
- **Status:** Not addressed — recommended for v2.8.0.

### L2: Verbose Exception Messages Returned to Client

- **File:** `nudgarr.py` — multiple `except` blocks returning `str(e)` in JSON responses
- **Impact:** Several API endpoints return raw exception strings to the client. In the notification test and connection test endpoints this could expose internal paths, library versions, or network topology details to the browser.
- **Mitigation:** Log the full exception server-side and return a generic user-facing message. Reserve detailed error strings for the diagnostic download, not inline API responses.
- **Status:** Low impact for single-user local tool. Recommended cleanup for v2.8.0.

---

## Positive Security Findings

- **Strong password hashing:** PBKDF2-HMAC-SHA256 with 260,000 iterations and a random salt. Significantly stronger than the SHA-256 used in the Huntarr codebase this project replaces.
- **Constant-time password comparison:** `hmac.compare_digest()` used for hash comparison, preventing timing attacks.
- **Progressive brute force lockout:** Failed login attempts trigger escalating lockouts (30s → 5m → 30m → 1h) tracked per IP in memory.
- **Session timeout:** Configurable session expiry (default 30 minutes) implemented and enforced on all authenticated routes.
- **Consistent XSS prevention:** `escapeHtml()` is applied to all user-supplied data rendered via `innerHTML`. `textContent` is used for non-HTML DOM updates. No instances of unescaped user data found in DOM rendering.
- **Complete endpoint authentication coverage:** All 24 non-auth API routes are decorated with `@requires_auth`. The 5 unauthenticated routes (`/login`, `/setup`, `/api/setup`, `/api/auth/login`, `/api/auth/logout`) are intentionally public and correct.
- **Privilege dropping at runtime:** The entrypoint uses `su-exec` to drop from root to the configured `PUID/PGID` before starting Python. The container does not run as root at application runtime.
- **Docker hardening:** `docker-compose.yml` includes `read_only` filesystem, `no-new-privileges`, `cap_drop: ALL` (with only `CHOWN`/`SETUID`/`SETGID` added back), `pids_limit`, `mem_limit`, and log rotation.
- **No telemetry or outbound data collection:** No phone-home, analytics, update-check, or external data transmission found in the codebase.
- **No code obfuscation:** Entire application is a single readable Python file. All logic is inspectable.
- **Atomic config writes:** `save_json_atomic()` uses write-to-temp then rename, preventing config corruption on crash.
- **API key masking in UI:** Instance cards display `Key: ••••••••` in the UI. `mask_url()` strips credentials from URLs in test connection results.
- **Alpine security patches at build time:** Dockerfile runs `apk upgrade --no-cache` to pull latest OS-level security patches on every image build.

---

## Recommendations by Priority

### Before v2.7.0 Release

1. **M2** — Add `SESSION_COOKIE_SAMESITE="Lax"` and `SESSION_COOKIE_HTTPONLY=True` to Flask app config. Two lines, no functional impact.

### v2.8.0 Hardening

1. **H1** — Mask API keys in `/api/config` GET response. Return only last 4 characters.
2. **H2** — Add URL validation to test connection and notification test endpoints. Block private IP ranges.
3. **H3** — Add `Origin`/`Referer` header validation on state-changing POST routes as minimum CSRF mitigation.
4. **L1** — Add `after_request` security header middleware.
5. **M1** — Persist auto-generated `SECRET_KEY` to `/config/nudgarr-secret.key` rather than regenerating on restart.
6. **L2** — Replace raw `str(e)` in API error responses with generic messages; log full detail server-side.

### Documentation

- Document that the `/config` volume should have restrictive filesystem permissions.
- Add a redaction reminder to the diagnostic output header before sharing publicly.

---

## Comparison to NewtArr/Huntarr Audit

The NewtArr security audit of the Huntarr v6.6.3 codebase identified 5 CRITICAL findings. Nudgarr has 0 CRITICAL findings. Key differences:

| Issue | Huntarr/NewtArr | Nudgarr |
|:------|:----------------|:--------|
| Password hashing | SHA-256 (CRITICAL) | PBKDF2-HMAC-SHA256 / 260k rounds |
| Timing attack protection | Not implemented | `hmac.compare_digest()` |
| Brute force protection | Not implemented | Progressive lockout per IP |
| Secret key | Hardcoded fallback (CRITICAL) | Random per restart or env var |
| Runs as root | Yes (MEDIUM) | `su-exec` drops to PUID/PGID |
| XSS prevention | `innerHTML` without escaping (CRITICAL) | `escapeHtml()` consistently applied |
| CSRF protection | Not implemented (HIGH) | Not implemented (LOW for local tool) |
| API key masking | Not implemented (HIGH) | UI masked; `/api/config` returns full key (H1) |
| Telemetry | Present in upstream | None |
| Code obfuscation | Present in upstream | None — fully readable |

---

*This audit was performed via automated static analysis and manual code review of the full `nudgarr.py` source, `Dockerfile`, `entrypoint.sh`, and `docker-compose.yml`. No dynamic testing or penetration testing was performed.*
