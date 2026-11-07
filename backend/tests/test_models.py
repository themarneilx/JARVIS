import asyncio
import json
import stat

import httpx
import pytest

from app.config import Settings
from app.hermes import HermesClient, HermesError, SAFE_TOOLS
from app.models import ModelError, ModelManager, prepared_name
from test_agent import safe_settings


GEMMA = 'hf.co/HauhauCS/Gemma-4-E4B-Uncensored-HauhauCS-Aggressive:Q4_K_M'
READY = 'jarvis-qwen35-4b-64k:latest'


def metadata(context=64000, limit=262144, tools=True, **extra):
    return {'parameters': f'temperature 0.7\nnum_ctx {context}',
            'capabilities': ['completion', 'tools'] if tools else ['completion'],
            'model_info': {'gemma4.context_length': limit},
            'details': {'parameter_size': '8B', 'quantization_level': 'Q4_K_M'}, **extra}


def model_transport(models, calls=None):
    def handler(request):
        if calls is not None:
            calls.append((request.url.path, json.loads(request.content) if request.content else None))
        assert 'authorization' not in request.headers
        if request.url.path == '/api/tags':
            return httpx.Response(200, json={'models': [{'name': name, 'digest': f'digest-{i}', 'size': 1234} for i, name in enumerate(models)]})
        if request.url.path == '/api/show':
            name = json.loads(request.content)['model']
            return httpx.Response(200, json=models[name]) if name in models else httpx.Response(404)
        if request.url.path == '/api/create':
            body = json.loads(request.content)
            assert body['from'] == GEMMA
            assert body['parameters'] == {'num_ctx': 64000}
            assert body['stream'] is False
            models[body['model']] = metadata()
            return httpx.Response(200, json={'status': 'success'})
        pytest.fail(f'Unexpected model API call: {request.url.path}')
    return httpx.MockTransport(handler)


def test_catalog_distinguishes_metadata_readiness_from_unverified_runtime(tmp_path):
    async def run():
        manager = ModelManager(safe_settings(tmp_path), transport=model_transport({
            GEMMA: metadata(context=4096), READY: metadata(), 'remote:latest': metadata(remote_host='https://ollama.com'),
            'small:latest': metadata(limit=32768), 'no-tools:latest': metadata(tools=False)}))
        try:
            result = await manager.catalog()
            rows = {row['name']: row for row in result['models']}
            assert result['required_context'] == 64000
            assert rows[GEMMA]['can_prepare'] and not rows[GEMMA]['ready']
            assert rows[GEMMA]['prepare_model'] == prepared_name(GEMMA)
            assert rows[READY]['ready'] and not rows[READY]['can_prepare']
            assert not rows['remote:latest']['ready'] and not rows['remote:latest']['can_prepare']
            assert not rows['small:latest']['ready'] and not rows['small:latest']['can_prepare']
            assert not rows['no-tools:latest']['ready'] and not rows['no-tools:latest']['can_prepare']
            assert rows[READY]['runtime_verified'] is False
        finally:
            await manager.close()
    asyncio.run(run())


@pytest.mark.parametrize('name', [GEMMA + '\nPARAMETER num_ctx 1', 'https://evil.example/model', '../escape:latest', 'model\x00:latest', '-bad:latest'])
def test_rejects_untrusted_model_names_before_any_request(tmp_path, name):
    async def run():
        calls = []
        manager = ModelManager(safe_settings(tmp_path), transport=model_transport({}, calls))
        try:
            with pytest.raises(ModelError):
                await manager.select(name)
            with pytest.raises(ModelError):
                await manager.prepare(name)
            assert calls == []
        finally:
            await manager.close()
    asyncio.run(run())


def test_selection_requires_exact_installed_ready_tag_and_persists_privately(tmp_path):
    async def run():
        settings = safe_settings(tmp_path)
        original = (settings.hermes_home / 'config.yaml').read_bytes()
        manager = ModelManager(settings, transport=model_transport({GEMMA: metadata(context=4096), READY: metadata()}))
        try:
            for name in ['uninstalled:latest', GEMMA]:
                with pytest.raises(ModelError):
                    await manager.select(name)
            row = await manager.select(READY)
            assert row['name'] == READY and row['ready']
            assert manager.selected_model == READY
            path = settings.state_dir / 'model-selection.json'
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
            assert json.loads(path.read_text()) == {'version': 1, 'model': READY}
            restored = ModelManager(settings, transport=model_transport({READY: metadata()}))
            try:
                assert restored.selected_model == READY
            finally:
                await restored.close()
            assert (settings.hermes_home / 'config.yaml').read_bytes() == original
        finally:
            await manager.close()
    asyncio.run(run())


def test_prepare_creates_separate_fixed_context_alias_without_selecting_or_inference(tmp_path):
    async def run():
        calls = []
        models = {GEMMA: metadata(context=4096)}
        manager = ModelManager(safe_settings(tmp_path), transport=model_transport(models, calls))
        try:
            row = await manager.prepare(GEMMA)
            assert row['name'] == prepared_name(GEMMA) and row['ready']
            assert row['name'] != GEMMA
            assert models[GEMMA]['parameters'].endswith('num_ctx 4096')
            assert manager.selected_model is None
            assert not (tmp_path / 'model-selection.json').exists()
            assert all(path in ('/api/tags', '/api/show', '/api/create') for path, _ in calls)
            assert sum(path == '/api/create' for path, _ in calls) == 1
            await manager.prepare(GEMMA)
            assert sum(path == '/api/create' for path, _ in calls) == 1
        finally:
            await manager.close()
    asyncio.run(run())


def test_prepare_does_not_overwrite_existing_unready_alias(tmp_path):
    async def run():
        calls = []
        manager = ModelManager(safe_settings(tmp_path), transport=model_transport({GEMMA: metadata(context=4096), prepared_name(GEMMA): metadata(context=4096)}, calls))
        try:
            with pytest.raises(ModelError, match='already exists'):
                await manager.prepare(GEMMA)
            assert not any(path == '/api/create' for path, _ in calls)
        finally:
            await manager.close()
    asyncio.run(run())


def test_selection_state_symlink_is_refused(tmp_path):
    settings = safe_settings(tmp_path)
    target = tmp_path / 'external.json'
    target.write_text(json.dumps({'version': 1, 'model': READY}))
    (tmp_path / 'model-selection.json').symlink_to(target)
    with pytest.raises(ModelError, match='selection'):
        ModelManager(settings)


def test_hermes_preflight_validates_selected_model_and_keeps_profile_checks(tmp_path):
    seen = []
    def handler(request):
        if request.url.path == '/api/show':
            assert 'authorization' not in request.headers
            seen.append(json.loads(request.content)['model'])
            return httpx.Response(200, json=metadata(context=4096))
        if request.url.path == '/v1/capabilities':
            return httpx.Response(200, json={})
        return httpx.Response(200, json={'data': [{'enabled': True, 'tools': sorted(SAFE_TOOLS)}]})
    async def run():
        client = HermesClient(safe_settings(tmp_path), httpx.MockTransport(handler))
        try:
            client.set_model(READY)
            with pytest.raises(HermesError, match='64,000'):
                await client.preflight()
            assert seen == [READY]
        finally:
            await client.close()
    asyncio.run(run())


def test_hermes_stream_pins_selected_local_model_and_custom_provider(tmp_path):
    def handler(request):
        body = json.loads(request.content)
        assert body['model'] == READY
        assert body['provider'] == 'custom'
        assert not any(key in body for key in ('base_url', 'api_key', 'model_routes'))
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"Hello."},"finish_reason":"stop"}]}\n\n')
    async def run():
        client = HermesClient(safe_settings(tmp_path), httpx.MockTransport(handler))
        try:
            client.checked_at = 100
            client.set_model(READY)
            assert client.checked_at == 0
            result = [event async for event in client.stream('Hi', 'new-session', 'request')]
            assert result[-1]['type'] == 'done'
        finally:
            await client.close()
    asyncio.run(run())


@pytest.mark.parametrize('details', [metadata(remote_model='gemma:cloud'), metadata(tools=False), metadata(limit=32768)])
def test_disallowed_metadata_cannot_select_or_prepare(tmp_path, details):
    async def run():
        calls = []
        manager = ModelManager(safe_settings(tmp_path), transport=model_transport({GEMMA: details}, calls))
        try:
            with pytest.raises(ModelError):
                await manager.select(GEMMA)
            with pytest.raises(ModelError):
                await manager.prepare(GEMMA)
            assert manager.selected_model is None
            assert not any(path == '/api/create' for path, _ in calls)
        finally:
            await manager.close()
    asyncio.run(run())


@pytest.mark.parametrize('permissions', [0o644, 0o666])
def test_selection_state_with_public_permissions_is_refused(tmp_path, permissions):
    settings = safe_settings(tmp_path)
    path = settings.state_dir / 'model-selection.json'
    path.write_text(json.dumps({'version': 1, 'model': READY}))
    path.chmod(permissions)
    with pytest.raises(ModelError, match='selection'):
        ModelManager(settings)


@pytest.mark.parametrize('details', [[], None, metadata(capabilities=None)])
def test_selected_hermes_metadata_errors_fail_closed(tmp_path, details):
    def handler(request):
        if request.url.path == '/api/show':
            return httpx.Response(200, json=details) if details is not None else httpx.Response(200, text='null')
        if request.url.path == '/v1/capabilities':
            return httpx.Response(200, json={})
        return httpx.Response(200, json={'data': [{'enabled': True, 'tools': sorted(SAFE_TOOLS)}]})
    async def run():
        client = HermesClient(safe_settings(tmp_path), httpx.MockTransport(handler))
        try:
            client.set_model(READY)
            with pytest.raises(HermesError):
                await client.preflight()
            assert client.checked_at == 0
        finally:
            await client.close()
    asyncio.run(run())
