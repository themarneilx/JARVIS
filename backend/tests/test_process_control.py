from pathlib import Path
import pytest
from app.process_control import validate_process,invocation


def fixture_process(tmp_path):
    root=tmp_path/'project';root.mkdir()
    proc=tmp_path/'proc/123';proc.mkdir(parents=True)
    (proc/'cwd').symlink_to(root,target_is_directory=True)
    (proc/'stat').write_text('123 (python process) '+' '.join(['S']+['0']*18+['4242']+['0']*5))
    argv=invocation('hermes')
    (proc/'cmdline').write_bytes(b'python\0'+b'\0'.join(a.encode() for a in argv)+b'\0')
    (proc/'environ').write_bytes(('HERMES_HOME='+str(root/'hermes/runtime')).encode()+b'\0')
    return root,proc,{'pid':123,'start_time':'4242','kind':'hermes','argv':argv}


def test_checks_process_generation_and_full_profile_before_stop(tmp_path):
    root,proc,record=fixture_process(tmp_path)
    validate_process(record,root,tmp_path/'proc')
    with pytest.raises(ValueError):validate_process({**record,'start_time':'previous-process'},root,tmp_path/'proc')
    (proc/'environ').write_bytes(b'HERMES_HOME=/home/user/.hermes\0')
    with pytest.raises(ValueError):validate_process(record,root,tmp_path/'proc')


def test_a_cli_from_the_same_workspace_is_not_a_gateway(tmp_path):
    root,proc,record=fixture_process(tmp_path)
    (proc/'cmdline').write_bytes(b'python\0-m\0hermes_cli.main\0chat\0')
    with pytest.raises(ValueError):validate_process(record,root,tmp_path/'proc')
