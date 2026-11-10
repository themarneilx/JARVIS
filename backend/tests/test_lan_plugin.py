import importlib.util
from pathlib import Path
import ssl
import urllib.request

from app.lan import ensure_lan_certificate


def plugin_module():
    path = Path(__file__).resolve().parents[2] / 'hermes/plugins/jarvis_desktop/__init__.py'
    spec = importlib.util.spec_from_file_location('jarvis_desktop_lan_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Response:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, _limit): return b'{"ok":true}'


def test_plugin_uses_https_local_ca_and_bearer_in_lan_mode(tmp_path, monkeypatch):
    ca, _cert, _key = ensure_lan_certificate('192.168.40.25', tmp_path)
    monkeypatch.setenv('JARVIS_LAN_MODE', '1')
    monkeypatch.setenv('JARVIS_LAN_HOST', '192.168.40.25')
    monkeypatch.setenv('JARVIS_LAN_CA_CERT', str(ca))
    monkeypatch.setenv('JARVIS_PORT', '8787')
    monkeypatch.setenv('JARVIS_BACKEND_URL', 'http://127.0.0.1:8787')
    monkeypatch.setenv('JARVIS_PLUGIN_TOKEN', 'plugin-test-token')
    captured = {}

    class Opener:
        def open(self, request, timeout):
            captured['url'] = request.full_url
            captured['authorization'] = request.get_header('Authorization')
            captured['timeout'] = timeout
            return Response()

    def build_opener(*handlers):
        captured['handlers'] = handlers
        return Opener()

    monkeypatch.setattr(urllib.request, 'build_opener', build_opener)
    assert plugin_module().call('/telemetry', {}) == '{"ok":true}'
    assert captured['url'] == 'https://192.168.40.25:8787/api/internal/telemetry'
    assert captured['authorization'] == 'Bearer plugin-test-token'
    https_handler = next(handler for handler in captured['handlers'] if isinstance(handler, urllib.request.HTTPSHandler))
    assert https_handler._context.verify_mode == ssl.CERT_REQUIRED
    assert https_handler._context.check_hostname is True
    assert https_handler._context.minimum_version >= ssl.TLSVersion.TLSv1_2
    assert https_handler._context.get_ca_certs()


def test_plugin_fails_closed_when_lan_ca_is_missing(monkeypatch):
    monkeypatch.setenv('JARVIS_LAN_MODE', '1')
    monkeypatch.setenv('JARVIS_LAN_HOST', '192.168.40.25')
    monkeypatch.setenv('JARVIS_LAN_CA_CERT', '/nonexistent/jarvis-lan-ca.crt')
    opened = []
    monkeypatch.setattr(urllib.request, 'build_opener', lambda *_: opened.append(True))
    result = plugin_module().call('/telemetry', {})
    assert 'error' in result
    assert not opened
