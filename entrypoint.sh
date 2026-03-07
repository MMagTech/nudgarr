#!/bin/sh
set -e

# Read PUID and PGID from environment, defaulting to 1000:1000
PUID=${PUID:-1000}
PGID=${PGID:-1000}

echo "[Nudgarr] Starting with UID=${PUID} GID=${PGID}"

# Attempt to fix ownership of /config so the runtime user can read/write it.
# This requires CHOWN capability. If it fails (e.g. cap_drop: ALL without
# cap_add: CHOWN), we warn and continue — the volume may already be owned
# correctly, in which case the app will start fine regardless.
if ! chown -R "${PUID}:${PGID}" /config 2>/dev/null; then
  echo "[Nudgarr] Warning: could not chown /config — continuing anyway."
  echo "[Nudgarr] If you see permission errors, either pre-set your volume"
  echo "[Nudgarr] ownership to ${PUID}:${PGID} or add cap_add: [CHOWN, SETUID, SETGID]"
fi

# Drop to the requested UID/GID using numeric values directly
exec su-exec "${PUID}:${PGID}" python /app/main.py
