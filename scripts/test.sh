#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${1:-}" == --interactions ]]; then shift; exec node scripts/interaction-check.mjs "$@"; fi
if [[ "${1:-}" == --firefox-chat ]]; then shift; exec node scripts/firefox-chat-check.mjs "$@"; fi
if [[ "${1:-}" == --browser ]]; then shift; exec node scripts/browser-check.mjs "$@"; fi
if [[ "${1:-}" == --speech ]]; then exec node scripts/speech-check.mjs; fi
if [[ "${1:-}" == --voice-browser ]]; then exec node scripts/voice-browser-check.mjs; fi
if [[ "${1:-}" == --tts-latency ]]; then shift; exec .venv/bin/python scripts/tts-latency-check.py "$@"; fi
if [[ "${1:-}" == --stt ]]; then shift; exec .venv/bin/python scripts/stt-check.py "$@"; fi
if [[ "${1:-}" == --conversation ]]; then exec node scripts/conversation-check.mjs; fi
if [[ "${1:-}" == --tts-probe ]]; then
  if [[ -d .runtime/speech-models/hub ]]; then export HF_HUB_CACHE="$PWD/.runtime/speech-models/hub"; fi
  export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=2
  voice_repo="$(realpath "${JARVIS_TTS_REPO:-$PWD/../JarvisLuxTTS}")"
  exec "${JARVIS_TTS_PYTHON:-$voice_repo/.venv/bin/python}" scripts/tts-probe.py "$voice_repo"
fi
if [[ "${1:-}" == --hardware ]]; then
  node scripts/doctor.mjs
  source scripts/common.sh
  exec .venv/bin/python scripts/agent-check.py
fi
if [[ "${1:-}" == --agent ]]; then
  shift
  source scripts/common.sh
  exec .venv/bin/python scripts/agent-check.py "$@"
fi
if [[ "${1:-}" == --memory ]]; then
  source scripts/common.sh
  exec .venv/bin/python scripts/memory-check.py
fi
export PYTHONPATH="$PWD/backend${PYTHONPATH:+:$PYTHONPATH}"
if [[ -n "${JARVIS_TEST_PYTHON:-}" ]]; then
  "$JARVIS_TEST_PYTHON" -m pytest backend/tests -q
else
  .venv/bin/python -m pytest backend/tests -q
fi
npm --prefix frontend test
