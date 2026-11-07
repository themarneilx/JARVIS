#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PWD/.runtime/uv-cache}"
source_dir="$PWD/.runtime/hermes-agent"
reviewed_revision=74b2ed65e6564bfcafd29236e5fab2447a68fc76
if [[ ! -f "$source_dir/pyproject.toml" ]]; then
  git clone --depth 1 --filter=blob:none --no-checkout https://github.com/NousResearch/hermes-agent.git "$source_dir"
  git -C "$source_dir" fetch --depth 1 origin "$reviewed_revision"
  git -C "$source_dir" checkout --detach "$reviewed_revision"
fi
if [[ "$(git -C "$source_dir" rev-parse HEAD)" != "$reviewed_revision" ]]; then
  echo 'Hermes source differs from the reviewed revision; review the new API/plugin contracts before updating this installer.' >&2
  exit 1
fi
# Source installation, not an uninspected remote shell installer.
if [[ ! -x .runtime/hermes-venv/bin/python ]]; then uv venv --python 3.14 .runtime/hermes-venv; fi
uv pip install --python .runtime/hermes-venv/bin/python -e "$source_dir" 'aiohttp==3.14.5'
.runtime/hermes-venv/bin/hermes --version
printf 'Hermes installed locally. Run python3 scripts/prepare-profile.py after model discovery.\n'
