import importlib
import importlib.util
import shutil
import ssl
import subprocess

import pytest


def lan_module():
    if importlib.util.find_spec('app.lan') is None:
        pytest.fail('app.lan LAN security helpers are not implemented')
    return importlib.import_module('app.lan')


@pytest.mark.parametrize('address', [
    '0.0.0.0', '127.0.0.1', '169.254.20.1', '8.8.8.8', '224.0.0.1',
    '192.168.1.1/24', '::1', 'not-an-address',
])
def test_lan_host_rejects_non_private_ipv4(address, monkeypatch):
    module = lan_module()
    monkeypatch.setattr(module, '_is_assigned', lambda _host: True)
    with pytest.raises(ValueError):
        module.validate_lan_host(address)


def test_lan_host_must_be_assigned_to_this_machine(monkeypatch):
    module = lan_module()
    monkeypatch.setattr(module, '_is_assigned', lambda _host: False)
    with pytest.raises(ValueError, match='assigned'):
        module.validate_lan_host('192.168.40.25')


def test_lan_host_accepts_assigned_private_ipv4(monkeypatch):
    module = lan_module()
    monkeypatch.setattr(module, '_is_assigned', lambda _host: True)
    assert module.validate_lan_host('192.168.40.25') == '192.168.40.25'


def test_generated_lan_certificate_is_private_signed_and_ip_matched(tmp_path):
    if not shutil.which('openssl'):
        pytest.skip('OpenSSL is required to generate LAN certificates')
    module = lan_module()
    ca_cert, cert, key = module.ensure_lan_certificate('192.168.40.25', tmp_path)

    assert (tmp_path / 'certs').stat().st_mode & 0o777 == 0o700
    assert ca_cert.stat().st_mode & 0o777 == 0o644
    assert cert.stat().st_mode & 0o777 == 0o644
    assert key.stat().st_mode & 0o777 == 0o600
    assert subprocess.run(['openssl', 'verify', '-CAfile', str(ca_cert), str(cert)], capture_output=True).returncode == 0
    assert subprocess.run(['openssl', 'x509', '-in', str(cert), '-noout', '-checkip', '192.168.40.25'], capture_output=True).returncode == 0
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))


def test_lan_certificate_is_reused_for_same_address(tmp_path):
    if not shutil.which('openssl'):
        pytest.skip('OpenSSL is required to generate LAN certificates')
    module = lan_module()
    first = module.ensure_lan_certificate('192.168.40.25', tmp_path)
    first_bytes = tuple(path.read_bytes() for path in first)
    second = module.ensure_lan_certificate('192.168.40.25', tmp_path)
    assert tuple(path.read_bytes() for path in second) == first_bytes


def test_lan_certificate_refuses_symlinked_runtime_directory(tmp_path):
    module = lan_module()
    external = tmp_path / 'outside'
    external.mkdir()
    (tmp_path / 'certs').symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        module.ensure_lan_certificate('192.168.40.25', tmp_path)


def test_lan_settings_pin_secure_origin_host_and_cookie(tmp_path):
    from app.config import Settings

    settings = Settings(state_dir=tmp_path, lan_mode=True, lan_host='192.168.40.25')
    assert settings.origins == ('https://192.168.40.25:8787',)
    assert settings.allowed_hosts == ('192.168.40.25',)
    assert settings.bind_host == '192.168.40.25'
    assert settings.secure_cookie is True


def test_lan_settings_reject_wildcard_and_public_hosts(tmp_path):
    from app.config import Settings

    for host in ('0.0.0.0', '8.8.8.8', '127.0.0.1'):
        with pytest.raises(ValueError):
            Settings(state_dir=tmp_path / host.replace('.', '_'), lan_mode=True, lan_host=host)


def test_loopback_settings_keep_non_secure_cookie_and_local_origins(tmp_path):
    from app.config import Settings

    settings = Settings(state_dir=tmp_path)
    assert settings.bind_host == '127.0.0.1'
    assert settings.secure_cookie is False
    assert all(origin.startswith('http://') for origin in settings.origins)


def test_lan_start_requires_one_explicit_private_host():
    module = lan_module()
    assert module.validate_start_options(True, '192.168.40.25', False) == '192.168.40.25'
    with pytest.raises(ValueError, match='--lan-host'):
        module.validate_start_options(True, '', False)
    with pytest.raises(ValueError, match='--lan'):
        module.validate_start_options(False, '192.168.40.25', False)
    with pytest.raises(ValueError, match='production'):
        module.validate_start_options(True, '192.168.40.25', True)
