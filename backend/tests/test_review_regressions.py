import asyncio,json
import httpx
import pytest
from app.config import Settings
from app.hermes import HermesClient,HermesError
from app.main import create_app


def test_error_finish_reason_cannot_be_reported_as_success(tmp_path):
    async def run():
        transport=httpx.MockTransport(lambda r:httpx.Response(200,text='data: {"choices":[{"delta":{},"finish_reason":"error"}]}\n\ndata: [DONE]\n\n'))
        client=HermesClient(Settings(state_dir=tmp_path,hermes_key='x'),transport)
        try:
            with pytest.raises(HermesError):[e async for e in client.stream('hi','session','request')]
        finally:await client.close()
    asyncio.run(run())


def test_chat_completion_id_is_stoppable_run_id(tmp_path):
    async def run():
        transport=httpx.MockTransport(lambda r:httpx.Response(200,text='data: {"id":"chatcmpl-123abc","choices":[{"delta":{"content":"hello"}}]}\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'))
        client=HermesClient(Settings(state_dir=tmp_path,hermes_key='x'),transport)
        try:assert {'type':'run','run_id':'chatcmpl-123abc'} in [e async for e in client.stream('hi','session','request')]
        finally:await client.close()
    asyncio.run(run())


def test_old_session_cannot_relabel_its_memory_epoch(tmp_path):
    class Agent:
        capabilities={}
        async def preflight(self):return {'connected':True}
        async def close(self):pass
        async def stop(self,run):return True
        async def stream(self,*args):yield {'type':'done'}
    async def run():
        settings=Settings(state_dir=tmp_path,login_token='test-login')
        app=create_app(settings,hermes=Agent())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://127.0.0.1:8787') as c:
            origin={'origin':'http://127.0.0.1:8787'}
            login=await c.post('/api/auth/login',json={'token':'test-login'},headers=origin)
            headers={**origin,'x-csrf-token':login.json()['csrf']}
            result=await c.post('/api/chat',json={'text':'hello'},headers=headers)
            frames=[json.loads(s[6:]) for s in result.text.splitlines() if s.startswith('data: ')]
            identifier=next(f['session_id'] for f in frames if f['type']=='session')
            import sqlite3
            with sqlite3.connect(tmp_path/'memory-review.db') as db:db.execute("UPDATE preferences SET value='1' WHERE key='epoch'")
            response=await c.post('/api/chat',json={'text':'again','session_id':identifier},headers={**headers,'x-memory-epoch':'1'})
            assert response.status_code==409
    asyncio.run(run())


def test_profile_without_no_mcp_cannot_pass_discovery(tmp_path):
    async def run():
        home=tmp_path/'hermes';home.mkdir()
        (home/'config.yaml').write_text(json.dumps({'model':{'provider':'custom','base_url':'http://127.0.0.1:11434/v1'},'platform_toolsets':{'api_server':['jarvis_desktop']},'plugins':{'enabled':['jarvis_desktop']},'mcp_servers':{'danger':{'command':'sh'}}}))
        def transport(request):
            return httpx.Response(200,json={'data':[{'enabled':True,'tools':['jarvis_telemetry']}]})
        client=HermesClient(Settings(state_dir=tmp_path,hermes_home=home,hermes_key='test'),httpx.MockTransport(transport))
        try:
            with pytest.raises(HermesError):await client.preflight()
        finally:await client.close()
    asyncio.run(run())


def test_disconnect_always_releases_local_generation_lock(tmp_path):
    import anyio
    from app.main import Chat
    class Agent:
        capabilities={}
        async def preflight(self):return {'connected':True}
        async def close(self):pass
        async def stop(self,identifier):await asyncio.sleep(0);return True
        async def stream(self,*args):
            yield {'type':'run','run_id':'chatcmpl-test'}
            await asyncio.sleep(60)
    class Request:
        headers={}
        async def is_disconnected(self):return False
    async def run():
        app=create_app(Settings(state_dir=tmp_path),hermes=Agent())
        endpoint=next(r.endpoint for r in app.routes if getattr(r,'path',None)=='/api/chat')
        response=await endpoint(Chat(text='first'),Request())
        with anyio.CancelScope() as scope:
            async for event in response.body_iterator:
                if 'chatcmpl-test' in event:
                    scope.cancel()
                    await response.body_iterator.aclose()
                    break
        second=await endpoint(Chat(text='second'),Request())
        assert second.status_code==200
    asyncio.run(run())


@pytest.mark.parametrize('operation',['cancel','logout'])
def test_server_cancellation_stops_pending_read_without_remote_stop(tmp_path,operation):
    from app.main import Chat
    class Agent:
        capabilities={}
        async def preflight(self):return {'connected':True}
        async def close(self):pass
        async def stop(self,identifier):return False
        async def stream(self,*args):
            yield {'type':'run','run_id':'chatcmpl-idle'}
            await asyncio.Event().wait()
    class Request:
        headers={}
        cookies={}
        async def is_disconnected(self):return False
    async def run():
        app=create_app(Settings(state_dir=tmp_path),hermes=Agent())
        route=lambda path:next(r.endpoint for r in app.routes if getattr(r,'path',None)==path)
        response=await route('/api/chat')(Chat(text='hello'),Request())
        iterator=response.body_iterator
        session=json.loads((await anext(iterator))[6:])['session_id']
        await anext(iterator)
        await anext(iterator)
        pending=asyncio.create_task(anext(iterator))
        await asyncio.sleep(0)
        try:
            if operation=='cancel':await route('/api/chat/{identifier}/cancel')(session)
            else:await route('/api/auth/logout')(Request())
            ready,_=await asyncio.wait({pending},timeout=0.2)
            assert ready,'Server cancellation must end the current upstream read even when native stop is unavailable'
            with pytest.raises(StopAsyncIteration):await pending
        finally:
            pending.cancel()
            await asyncio.gather(pending,return_exceptions=True)
            await iterator.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('disconnect',['unstarted','headers'])
def test_disconnect_before_first_stream_event_releases_turn_reservation(tmp_path,disconnect):
    from app.main import Chat
    class Agent:
        async def preflight(self):return {'connected':True}
        async def close(self):pass
        async def stream(self,*args):yield {'type':'done'}
    class Request:
        headers={}
        async def is_disconnected(self):return False
    async def run():
        app=create_app(Settings(state_dir=tmp_path),hermes=Agent())
        endpoint=next(r.endpoint for r in app.routes if getattr(r,'path',None)=='/api/chat')
        response=await endpoint(Chat(text='first'),Request())
        if disconnect=='unstarted':await response.body_iterator.aclose()
        else:
            async def send(message):raise OSError('Client disconnected before headers')
            async def receive():return {'type':'http.disconnect'}
            with pytest.raises(Exception):await response({'type':'http','asgi':{'spec_version':'2.4'}},receive,send)
        second=await endpoint(Chat(text='second'),Request())
        assert second.status_code==200
        await second.body_iterator.aclose()
    asyncio.run(run())
