# Security Policy

## Supported Versions

Only the latest release of Nudgarr receives security fixes.

| Version | Supported |
|---------|-----------|
| Latest  | ✅ |
| Older   | ❌ |

---

## Deployment Context

Nudgarr is a single-user, self-hosted Docker application designed for local network use. It is not designed for direct internet exposure — users requiring external access should place it behind an authenticated reverse proxy.

---

## Reporting a Vulnerability

You can report vulnerabilities by opening a public issue or via GitHub's private vulnerability reporting for this repository. Private reporting allows the issue to be investigated and patched before public disclosure.

Expect an initial response within a few days. This is a solo-maintained project — there is no formal SLA, but security reports are treated as high priority. Patches will be applied to the latest version only.

Please include:

- Nudgarr version
- Steps to reproduce
- Potential impact

---

## Scope

**In scope:** the Nudgarr application, Dockerfile, and default docker-compose configuration.

**Out of scope:** vulnerabilities that require physical access to the host, or issues in Radarr, Sonarr, or Apprise themselves.
