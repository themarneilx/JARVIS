import importlib.util
from pathlib import Path
from types import SimpleNamespace


def run_module():
    path = Path(__file__).resolve().parents[2] / 'scripts/run.py'
    spec = importlib.util.spec_from_file_location('jarvis_run_lan_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launcher_parses_explicit_lan_mode_and_address():
    module = run_module()
    args = module.build_parser().parse_args(['--lan', '--lan-host', '192.168.40.25', '--no-token'])
    assert args.lan is True
    assert args.lan_host == '192.168.40.25'
    assert args.no_token is True


def test_launcher_configures_private_certificate_paths_for_hermes(monkeypatch, tmp_path):
    module = run_module()
    args = SimpleNamespace(lan=True, lan_host='192.168.40.25', dev=False)
    monkeypatch.setattr(module, 'validate_lan_host', lambda host: host)
    monkeypatch.setattr(module, 'ensure_lan_certificate', lambda host, state: (state/'ca.crt', state/'server.crt', state/'server.key'))
    environment = {}

    result = module.configure_lan(args, environment, tmp_path)
    assert result == ('192.168.40.25', tmp_path/'ca.crt', tmp_path/'server.crt', tmp_path/'server.key')
    assert environment == {
        'JARVIS_LAN_MODE':'1',
        'JARVIS_LAN_HOST':'192.168.40.25',
        'JARVIS_LAN_CA_CERT':str(tmp_path/'ca.crt'),
        'JARVIS_LAN_CERT':str(tmp_path/'server.crt'),
        'JARVIS_LAN_KEY':str(tmp_path/'server.key'),
    }


def test_default_launcher_clears_inherited_lan_mode(monkeypatch, tmp_path):
    module = run_module()
    args = SimpleNamespace(lan=False, lan_host='', dev=False)
    environment = {
        'JARVIS_LAN_MODE':'1', 'JARVIS_LAN_HOST':'192.168.40.25',
        'JARVIS_LAN_CA_CERT':'/old/ca.crt', 'JARVIS_LAN_CERT':'/old/server.crt',
        'JARVIS_LAN_KEY':'/old/server.key',
    }
    assert module.configure_lan(args, environment, tmp_path) is None
    assert environment == {}


def test_backend_child_receives_tls_only_in_lan_mode():
    module = run_module()
    local = SimpleNamespace(lan_mode=False, lan_host='', lan_certfile=None, lan_keyfile=None)
    lan = SimpleNamespace(lan_mode=True, lan_host='192.168.40.25', lan_certfile=Path('/state/server.crt'), lan_keyfile=Path('/state/server.key'))
    assert module.backend_command(local) == ['bash','scripts/start.sh','--backend']
    assert module.backend_command(lan) == ['bash','scripts/start.sh','--backend','--lan-host','192.168.40.25','--tls-cert','/state/server.crt','--tls-key','/state/server.key']
