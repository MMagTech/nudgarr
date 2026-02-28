#!/bin/sh
set -e

# Fix ownership of /config so the nudgarr user can read/write it
# This runs briefly as root before dropping privileges
chown -R nudgarr:nudgarr /config

# Drop to non-root user and start the app
exec su-exec nudgarr python /app/nudgarr.py
