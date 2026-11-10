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
shift
backend_host=127.0.0.1
backend_tls_cert=''
backend_tls_key=''
while (($#)); do
  case "$1" in
    --lan-host) (($# >= 2)) || { echo '--lan-host requires an address' >&2; exit 2; }; backend_host="$2"; shift 2 ;;
    --tls-cert) (($# >= 2)) || { echo '--tls-cert requires a path' >&2; exit 2; }; backend_tls_cert="$2"; shift 2 ;;
    --tls-key) (($# >= 2)) || { echo '--tls-key requires a path' >&2; exit 2; }; backend_tls_key="$2"; shift 2 ;;
    *) echo "Unknown backend option: $1" >&2; exit 2 ;;
  esac
done
if [[ "$backend_host" != 127.0.0.1 ]]; then
  [[ -n "$backend_tls_cert" && -n "$backend_tls_key" ]] || { echo 'Non-loopback binds require both HTTPS certificate and key files.' >&2; exit 2; }
  JARVIS_LAN_HOST="$backend_host" .venv/bin/python -c 'import os,sys; from app.lan import validate_lan_host; validate_lan_host(os.environ["JARVIS_LAN_HOST"])' || exit 2
  export JARVIS_LAN_MODE=1 JARVIS_LAN_HOST="$backend_host" JARVIS_LAN_CERT="$backend_tls_cert" JARVIS_LAN_KEY="$backend_tls_key"
  uvicorn_tls=(--ssl-certfile "$backend_tls_cert" --ssl-keyfile "$backend_tls_key")
  process_tls=(--tls-cert "$backend_tls_cert" --tls-key "$backend_tls_key")
else
  [[ -z "$backend_tls_cert" && -z "$backend_tls_key" ]] || { echo 'TLS files require a private LAN host.' >&2; exit 2; }
  unset JARVIS_LAN_MODE JARVIS_LAN_HOST JARVIS_LAN_CERT JARVIS_LAN_KEY
  uvicorn_tls=()
  process_tls=()
fi
if [[ "${JARVIS_DEV_MODE:-}" != 1 && ! -f frontend/dist/index.html ]]; then
  echo 'Build the frontend with npm --prefix frontend run build first.' >&2
  exit 1
fi
.venv/bin/python scripts/record-process.py backend "$$" --host "$backend_host" "${process_tls[@]}"
exec .venv/bin/python -m uvicorn app.main:create_app --factory --host "$backend_host" --port "$JARVIS_PORT" --no-access-log "${uvicorn_tls[@]}"
