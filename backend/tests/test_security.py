import time
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport
from app.config import Settings
from app.main import create_app
from app.permissions import ActionPolicy, ApprovalStore

@pytest.fixture
def app(tmp_path):
    return create_app(Settings(state_dir=tmp_path, login_token="l" * 40, plugin_token="p" * 40))

@pytest.fixture
def anyio_backend():
    return 'asyncio'

pytestmark = pytest.mark.anyio

@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1:8787") as client:
        yield client

@pytest.fixture
async def auth(client):
    r = await client.post('/api/auth/login', json={'token': 'l' * 40}, headers={'origin': 'http://127.0.0.1:8787'})
    assert r.status_code == 200
    return {'origin': 'http://127.0.0.1:8787', 'x-csrf-token': r.json()['csrf']}

async def test_unauthorized(client):
    assert (await client.get('/api/telemetry')).status_code == 401
    assert (await client.get('/api/information/settings')).status_code==401
    assert (await client.get('/api/audio/processing')).status_code==401

async def test_processing_audio_fixed_private_file(client, auth, tmp_path):
    assets=tmp_path/'assets';assets.mkdir()
    path=assets/'processing-readout.wav'
    assert (await client.get('/api/audio/processing')).status_code==404
    path.write_bytes(b'RIFF-test-audio')
    response=await client.get('/api/audio/processing')
    assert response.status_code==200 and response.content==path.read_bytes()
    path.unlink();path.symlink_to(tmp_path/'login.token')
    assert (await client.get('/api/audio/processing')).status_code==404

async def test_plugin_can_read_time_but_cannot_change_online_settings(client):
    headers={'authorization':'Bearer '+'p'*40,'origin':'http://127.0.0.1:8787'}
    assert (await client.post('/api/internal/online/lookup',json={'kind':'time'},headers=headers)).status_code==200
    assert (await client.post('/api/information/settings',json={'enabled':True},headers=headers)).status_code==401
    assert (await client.get('/api/information/settings',headers=headers)).status_code==401

async def test_bad_origin(client):
    assert (await client.post('/api/auth/login', json={'token': 'l'*40}, headers={'origin': 'https://evil.example'})).status_code == 403

async def test_bad_host(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://evil.example') as client:
        assert (await client.get('/api/health')).status_code == 400

async def test_lan_host_and_origin_are_exact_and_cookie_is_secure(tmp_path):
    settings = Settings(state_dir=tmp_path, login_token='l'*40, lan_mode=True, lan_host='192.168.40.25')
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='https://192.168.40.25:8787') as client:
        accepted = await client.post('/api/auth/login', json={'token':'l'*40}, headers={'origin':'https://192.168.40.25:8787'})
        assert accepted.status_code == 200
        assert accepted.headers['set-cookie'].lower().find('secure') >= 0
        rejected = await client.post('/api/auth/login', json={'token':'l'*40}, headers={'origin':'https://192.168.40.26:8787'})
        assert rejected.status_code == 403
    async with AsyncClient(transport=ASGITransport(app=app), base_url='https://evil.example') as client:
        assert (await client.get('/api/health')).status_code == 400

async def test_csrf_required(client, auth):
    assert (await client.post('/api/information/settings',json={'enabled':True})).status_code==403
    assert (await client.post('/api/information/settings',json={'enabled':True},headers={'authorization':'Bearer '+'p'*40})).status_code==403
    assert (await client.post('/api/actions', json={'kind':'workspace', 'target':'2'})).status_code == 403

async def test_secrets_never_in_status(client, auth):
    r = await client.get('/api/status')
    assert r.status_code == 200
    assert 'l'*40 not in r.text and 'p'*40 not in r.text

async def test_plugin_token_cannot_approve(client):
    r = await client.post('/api/actions/x/resolve', json={'approve': True}, headers={'authorization':'Bearer ' + 'p'*40})
    assert r.status_code in (401,403)

def test_arguments_and_allowlist():
    policy = ActionPolicy(services=('ollama.service',), applications={'terminal': ('kitty',)})
    assert policy.command('service_restart', 'ollama.service') == ['systemctl', '--user', 'restart', 'ollama.service']
    assert policy.command('workspace', '2') == ['hyprctl','dispatch','workspace','2']
    for kind, target in [('service_restart','sshd.service'),('workspace','2;touch /tmp/pwned'),('launch','sh'),('process_stop','1')]:
        with pytest.raises(ValueError): policy.command(kind, target)

def test_approval_scoped_expired_and_one_use(tmp_path):
    store = ApprovalStore(tmp_path / 'approvals.db', ActionPolicy())
    a = store.propose('workspace', '2', 'Switch workspace')
    assert store.resolve(a['id'], False)['status'] == 'rejected'
    with pytest.raises(ValueError): store.resolve(a['id'], True)
    a = store.propose('workspace','3','Switch workspace', ttl=-1)
    with pytest.raises(ValueError): store.resolve(a['id'], True)

def test_unapproved_does_not_execute(tmp_path):
    calls=[]
    store = ApprovalStore(tmp_path / 'a.db', ActionPolicy(), executor=lambda argv: calls.append(argv) or {'ok':True})
    a = store.propose('workspace','2','Switch workspace')
    assert not calls
    assert store.resolve(a['id'],True)['status'] == 'executed'
    assert calls == [['hyprctl','dispatch','workspace','2']]
    with pytest.raises(ValueError): store.resolve(a['id'],True)

async def test_audio_invalid_magic(client, auth):
    assert (await client.post('/api/audio/transcribe', content=b'not webm', headers={**auth,'content-type':'audio/webm'})).status_code == 415

async def test_unsafe_agent_unavailable(client, auth):
    r=await client.post('/api/chat',json={'text':'hello'},headers=auth)
    assert r.status_code == 503

async def test_non_ascii_pairing_input_is_rejected_cleanly(client):
    response=await client.post('/api/auth/login',json={'token':'é'*40},headers={'origin':'http://127.0.0.1:8787'})
    assert response.status_code==401
