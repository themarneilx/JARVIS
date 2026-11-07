#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
if [[ -z "${HERMES_PYTHON:-}" || -z "${HERMES_SOURCE:-}" ]]; then
  python3 scripts/runtime.py >&2
  exit 1
fi
if [[ ! -f "$HERMES_HOME/config.yaml" ]]; then echo 'Run python3 scripts/prepare-profile.py first.' >&2; exit 1; fi
.venv/bin/python scripts/sync-plugin.py
export PYTHONPATH="$HERMES_SOURCE:$PYTHONPATH"
export HERMES_DISABLE_LAZY_INSTALLS=1
export XDG_STATE_HOME="${XDG_STATE_HOME:-$PWD/.runtime/xdg-state}"
# The dedicated home scopes the same identity and native memory for CLI and API sessions.
if [[ "${1:-}" == cli ]]; then shift; exec "$HERMES_PYTHON" -m hermes_cli.main "$@"; fi
.venv/bin/python scripts/record-process.py hermes "$$"
exec "$HERMES_PYTHON" -m hermes_cli.main gateway run
