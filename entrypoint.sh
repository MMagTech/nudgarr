#!/bin/sh
set -e

# Read PUID and PGID from environment, defaulting to 1000:1000
PUID=${PUID:-1000}
PGID=${PGID:-1000}

echo "[Nudgarr] Starting with UID=${PUID} GID=${PGID}"

# Fix ownership of /config so the runtime user can read/write it
chown -R "${PUID}:${PGID}" /config

# Drop to the requested UID/GID using numeric values directly
exec su-exec "${PUID}:${PGID}" python /app/nudgarr.py
