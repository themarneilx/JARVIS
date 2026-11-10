from httpx import ASGITransport, AsyncClient
import pytest

from app.config import Settings
from app.main import create_app


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend(): return 'asyncio'


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(state_dir=tmp_path, login_token='l'*40, plugin_token='p'*40))


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://127.0.0.1:8787') as client:
        yield client


@pytest.fixture
async def auth(client):
    response = await client.post('/api/auth/login', json={'token': 'l'*40}, headers={'origin': 'http://127.0.0.1:8787'})
    assert response.status_code == 200
    return {'origin': 'http://127.0.0.1:8787', 'x-csrf-token': response.json()['csrf']}


def spec(**values):
    return {'name': 'Reviewed test shortcut', 'trigger': 'manual', 'message': 'A short test notification.', 'chime': False, **values}


async def create(client, auth, **values):
    result = await client.post('/api/shortcuts', json={'spec': spec(**values), 'authorized': True}, headers=auth)
    assert result.status_code == 200, result.text
    return result.json()


async def test_browser_credentials_and_explicit_authorization_required(client, auth, app):
    anonymous = AsyncClient(transport=ASGITransport(app=app), base_url='http://127.0.0.1:8787')
    async with anonymous:
        assert (await anonymous.get('/api/shortcuts')).status_code == 401
        assert (await anonymous.get('/api/shortcuts/stream')).status_code == 401
        assert (await anonymous.post('/api/shortcuts', json={'spec': spec(), 'authorized': True}, headers=auth)).status_code == 401
    assert (await client.post('/api/shortcuts', json={'spec': spec(), 'authorized': True})).status_code == 403
    assert (await client.post('/api/shortcuts', json={'spec': spec(), 'authorized': False}, headers=auth)).status_code == 403
    assert (await client.post('/api/shortcuts', json={'spec': spec(), 'authorized': True}, headers={**auth, 'origin': 'https://evil.example'})).status_code == 403


async def test_native_plugin_can_only_list_and_propose(client, app):
    plugin = {'authorization': 'Bearer '+'p'*40}
    assert (await client.get('/api/internal/shortcuts', headers=plugin)).status_code == 200
    assert (await client.get('/api/shortcuts', headers=plugin)).status_code == 401
    result = await client.post('/api/internal/shortcuts/proposals', json=spec(), headers=plugin)
    assert result.status_code == 200 and result.json()['status'] == 'pending'
    assert app.state.shortcuts.list() == []
    assert (await client.post('/api/internal/shortcuts/proposals', json={**spec(), 'authorized': True}, headers=plugin)).status_code == 422
    assert (await client.post('/api/shortcuts', json={'spec': spec(), 'authorized': True}, headers=plugin)).status_code == 401


async def test_shortcut_proposal_uses_existing_exact_code_review(client, auth, app):
    proposal = (await client.post('/api/internal/shortcuts/proposals', json=spec(), headers={'authorization': 'Bearer '+'p'*40})).json()
    tickets = (await client.get('/api/reviews')).json()
    ticket = next(row for row in tickets if row['source'] == 'shortcut')
    assert ticket['proposal_id'] == proposal['id'] and 'Output:' in ticket['effect']
    wrong = '0000' if ticket['code'] != '0000' else '1111'
    assert (await client.post('/api/reviews/'+ticket['id']+'/resolve', json={'approve': True, 'code': wrong}, headers=auth)).status_code == 400
    assert app.state.shortcuts.list() == []
    result = await client.post('/api/reviews/'+ticket['id']+'/resolve', json={'approve': True, 'code': ticket['code']}, headers=auth)
    assert result.status_code == 200 and result.json()['kind'] == 'shortcut'
    assert app.state.shortcuts.list()[0]['enabled'] is True
    assert (await client.post('/api/reviews/'+ticket['id']+'/resolve', json={'approve': True, 'code': ticket['code']}, headers=auth)).status_code == 400


async def test_edit_disable_and_remove_require_current_revision(client, auth, app):
    saved = await create(client, auth)
    bad = await client.put('/api/shortcuts/'+saved['id'], json={'spec': spec(name='Changed'), 'authorized': False, 'revision': saved['revision']}, headers=auth)
    assert bad.status_code == 403
    event = (await client.post('/api/shortcuts/'+saved['id']+'/run', json={}, headers=auth)).json()
    saved = (await client.post('/api/shortcuts/'+saved['id']+'/enabled', json={'enabled': False, 'revision': saved['revision']}, headers=auth)).json()
    assert app.state.shortcuts.event(event['id'])['status'] == 'cancelled'
    assert (await client.delete('/api/shortcuts/'+saved['id']+'?revision=1', headers=auth)).status_code == 400
    assert (await client.delete('/api/shortcuts/'+saved['id']+'?revision='+str(saved['revision']), headers=auth)).status_code == 200
    assert (await client.get('/api/shortcuts')).json()['shortcuts'] == []


async def test_browser_claim_is_single_use_and_does_not_reach_desktop_delivery(client, auth, app):
    saved = await create(client, auth)
    event = (await client.post('/api/shortcuts/'+saved['id']+'/run', json={}, headers=auth)).json()
    claim = (await client.post('/api/shortcuts/events/'+event['id']+'/claim', json={}, headers=auth)).json()
    assert claim['event']['status'] == 'preparing'
    assert (await client.post('/api/shortcuts/events/'+event['id']+'/claim', json={}, headers=auth)).status_code == 400
    assert (await client.post('/api/shortcuts/events/'+event['id']+'/finish', json={'claim_id': 'x'*24, 'status': 'delivered'}, headers=auth)).status_code == 400
    assert (await client.post('/api/shortcuts/events/'+event['id']+'/finish', json={'claim_id': claim['claim_id'], 'status': 'muted'}, headers=auth)).status_code == 200
    assert app.state.shortcuts.event(event['id'])['status'] == 'muted'


async def test_browser_cannot_claim_explicit_desktop_shortcut(client, auth, app, monkeypatch):
    monkeypatch.setattr(app.state.shortcut_runner, 'capabilities', lambda: {'desktop_audio_available': True})
    saved = await create(client, auth, delivery='desktop')
    event = (await client.post('/api/shortcuts/'+saved['id']+'/run', json={}, headers=auth)).json()
    assert (await client.post('/api/shortcuts/events/'+event['id']+'/claim', json={}, headers=auth)).status_code == 403


async def test_weather_creation_requires_saved_location_and_consent(client, auth):
    response = await client.post('/api/shortcuts', json={'spec': spec(weather=True), 'authorized': True}, headers=auth)
    assert response.status_code == 400 and 'disabled' in response.json()['detail']


async def test_active_announcement_blocks_new_chat_stt_and_speech_server_side(client, auth):
    saved = await create(client, auth)
    event = (await client.post('/api/shortcuts/'+saved['id']+'/run', json={}, headers=auth)).json()
    assert (await client.post('/api/shortcuts/events/'+event['id']+'/claim', json={}, headers=auth)).status_code == 200
    assert (await client.post('/api/chat', json={'text': 'hello'}, headers=auth)).status_code == 409
    assert (await client.post('/api/audio/plan', json={'text': 'hello'}, headers=auth)).status_code == 409
    assert (await client.post('/api/audio/transcribe', content=b'invalid', headers={**auth, 'content-type': 'audio/webm'})).status_code == 409
    assert (await client.post('/api/shortcuts/events/'+event['id']+'/stop', json={}, headers=auth)).status_code == 200


async def test_logout_cancels_only_its_claimed_browser_event(client, auth, app):
    saved = await create(client, auth)
    event = (await client.post('/api/shortcuts/'+saved['id']+'/run', json={}, headers=auth)).json()
    await client.post('/api/shortcuts/events/'+event['id']+'/claim', json={}, headers=auth)
    assert (await client.post('/api/auth/logout', json={}, headers=auth)).status_code == 200
    assert app.state.shortcuts.event(event['id'])['status'] == 'cancelled'
    assert app.state.shortcuts.get(saved['id'])['enabled'] is True


async def test_shortcut_stream_notifies_connected_tabs_of_cancellation(client, auth, app):
    from starlette.requests import Request
    route = next(route for group in app.routes for route in getattr(getattr(group, 'original_router', None), 'routes', [])
                 if getattr(route, 'path', '') == '/api/shortcuts/stream')
    async def receive(): return {'type': 'http.request', 'body': b'', 'more_body': False}
    request = Request({'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.3'}, 'http_version': '1.1',
                       'method': 'GET', 'scheme': 'http', 'path': '/api/shortcuts/stream', 'raw_path': b'/api/shortcuts/stream',
                       'query_string': b'', 'headers': [], 'server': ('127.0.0.1', 8787), 'client': ('127.0.0.1', 1234)}, receive)
    response = await route.endpoint(request)
    stream = response.body_iterator
    try:
        ready = await anext(stream)
        assert 'ready' in (ready.decode() if isinstance(ready, bytes) else ready)
        app.state.shortcut_runner.publish_cancel('event-from-another-tab')
        notice = await anext(stream)
        notice = notice.decode() if isinstance(notice, bytes) else notice
        assert '"type":"cancel"' in notice
        assert '"event_id":"event-from-another-tab"' in notice
    finally:
        await stream.aclose()
