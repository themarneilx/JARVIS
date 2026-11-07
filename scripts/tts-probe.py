import faulthandler
import sys
import time
import importlib.metadata
import os
faulthandler.dump_traceback_later(90,exit=True)
start=time.monotonic()
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1]).resolve()))
print('Python:',sys.executable,sys.version,flush=True)
for package in ('torch','transformers','torchaudio','tokenizers','numpy','scikit-learn'):
    try:print(package,importlib.metadata.version(package),flush=True)
    except importlib.metadata.PackageNotFoundError:print(package,'no distribution metadata',flush=True)
from transformers.utils import is_torch_available
print('Transformers detects Torch:',is_torch_available(),'USE_TORCH:',os.getenv('USE_TORCH','unset'),'USE_TF:',os.getenv('USE_TF','unset'),flush=True)
try:
    from transformers.generation.utils import GenerationMixin
    print('Direct GenerationMixin import succeeded',flush=True)
except Exception:
    import traceback
    traceback.print_exc()
from audio import StreamJarvisTTS
print('Module imported in',round(time.monotonic()-start,2),flush=True)
engine=StreamJarvisTTS(device='cpu')
print('CPU engine initialized in',round(time.monotonic()-start,2),flush=True)
