#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
umask 077
if [[ -f .env ]]; then set -a; source .env; set +a; fi
profile_path="$(python3 scripts/runtime.py --profile-home)"
export HERMES_HOME="$profile_path"
if runtime_exports="$(python3 scripts/runtime.py --shell 2>/dev/null)"; then
  eval "$runtime_exports"
fi
export PYTHONPATH="$PWD/backend${PYTHONPATH:+:$PYTHONPATH}"
export HF_HUB_DISABLE_TELEMETRY=1
export DO_NOT_TRACK=1
export JARVIS_PORT="${JARVIS_PORT:-8787}"
export JARVIS_BACKEND_URL="http://127.0.0.1:$JARVIS_PORT"
export JARVIS_FRONTEND_PORT="${JARVIS_FRONTEND_PORT:-3000}"
if [[ "$JARVIS_PORT" != 8787 || "$JARVIS_FRONTEND_PORT" != 3000 ]]; then
  export JARVIS_ORIGINS="${JARVIS_ORIGINS:-http://127.0.0.1:$JARVIS_FRONTEND_PORT,http://localhost:$JARVIS_FRONTEND_PORT,http://127.0.0.1:$JARVIS_PORT,http://localhost:$JARVIS_PORT}"
fi
