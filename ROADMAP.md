# Roadmap

Planned features for upcoming releases. Nothing here is guaranteed — priorities may shift based on feedback and testing.

---

## v2.8.0 ✓

**Project structure refactor**
Split the monolithic nudgarr.py into a proper Python package — separate modules and a routes layer. No functional changes, no new dependencies.

---

## v2.9.0 ✓

**Security hardening**
Addressed all findings from the internal security audit — API key masking in config responses, URL validation on test endpoints, CSRF Origin/Referer header validation, security response headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy), persistent secret key surviving container restarts, and generic client-facing error messages with server-side logging.

---

## v3.0.0 ✓

**Mobile UI**
Purpose-built mobile layout for devices under 500px wide. Four-tab bottom nav (Home, Instances, Sweep, Exclusions), import pills on Home, bottom sheet modals for Exclusions and Imports, iOS safe area support, landscape orientation overlay. Same backend, no new dependencies.

---

## Future considerations

Items being considered but not yet scheduled: database migration from JSON to SQLite for better querying and pagination at scale, login page improvements for mobile thumb zones.

Items not on the roadmap by design: additional arr support (Readarr, Lidarr) — the codebase is open source and welcomes forks for this. Webhook trigger endpoint — Nudgarr is intentionally one-directional. Dashboard charts — keeps the approach lean.
