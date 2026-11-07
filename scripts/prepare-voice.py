"""Prepare the selected reference transcription weights in the private project cache."""
import argparse
import json
from pathlib import Path
import sys

from huggingface_hub import HfApi, snapshot_download
from huggingface_hub.constants import HF_HUB_CACHE
from huggingface_hub.errors import LocalEntryNotFoundError

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--gpu', action='store_true', help='Prepare whisper-base for the original CUDA voice path')
gpu = parser.parse_args().gpu
model_name = 'openai/whisper-base' if gpu else 'openai/whisper-tiny'
cache = ROOT / '.runtime/speech-models/hub'
cache.mkdir(parents=True, exist_ok=True, mode=0o700)
existing = Path(HF_HUB_CACHE) / 'models--YatharthS--LuxTTS'
linked = cache / existing.name
if not linked.exists():
    if not existing.is_dir():
        sys.exit('Cached LuxTTS weights are missing. Download the selected voice models explicitly first.')
    linked.symlink_to(existing.resolve(), target_is_directory=True)
model_cache = cache / ('models--' + model_name.replace('/', '--'))
path = None
if model_cache.is_symlink():
    try:
        path = snapshot_download(model_name, cache_dir=str(cache), local_files_only=True)
        revision = Path(path).name
    except LocalEntryNotFoundError:
        # A partial external cache must never become the destination of a setup download.
        model_cache.unlink()
if path is None:
    revision = HfApi().model_info(model_name).sha
    path = snapshot_download(model_name, revision=revision, cache_dir=str(cache), allow_patterns=['*.json', '*.txt', 'model.safetensors'])
    reference = model_cache / 'refs/main'
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text(revision)
result = {'repository': model_name, 'revision': revision, 'cache': str(cache), 'snapshot': path, 'voice': 'original JarvisLuxTTS', 'device': 'cuda' if gpu else 'cpu'}
(ROOT / ('.runtime/voice-models-gpu.json' if gpu else '.runtime/voice-models.json')).write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
