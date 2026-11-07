#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cat "${JARVIS_STATE_DIR:-.runtime}/login.token"
printf '\n'
