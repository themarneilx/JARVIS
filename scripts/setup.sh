#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PWD/.runtime/uv-cache}"
if [[ ! -x .venv/bin/python ]]; then uv venv --python 3.14 .venv; fi
uv pip install --python .venv/bin/python -e 'backend[test,stt]'
npm --prefix frontend ci
printf 'Backend and frontend dependencies installed. Hermes: bash scripts/install-hermes.sh\n'
