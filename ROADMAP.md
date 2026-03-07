# Roadmap

Planned features for upcoming releases. Nothing here is guaranteed — priorities may shift based on feedback and testing.

---

## v2.8.0

**Project structure refactor**
The codebase is currently a single Python file. v2.8.0 will split it into a proper project structure with separate files and folders — making it easier to read, review, and contribute to. No functional changes, no new dependencies. The goal is to make the codebase more accessible for community review ahead of the security hardening pass in v2.9.0.

---

## v2.9.0

**Security hardening**
Addressing findings from the internal security audit — API key masking in config responses, URL validation on test endpoints, CSRF origin header validation, security response headers, persistent secret key, and structured logging with generic client-facing error messages.

---

## v3.0

**Database migration**
Replace JSON file storage with SQLite for history, state, and stats. Enables better querying, filtering, and pagination performance as history grows. Will include a migration path from existing JSON files — no data loss on upgrade.

---

## Future considerations

A proper mobile layout — same backend, same logic, just a UI built for smaller screens. If the project finds its audience, this would be the natural next step.

---

Items not on the roadmap by design: additional arr support (Readarr, Lidarr) — the codebase is open source and welcomes forks for this. Webhook trigger endpoint — Nudgarr is intentionally one-directional. Dashboard charts — keeps the approach lean.
