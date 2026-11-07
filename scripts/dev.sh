#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
exec .venv/bin/python scripts/run.py --dev "$@"
