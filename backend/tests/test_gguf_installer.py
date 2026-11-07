import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import pytest

SCRIPT=Path(__file__).resolve().parents[2]/'scripts/gguf-installer/install_gguf.py'
spec=importlib.util.spec_from_file_location('gguf_installer',SCRIPT)
installer=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=installer
spec.loader.exec_module(installer)

def fixture_file(path):
    path.write_bytes(b'GGUF'+struct.pack('<IQQ',3,0,0))
    return path

class LocalService:
    def __init__(self,existing=()):self.existing=set(existing);self.uploads=[];self.created=[]
    def tags(self):return self.existing
    def upload(self,path,digest):
        assert digest=='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
        self.uploads.append(path)
    def create(self,payload):self.created.append(payload);self.existing.add(payload['model'])
    def show(self,name):return {'capabilities':['completion','tools'],'parameters':'num_ctx 64000','model_info':{'qwen3.context_length':262144},'details':{'quantization_level':'Q4_K_M'}}

def test_import_path_with_spaces_has_distinct_raw_and_jarvis_tags(tmp_path):
    file=fixture_file(tmp_path/'model with spaces.gguf')
    plan=installer.make_plan([str(file)],name='qwen35-2b:q4_k_m',jarvis=True)
    service=LocalService()
    result=installer.install(plan,service)
    assert service.created[0]['model']=='qwen35-2b:q4_k_m'
    assert service.created[0]['files']=={file.name:'sha256:'+hashlib.sha256(file.read_bytes()).hexdigest()}
    assert service.created[1]['model']=='jarvis-qwen35-2b-64k:q4_k_m'
    assert service.created[1]['files']==service.created[0]['files']
    assert 'from' not in service.created[1]
    assert service.created[1]['parameters']=={'num_ctx':64000}
    assert 'J.A.R.V.I.S.' in service.created[1]['system']
    assert result[0]['metadata_ready_for_hermes'] is True
    assert file.read_bytes().startswith(b'GGUF')

def test_any_existing_target_refuses_entire_batch_before_upload(tmp_path):
    file=fixture_file(tmp_path/'test.gguf')
    plan=installer.make_plan([str(file)],name='qwen:q4',jarvis=True)
    for existing in ('qwen:q4','jarvis-qwen-64k:q4'):
        service=LocalService([existing])
        with pytest.raises(ValueError,match='already exist'):installer.install(plan,service)
        assert not service.uploads and not service.created

def test_existing_tag_case_variants_are_not_overwritten(tmp_path):
    plan=installer.make_plan([str(fixture_file(tmp_path/'file.gguf'))],name='qwen:q4_k_m',jarvis=True)
    service=LocalService(['qwen:Q4_K_M'])
    with pytest.raises(ValueError,match='already exist'):installer.install(plan,service)
    assert not service.created and not service.uploads

def test_reports_ollamas_actual_tag_capitalization(tmp_path):
    class CanonicalTags(LocalService):
        def create(self,payload):
            self.created.append(payload)
            self.existing.add(payload['model'].replace(':q4_k_m',':Q4_K_M'))
    service=CanonicalTags()
    result=installer.install(installer.make_plan([str(fixture_file(tmp_path/'file.gguf'))],name='qwen:q4_k_m',jarvis=True),service)
    assert result[0]['model']=='qwen:Q4_K_M'
    assert result[0]['jarvis_model']=='jarvis-qwen-64k:Q4_K_M'

def test_explicit_replace_is_required_to_reuse_a_name(tmp_path):
    plan=installer.make_plan([str(fixture_file(tmp_path/'test.gguf'))],name='qwen:local')
    service=LocalService(['qwen:local'])
    installer.install(plan,service,replace=True)
    assert len(service.created)==1

def test_invalid_file_and_split_parts_are_refused(tmp_path):
    bad=tmp_path/'bad.gguf';bad.write_bytes(b'not a model')
    with pytest.raises(ValueError,match='GGUF'):installer.make_plan([str(bad)])
    shard=fixture_file(tmp_path/'model-00001-of-00002.gguf')
    with pytest.raises(ValueError,match='split'):installer.make_plan([str(shard)])

def test_normalized_name_collision_is_refused(tmp_path):
    fixture_file(tmp_path/'same name.gguf');fixture_file(tmp_path/'same-name.gguf')
    with pytest.raises(ValueError,match='same model name'):installer.make_plan([str(tmp_path)])

@pytest.mark.parametrize('name',['a\nPARAMETER num_ctx 1','https://host/model','../escape','-model','qwen:'])
def test_model_name_injection_refused(tmp_path,name):
    with pytest.raises(ValueError):installer.make_plan([str(fixture_file(tmp_path/'test.gguf'))],name=name)

@pytest.mark.parametrize('value',['https://127.0.0.1:11434','http://remote.example:11434','http://user:secret@localhost:11434','http://localhost:11434/v1','http://127.0.0.1:11434?key=x'])
def test_remote_or_credentialed_endpoints_refused(value):
    with pytest.raises(ValueError):installer.local_endpoint(value)

def test_loopback_custom_port_is_supported():
    assert installer.local_endpoint('127.0.0.1:11435')==('127.0.0.1',11435)

def test_context_limit_failure_preserves_imported_base_without_false_ready(tmp_path):
    class SmallContext(LocalService):
        def show(self,name):return {'model_info':{'model.context_length':32768},'capabilities':['completion','tools']}
    service=SmallContext()
    result=installer.install(installer.make_plan([str(fixture_file(tmp_path/'small.gguf'))],jarvis=True),service)
    assert result[0]['status']=='failed'
    assert len(service.created)==1
    assert result[0]['metadata_ready_for_hermes'] is False

def test_dry_run_never_contacts_ollama(tmp_path,monkeypatch):
    file=fixture_file(tmp_path/'safe file.gguf')
    monkeypatch.setattr(installer,'Ollama',lambda url:pytest.fail('Dry-run contacted Ollama'))
    assert installer.main(['--jarvis','--dry-run',str(file)])==0

def test_report_cannot_overwrite_input_or_existing_file(tmp_path):
    file=fixture_file(tmp_path/'safe.gguf');original=file.read_bytes()
    assert installer.main(['--report',str(file),str(file)])==1
    assert file.read_bytes()==original
    report=tmp_path/'existing.json';report.write_text('keep me')
    assert installer.main(['--report',str(report),str(file)])==1
    assert report.read_text()=='keep me'
