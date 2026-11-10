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


def test_backend_invocation_pins_exact_lan_host_and_tls_files():
    argv=invocation('backend',8787,host='192.168.40.25',tls_cert='/private/lan.crt',tls_key='/private/lan.key')
    assert argv == ['-m','uvicorn','app.main:create_app','--factory','--host','192.168.40.25','--port','8787','--no-access-log','--ssl-certfile','/private/lan.crt','--ssl-keyfile','/private/lan.key']


def test_lan_process_record_rejects_changed_certificate_arguments(tmp_path):
    root=tmp_path/'project';root.mkdir()
    proc=tmp_path/'proc/456';proc.mkdir(parents=True)
    (proc/'cwd').symlink_to(root,target_is_directory=True)
    argv=invocation('backend',8787,host='192.168.40.25',tls_cert='/private/lan.crt',tls_key='/private/lan.key')
    (proc/'stat').write_text('456 (python process) '+' '.join(['S']+['0']*18+['7890']+['0']*5))
    (proc/'cmdline').write_bytes(b'python\0'+b'\0'.join(a.encode() for a in argv)+b'\0')
    (proc/'environ').write_bytes(('HERMES_HOME='+str(root/'hermes/runtime')).encode()+b'\0')
    record={'pid':456,'start_time':'7890','kind':'backend','port':8787,'host':'192.168.40.25','tls_cert':'/private/lan.crt','tls_key':'/private/lan.key','argv':argv}
    validate_process(record,root,tmp_path/'proc')
    (proc/'cmdline').write_bytes(b'python\0'+b'\0'.join(a.encode() for a in argv[:-1]+['/private/other.key'])+b'\0')
    with pytest.raises(ValueError):validate_process(record,root,tmp_path/'proc')
