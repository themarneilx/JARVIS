"""Install pinned official Parakeet CPU assets inside the project only."""
import hashlib
import json
import os
from pathlib import Path
import platform
import tarfile
import tempfile
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
MODEL_REPOSITORY='nvidia/parakeet-tdt-0.6b-v3'
MODEL_REVISION='541d1f99c6b0c3cd0b11a95167540bb8edefd82b'
MODEL_FILE='parakeet-tdt-0.6b-v3.q8_0.gguf'
MODEL_SHA256='e3880d0aaaaf2c308ea2c35016b2b895c423eb3fda924c1b463d1c19b7f4d32e'
MODEL_SIZE=713975456
RUNTIME_VERSION='0.3.0'
RUNTIME_FILE='nemo-speech-0.3.0-linux-x86_64-cpu.tar.gz'
RUNTIME_SHA256='255f12b722ab15b2a38a51cf125d56e3fa97058b528f7e895b39d6a473deb06e'
RUNTIME_SIZE=9605101


def digest(path):
    with path.open('rb') as file: return hashlib.file_digest(file,'sha256').hexdigest()


def download_verified(url,path,expected_hash,expected_size,opener=urlopen):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.is_symlink(): raise ValueError('Download target cannot be a symbolic link')
    if path.is_file() and path.stat().st_size==expected_size and digest(path)==expected_hash:
        print('Verified cached asset:',path.name,flush=True)
        return
    partial=path.with_name(path.name+'.part')
    descriptor=os.open(partial,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        size=0
        sha=hashlib.sha256()
        with os.fdopen(descriptor,'wb') as file,opener(url,timeout=60) as response:
            while block:=response.read(1024*1024):
                size+=len(block)
                if size>expected_size: raise ValueError('Download exceeds the pinned asset size')
                sha.update(block)
                file.write(block)
                if size%(32*1024*1024)<len(block): print(f'{path.name}: {size//2**20}/{expected_size//2**20} MiB',flush=True)
        if size!=expected_size or sha.hexdigest()!=expected_hash:
            raise ValueError('Downloaded asset does not match its pinned size/SHA256')
        os.replace(partial,path)
    finally:
        partial.unlink(missing_ok=True)


def extract_runtime(archive,destination):
    destination=Path(destination)
    if destination.exists():
        marker=destination/'jarvis-release.sha256'
        if not destination.is_symlink() and marker.is_file() and marker.read_text().strip()==RUNTIME_SHA256:
            return
        raise ValueError('Runtime directory already exists without the expected release marker')
    destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with tempfile.TemporaryDirectory(prefix='.parakeet-stage-',dir=destination.parent) as temporary:
        stage=Path(temporary)
        with tarfile.open(archive,'r:gz') as tar:
            tar.extractall(stage,filter='data')
        libraries=list(stage.glob('**/libnemo_speech_asr_c.so'))
        if len(libraries)!=1: raise ValueError('Official ASR library was not found in the runtime bundle')
        # The release has one installation prefix containing bin, lib and include.
        prefix=libraries[0].parent.parent
        (prefix/'jarvis-release.sha256').write_text(RUNTIME_SHA256+'\n')
        os.replace(prefix,destination)


def main():
    if platform.system()!='Linux' or platform.machine() not in ('x86_64','AMD64'):
        raise SystemExit('This pinned Parakeet package targets Linux x86_64')
    state=ROOT/'.runtime'
    runtime_archive=state/'downloads'/RUNTIME_FILE
    model=state/'models/parakeet-tdt-0.6b-v3'/MODEL_FILE
    download_verified(f'https://github.com/NVIDIA/NeMo-Speech.cpp/releases/download/v{RUNTIME_VERSION}/{RUNTIME_FILE}',runtime_archive,RUNTIME_SHA256,RUNTIME_SIZE)
    extract_runtime(runtime_archive,state/'stt/nemo-speech-0.3.0-cpu')
    download_verified(f'https://huggingface.co/{MODEL_REPOSITORY}/resolve/{MODEL_REVISION}/{MODEL_FILE}',model,MODEL_SHA256,MODEL_SIZE)
    result={'repository':MODEL_REPOSITORY,'revision':MODEL_REVISION,'path':str(model),'sha256':MODEL_SHA256,'runtime':'NVIDIA/NeMo-Speech.cpp','runtime_version':RUNTIME_VERSION,'runtime_sha256':RUNTIME_SHA256,'device':'cpu','compute_type':'Q8_0'}
    path=state/'stt-models.json'
    path.write_text(json.dumps(result,indent=2)+'\n')
    path.chmod(0o600)
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__': main()
