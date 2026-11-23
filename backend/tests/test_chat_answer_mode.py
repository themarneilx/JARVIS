import json

import httpx
import pytest

from app.config import Settings
from app.hermes import HermesClient, chat_online_kinds
from app.information import Information, OnlineSettings
from app.main import create_app


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def test_answer_modes_preserve_local_requests_and_live_sources():
    question = 'Who is the current CEO of Apple?'
    assert chat_online_kinds(question) == set()
    assert chat_online_kinds(question, 'local') == set()
    assert chat_online_kinds(question, 'web') == {'search'}
    assert chat_online_kinds('Check the system.', 'web') == set()
    assert chat_online_kinds('Find my files in Downloads.', 'web') == set()
    assert chat_online_kinds('What is the weather today?', 'web') == {'weather'}
    assert chat_online_kinds('What time is it now?', 'local') == {'time'}


@pytest.mark.anyio
async def test_web_answer_cites_the_current_native_search_and_restores_on_reload(tmp_path):
    prompt = 'Who is the current CEO of Example Company?'
    result = {'source': 'jarvis_online/v1', 'covered': ['search'], 'browser_query': True,
              'results': [{'title': 'Example Company leadership', 'url': 'https://example.com/leadership'}]}
    rows = [
        {'role': 'user', 'content': prompt},
        {'role': 'tool', 'tool_name': 'jarvis_online', 'content': json.dumps(result)},
        {'role': 'assistant', 'content': 'The company lists Alex as CEO.'},
    ]
    def responder(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'data': rows})
        body = json.loads(request.content)
        assert 'Tools for this turn: jarvis_online.' in body['messages'][0]['content']
        return httpx.Response(200, text='data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n')

    agent = HermesClient(Settings(state_dir=tmp_path), httpx.MockTransport(responder))
    try:
        events = [event async for event in agent.stream(prompt, 'session', 'request', answer_mode='web')]
        answer = next(event['text'] for event in events if event['type'] == 'delta')
        assert answer.startswith('The company lists Alex as CEO.')
        assert 'https://example.com/leadership' in answer
        assert (await agent.history('session'))[-1]['text'] == answer
    finally:
        await agent.close()


@pytest.mark.anyio
async def test_local_mode_denies_plugin_egress_and_web_needs_browser_consent(tmp_path):
    class ProbeAgent:
        async def preflight(self):
            return {'connected': True}

        async def stream(self, text, session, request, *, answer_mode):
            permit = await client.get('/api/internal/online/search-permit', headers={'Authorization': 'Bearer ' + 'p'*40})
            if answer_mode == 'local':
                assert permit.status_code == 403
            else:
                assert permit.json() == {'enabled': True, 'query': text}
            yield {'type': 'done'}

    origin = 'http://127.0.0.1:8787'
    app = create_app(Settings(state_dir=tmp_path, login_token='l'*40, plugin_token='p'*40), hermes=ProbeAgent())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=origin) as client:
        login = await client.post('/api/auth/login', json={'token': 'l'*40}, headers={'Origin': origin})
        headers = {'Origin': origin, 'X-CSRF-Token': login.json()['csrf']}
        async def turn(mode, text='Who is the current CEO of Apple?'):
            return await client.post('/api/chat', json={'text': text, 'answer_mode': mode}, headers=headers)
        assert (await turn('web')).status_code == 403
        assert (await client.post('/api/information/settings', json={'enabled': True}, headers=headers)).status_code == 200
        assert (await turn('local', 'What is the weather today?')).status_code == 403
        for mode in ('local', 'web'):
            assert '"type": "done"' in (await turn(mode)).text


@pytest.mark.anyio
async def test_wikipedia_fallback_uses_fixed_endpoint_and_plain_text(tmp_path):
    def provider(request):
        assert request.url.host == 'en.wikipedia.org'
        assert request.url.path == '/w/rest.php/v1/search/page'
        assert request.url.params.get('q') == 'What is PyPI?'
        return httpx.Response(200, json={'pages': [
            {'title': 'Python Package Index', 'key': 'Python_Package_Index',
             'excerpt': '<span class="searchmatch">PyPI</span> is a package repository.'},
        ]})

    information = Information(tmp_path, transport=httpx.MockTransport(provider))
    try:
        with pytest.raises(ValueError, match='disabled'):
            await information.wikipedia_search('What is PyPI?')
        information.save(OnlineSettings(enabled=True))
        result = await information.wikipedia_search('What is PyPI?')
        assert result['provider'] == 'Wikipedia search fallback'
        assert result['results'][0]['url'] == 'https://en.wikipedia.org/wiki/Python_Package_Index'
        assert '<span' not in result['verified_summary']
    finally:
        await information.close()
