#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == --prepare-stt ]]; then
  exec bash "$(dirname "$0")/prepare-stt.sh"
fi
if [[ "${1:-}" == --prepare-voice ]]; then
  exec bash "$(dirname "$0")/prepare-voice.sh"
fi
if [[ "${1:-}" == --prepare-voice-gpu ]]; then
  exec bash "$(dirname "$0")/prepare-voice.sh" --gpu
fi
if [[ "${1:-}" == --configure-model ]]; then
  exec bash "$(dirname "$0")/context-model.sh"
fi
if [[ "${1:-}" == --agent ]]; then
  exec bash "$(dirname "$0")/hermes.sh"
fi
source "$(dirname "$0")/common.sh"
if [[ "${1:-}" == --prepare-memory ]]; then
  exec .venv/bin/python scripts/prepare-memory.py
fi
if [[ "${1:-}" != --backend ]]; then
  exec .venv/bin/python scripts/run.py "$@"
fi
if [[ "${JARVIS_DEV_MODE:-}" != 1 && ! -f frontend/dist/index.html ]]; then
  echo 'Build the frontend with npm --prefix frontend run build first.' >&2
  exit 1
fi
.venv/bin/python scripts/record-process.py backend "$$"
exec .venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port "$JARVIS_PORT" --no-access-log
