#!/usr/bin/env bash
# Stop Langflow container and quit Docker Desktop.
set -euo pipefail

DOCKER="/Applications/Docker.app/Contents/Resources/bin/docker"
NAME="langflow"

if "$DOCKER" info >/dev/null 2>&1; then
  echo "==> Stopping '$NAME'..."
  "$DOCKER" stop "$NAME" >/dev/null 2>&1 || echo "    (not running)"
  echo "==> Quitting Docker Desktop..."
  osascript -e 'quit app "Docker Desktop"' >/dev/null 2>&1 || true
  sleep 3
fi

if pgrep -f "Docker Desktop" >/dev/null; then
  echo "    Docker still running (force-quit if needed)."
else
  echo "==> Docker Desktop quit. All stopped."
fi
