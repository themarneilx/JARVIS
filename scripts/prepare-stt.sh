#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
export UV_CACHE_DIR="$PWD/.runtime/uv-cache"
uv pip install --python .venv/bin/python 'av>=14,<20' 'numpy>=2,<3'
exec .venv/bin/python scripts/prepare-stt.py
