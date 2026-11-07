import hashlib,uuid
import httpx
import pytest
from app.config import Settings
from app.main import create_app
from app.permissions import ApprovalStore
from app.terminal import DesktopAccess

pytestmark=pytest.mark.anyio
@pytest.fixture
def anyio_backend():return 'asyncio'


async def native_headers(client,session,text):
    turn=uuid.uuid4().hex
    headers={'authorization':'Bearer '+'p'*40,'x-jarvis-native-session':session,'x-jarvis-native-turn':turn}
    result=await client.post('/api/internal/desktop/bind-turn',headers=headers,json={'session_id':session,'turn_id':turn,'prompt_hash':hashlib.sha256(text.encode()).hexdigest()})
    assert result.json()['bound']
    return headers


async def test_only_browser_can_set_policy_or_save_commands(tmp_path,monkeypatch):
    import app.main as main
    home=tmp_path/'home';home.mkdir()
    programs=tmp_path/'bin';programs.mkdir()
    for name in ('kitty','fastfetch'):
        item=programs/name;item.write_text('fixture');item.chmod(0o755)
    access=DesktopAccess(tmp_path/'desktop.db',home=home,bin_dir=programs)
    monkeypatch.setattr(main,'DesktopAccess',lambda *args:access)
    calls=[]
    class Store(ApprovalStore):
        def __init__(self,path,policy):super().__init__(path,policy,executor=lambda argv:calls.append(argv) or {'ok':True})
    monkeypatch.setattr(main,'ApprovalStore',Store)
    app=create_app(Settings(state_dir=tmp_path/'state',login_token='l'*40,plugin_token='p'*40))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://127.0.0.1:8787') as client:
        plugin={'authorization':'Bearer '+'p'*40}
        assert (await client.post('/api/desktop/settings',json={'ask_before_launch':False},headers=plugin)).status_code==401
        assert (await client.post('/api/internal/desktop/settings',json={'ask_before_launch':False},headers=plugin)).status_code in (404,405)
        recipe=(await client.get('/api/internal/terminal/commands',headers=plugin)).json()['commands'][0]
        for body in ({'command_id':recipe['id'],'argv':['sudo','id']},{'command_id':recipe['id'],'approve':True}):
            assert (await client.post('/api/internal/terminal/propose',json=body,headers=plugin)).status_code==422
        proposal=(await client.post('/api/internal/terminal/propose',json={'command_id':recipe['id']},headers=plugin)).json()
        assert proposal['status']=='pending' and not calls
        paired=await client.post('/api/auth/login',json={'token':'l'*40},headers={'origin':'http://127.0.0.1:8787'})
        auth={'origin':'http://127.0.0.1:8787','x-csrf-token':paired.json()['csrf']}
        assert (await client.post('/api/desktop/settings',json={'ask_before_launch':False})).status_code==403
        assert (await client.post('/api/desktop/settings',json={'ask_before_launch':'false'},headers=auth)).status_code==422
        assert (await client.post('/api/desktop/settings',json={'ask_before_launch':False},headers=auth)).status_code==200
        unbound=(await client.post('/api/internal/terminal/propose',json={'command_id':recipe['id']},headers=plugin)).json()
        assert unbound['status']=='pending' and not calls
        result=(await client.post('/api/terminal/propose',json={'command_id':recipe['id']},headers=auth)).json()
        assert result['status']=='executed' and result['authorization']=='desktop_setting' and len(calls)==1
        actions=(await client.get('/api/actions')).json()
        assert next(row for row in actions if row['id']==proposal['id'])['status']=='pending'
        # Generic proposals cannot hide a terminal target or invent its effect.
        response=await client.post('/api/internal/actions',json={'kind':'terminal','target':recipe['id'],'effect':'harmless'},headers=plugin)
        assert response.status_code==400 and len(calls)==1
        response=await client.post('/api/terminal/commands',json={'name':'Custom','command':'fastfetch --version','cwd':''},headers=auth)
        assert response.status_code==200
        saved=response.json()
        assert (await client.delete('/api/terminal/commands/'+saved['id'],headers=auth)).status_code==200
        assert (await client.post('/api/internal/terminal/propose',json={'command_id':saved['id']},headers=plugin)).status_code==400
        assert len(calls)==1


async def test_review_result_reports_terminal_launch_not_command_completion(tmp_path):
    from app.permissions import ActionPolicy
    access=DesktopAccess(tmp_path/'desktop.db')
    recipes=access.catalog()['commands']
    if not recipes:pytest.skip('Kitty and a supported command are not installed')
    store=ApprovalStore(tmp_path/'actions.db',ActionPolicy(terminal_catalog=access),executor=lambda argv:{'ok':True})
    action=access.request(store,'terminal',recipes[0]['id'])
    result=store.resolve(action['id'],True)
    assert result['kind']=='terminal' and result['result']['authorization']=='review'


async def test_repeated_native_requests_launch_once_per_web_turn(tmp_path,monkeypatch):
    import app.main as main
    home=tmp_path/'home';home.mkdir()
    programs=tmp_path/'bin';programs.mkdir()
    for name in ('kitty','fastfetch'):
        item=programs/name;item.write_text('fixture');item.chmod(0o755)
    access=DesktopAccess(tmp_path/'desktop.db',home=home,bin_dir=programs)
    monkeypatch.setattr(main,'DesktopAccess',lambda *args:access)
    calls=[]
    class Store(ApprovalStore):
        def __init__(self,path,policy):super().__init__(path,policy,executor=lambda argv:calls.append(argv) or {'ok':True})
    monkeypatch.setattr(main,'ApprovalStore',Store)
    command=access.catalog()['commands'][0]
    class Agent:
        async def preflight(self):return {}
        async def stream(self,text,identifier,*args):
            # An unrelated CLI, a guessed session, and a stale prior turn must
            # never borrow this browser turn's permission.
            for extra in ({},{'x-jarvis-native-session':identifier},{'x-jarvis-native-session':identifier,'x-jarvis-native-turn':'stale-turn'}):
                result=await self.client.post('/api/internal/terminal/propose',json={'command_id':command['id']},headers={'authorization':'Bearer '+'p'*40,**extra})
                assert result.json()['status']=='pending'
            old=getattr(self,'last_headers',None)
            if old:
                replay=await self.client.post('/api/internal/desktop/bind-turn',headers=old,json={'session_id':identifier,'turn_id':old['x-jarvis-native-turn'],'prompt_hash':hashlib.sha256(text.encode()).hexdigest()})
                assert replay.json()['bound'] is False
            headers=await native_headers(self.client,identifier,text)
            self.last_headers=headers
            receipts=[]
            for _ in range(2):
                response=await self.client.post('/api/internal/terminal/propose',json={'command_id':command['id']},headers=headers)
                assert response.status_code==200
                receipts.append(response.json())
            assert receipts[0]['id']==receipts[1]['id']
            unrelated=await self.client.post('/api/internal/terminal/propose',json={'command_id':command['id']},headers={'authorization':'Bearer '+'p'*40})
            assert unrelated.json()['status']=='pending'
            yield {'type':'done'}
    agent=Agent()
    app=create_app(Settings(state_dir=tmp_path/'state',login_token='l'*40,plugin_token='p'*40),hermes=agent)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://127.0.0.1:8787') as client:
        agent.client=client
        paired=await client.post('/api/auth/login',json={'token':'l'*40},headers={'origin':'http://127.0.0.1:8787'})
        auth={'origin':'http://127.0.0.1:8787','x-csrf-token':paired.json()['csrf']}
        assert (await client.post('/api/desktop/settings',json={'ask_before_launch':False},headers=auth)).status_code==200
        identifier=None
        for expected in (1,2):
            response=await client.post('/api/chat',json={'text':'Run fastfetch','session_id':identifier},headers=auth)
            assert response.status_code==200 and len(calls)==expected
            import json
            events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
            identifier=next(event['session_id'] for event in events if event['type']=='session')


async def test_cancelled_turn_cannot_launch_a_queued_command(tmp_path,monkeypatch):
    import asyncio,threading
    import app.main as main
    home=tmp_path/'home';home.mkdir()
    programs=tmp_path/'bin';programs.mkdir()
    for name in ('kitty','fastfetch'):
        item=programs/name;item.write_text('fixture');item.chmod(0o755)
    access=DesktopAccess(tmp_path/'desktop.db',home=home,bin_dir=programs)
    monkeypatch.setattr(main,'DesktopAccess',lambda *args:access)
    started,release=threading.Event(),threading.Event()
    calls=[]
    def execute(argv):
        calls.append(argv);started.set();release.wait(10)
        return {'ok':True}
    class Store(ApprovalStore):
        def __init__(self,path,policy):super().__init__(path,policy,executor=execute)
    monkeypatch.setattr(main,'ApprovalStore',Store)
    command=access.catalog()['commands'][0]
    class Agent:
        def __init__(self):self.queued=asyncio.Event();self.requests=[]
        async def preflight(self):return {}
        async def stream(self,text,identifier,*args):
            self.identifier=identifier
            headers=await native_headers(self.client,identifier,text)
            async def submit():return await self.client.post('/api/internal/terminal/propose',json={'command_id':command['id']},headers=headers)
            self.requests.append(asyncio.create_task(submit()))
            while not started.is_set():await asyncio.sleep(.001)
            self.requests.append(asyncio.create_task(submit()))
            await asyncio.sleep(.03)
            self.queued.set()
            await asyncio.Event().wait()
            yield {'type':'done'}
    agent=Agent()
    app=create_app(Settings(state_dir=tmp_path/'state',login_token='l'*40,plugin_token='p'*40),hermes=agent)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://127.0.0.1:8787') as client:
        agent.client=client
        paired=await client.post('/api/auth/login',json={'token':'l'*40},headers={'origin':'http://127.0.0.1:8787'})
        auth={'origin':'http://127.0.0.1:8787','x-csrf-token':paired.json()['csrf']}
        await client.post('/api/desktop/settings',json={'ask_before_launch':False},headers=auth)
        chat=asyncio.create_task(client.post('/api/chat',json={'text':'Run fastfetch'},headers=auth))
        try:
            await asyncio.wait_for(agent.queued.wait(),2)
            cancelled=await client.post('/api/chat/'+agent.identifier+'/cancel',headers=auth)
            assert cancelled.json()['stream_closed']
        finally:release.set()
        responses=await asyncio.wait_for(asyncio.gather(*agent.requests),2)
        await asyncio.wait_for(chat,2)
        assert len(calls)==1
        assert responses[0].status_code==200 and responses[1].status_code==400
