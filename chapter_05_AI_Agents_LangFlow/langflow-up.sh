#!/usr/bin/env bash
# Start Docker Desktop (if needed) + Langflow container, wait until ready.
set -euo pipefail

DOCKER="/Applications/Docker.app/Contents/Resources/bin/docker"
DATA="/Users/promode/Documents/AITesterBlueprint3x/chapter_05_AI_Agents_LangFlow/langflow-data"
NAME="langflow"
URL="http://localhost:7860"

echo "==> Starting Docker Desktop..."
open -a "Docker Desktop"

echo "==> Waiting for daemon..."
for i in $(seq 1 60); do
  if "$DOCKER" info >/dev/null 2>&1; then echo "    daemon up (~$((i*3))s)"; break; fi
  sleep 3
done

# Create container if missing (first run / after prune), else just start it.
if "$DOCKER" ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  echo "==> Starting existing '$NAME' container..."
  "$DOCKER" start "$NAME" >/dev/null
else
  echo "==> Container '$NAME' not found. Creating with persistent volume..."
  "$DOCKER" run -d --name "$NAME" \
    -p 7860:7860 \
    -v "$DATA":/app/langflow-data \
    -e LANGFLOW_CONFIG_DIR=/app/langflow-data \
    -e LANGFLOW_SAVE_DB_IN_CONFIG_DIR=true \
    langflowai/langflow:latest >/dev/null
fi

echo "==> Waiting for Langflow to be ready..."
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$URL/health" 2>/dev/null || echo 000)
  if [ "$code" = "200" ]; then echo "    READY (~$((i*3))s)"; break; fi
  sleep 3
done

echo "==> Langflow: $URL"
"$DOCKER" ps --filter "name=$NAME" --format '    {{.Names}} | {{.Status}} | {{.Ports}}'
