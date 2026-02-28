#!/bin/sh
set -e

# Read PUID and PGID from environment, defaulting to 1000:1000
PUID=${PUID:-1000}
PGID=${PGID:-1000}

echo "[Nudgarr] Starting with UID=${PUID} GID=${PGID}"

# Create group with the requested GID if it doesn't already exist
if ! getent group "$PGID" > /dev/null 2>&1; then
    addgroup -g "$PGID" nudgarr
fi

# Create user with the requested UID if it doesn't already exist
if ! getent passwd "$PUID" > /dev/null 2>&1; then
    adduser -D -u "$PUID" -G "$(getent group "$PGID" | cut -d: -f1)" nudgarr
fi

# Fix ownership of /config so the runtime user can read/write it
chown -R "$PUID:$PGID" /config

# Drop privileges to the requested UID/GID and start the app
exec su-exec "$PUID:$PGID" python /app/nudgarr.py
