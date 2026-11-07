import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile

import pytest


def setup_module_script():
    path=Path(__file__).resolve().parents[2]/'scripts/prepare-stt.py'
    spec=importlib.util.spec_from_file_location('parakeet_setup',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_download_requires_pinned_hash_and_size_before_publishing(tmp_path):
    setup=setup_module_script()
    data=b'official-model-fixture'
    path=tmp_path/'model.gguf'
    opener=lambda url,timeout: io.BytesIO(data)
    setup.download_verified('https://example.invalid/model',path,hashlib.sha256(data).hexdigest(),len(data),opener=opener)
    assert path.read_bytes()==data
    assert path.stat().st_mode&0o077==0
    path.unlink()
    with pytest.raises(ValueError): setup.download_verified('https://example.invalid/model',path,'0'*64,len(data),opener=opener)
    assert not path.exists() and not list(tmp_path.glob('*.part'))
    with pytest.raises(ValueError): setup.download_verified('https://example.invalid/model',path,hashlib.sha256(data).hexdigest(),2,opener=opener)
    assert not path.exists()


@pytest.mark.parametrize('kind',['path','symlink'])
def test_runtime_archive_cannot_write_outside_private_stage(tmp_path,kind):
    setup=setup_module_script()
    archive=tmp_path/'runtime.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        member=tarfile.TarInfo('../escape' if kind=='path' else 'bundle/link')
        if kind=='symlink': member.type=tarfile.SYMTYPE; member.linkname='../../escape'
        tar.addfile(member)
    with pytest.raises((ValueError,tarfile.FilterError)):
        setup.extract_runtime(archive,tmp_path/'runtime')
    assert not (tmp_path/'escape').exists()


def test_setup_pins_the_selected_nvidia_model():
    setup=setup_module_script()
    assert setup.MODEL_REPOSITORY=='nvidia/parakeet-tdt-0.6b-v3'
    assert setup.MODEL_SHA256=='e3880d0aaaaf2c308ea2c35016b2b895c423eb3fda924c1b463d1c19b7f4d32e'
