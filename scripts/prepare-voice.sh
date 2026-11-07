#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
export HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1
voice_repo="$(realpath "${JARVIS_TTS_REPO:-$PWD/../JarvisLuxTTS}")"
voice_python="${JARVIS_TTS_PYTHON:-$voice_repo/.venv/bin/python}"
exec "$voice_python" scripts/prepare-voice.py "$@"
