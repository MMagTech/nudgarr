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

## v3.0

**Database migration**
Replace JSON file storage with SQLite for history, state, and stats. Enables better querying, filtering, and pagination performance as history grows. Will include a migration path from existing JSON files — no data loss on upgrade.

---

## Future considerations

A proper mobile layout — same backend, same logic, just a UI built for smaller screens. If the project finds its audience, this would be the natural next step.

---

Items not on the roadmap by design: additional arr support (Readarr, Lidarr) — the codebase is open source and welcomes forks for this. Webhook trigger endpoint — Nudgarr is intentionally one-directional. Dashboard charts — keeps the approach lean.
