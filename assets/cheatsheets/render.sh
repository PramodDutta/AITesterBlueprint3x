#!/usr/bin/env bash
# Render one chapter cheat sheet. Needs a working Codex login.
#   ./render.sh ch18-langgraph
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
NAME="${1:?usage: render.sh <brief-name, e.g. ch18-langgraph>}"
bash ~/.claude/skills/codex-imagegen/scripts/codex-image.sh \
  --prompt-file "$HERE/$NAME.brief.md" \
  --out "$HERE/$NAME.png" \
  --size 1920x1080 --aspect 16:9 "${@:2}"
