#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
export OLLAMA_HOST=http://127.0.0.1:11434
# Explicit setup command: this persists a separate tag, sharing the existing model layers.
ollama create jarvis-qwen35-4b-64k -f hermes/Ollama.Modelfile
.venv/bin/python - <<'PY'
import json
import os
from pathlib import Path
import shutil
import time
import yaml

path = Path(os.environ['HERMES_HOME']) / 'config.yaml'
config = yaml.safe_load(path.read_text())
backup = path.with_name(f'config.before-64k-{time.time_ns()}.yaml')
shutil.copyfile(path, backup)
backup.chmod(0o600)
config['model']['default'] = 'jarvis-qwen35-4b-64k:latest'
config['model']['context_length'] = 64000
config['model']['ollama_num_ctx'] = 64000
path.write_text(json.dumps(config, indent=2) + '\n')
print('Selected jarvis-qwen35-4b-64k:latest in the dedicated profile. Restart its gateway.')
PY
