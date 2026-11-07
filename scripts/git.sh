#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec git --git-dir="$PWD/.runtime/project.git" --work-tree="$PWD" "$@"
