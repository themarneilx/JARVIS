import json
from pathlib import Path
import httpx,pytest
from app.config import Settings
from app.main import create_app
from app.desktop_apps import DesktopApps
from app.home_files import HomeFiles
from app.permissions import ApprovalStore

pytestmark=pytest.mark.anyio
@pytest.fixture
def anyio_backend():return 'asyncio'

@pytest.fixture
def configured(tmp_path,monkeypatch):
    import app.main as main
    home=tmp_path/'home';home.mkdir()
    (home/'notes.txt').write_text('Useful notes. api_key=do-not-echo-this-value')
    (home/'settings.json').write_text(json.dumps({'api_key':'example-sensitive-value','password':'another-sensitive-value','nested':{'refresh_token':'never-expose-refresh'},'normal':'keep this'}))
    apps=tmp_path/'apps';apps.mkdir()
    (apps/'editor.desktop').write_text('[Desktop Entry]\nType=Application\nName=Notes Editor\nExec=editor\n')
    launcher=tmp_path/'gio';launcher.touch();launcher.chmod(0o700)
    catalog=DesktopApps(roots=(apps,),launcher=launcher)
    monkeypatch.setattr(main,'DesktopApps',lambda:catalog)
    monkeypatch.setattr(main,'HomeFiles',lambda **kwargs:HomeFiles(home))
    calls=[]
    class CapturedStore(ApprovalStore):
        def __init__(self,path,policy):super().__init__(path,policy,executor=lambda argv:calls.append(argv) or {'ok':True})
    monkeypatch.setattr(main,'ApprovalStore',CapturedStore)
    return tmp_path,catalog,calls,apps

async def pair(client):
    response=await client.post('/api/auth/login',json={'token':'l'*40},headers={'origin':'http://127.0.0.1:8787'})
    return {'origin':'http://127.0.0.1:8787','x-csrf-token':response.json()['csrf']}

async def test_home_and_app_apis_enforce_scope_and_browsers_cannot_supply_arguments(configured):
    root,catalog,calls,apps=configured
    app=create_app(Settings(state_dir=root/'state',login_token='l'*40,plugin_token='p'*40))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://127.0.0.1:8787') as client:
        assert (await client.get('/api/applications')).status_code==401
        headers=await pair(client)
        for path in ('/etc/passwd','../outside','.env'):
            assert (await client.post('/api/home/lookup',json={'kind':'read','path':path},headers=headers)).status_code==400
        result=(await client.post('/api/home/lookup',json={'kind':'read','path':'notes.txt'},headers=headers)).json()
        assert result['credentials_redacted'] and 'do-not-echo' not in result['text']
        internal=await client.post('/api/internal/home/lookup',json={'kind':'read','path':'settings.json'},headers={'authorization':'Bearer '+'p'*40})
        assert internal.status_code==200
        result=internal.json()
        assert result['credentials_redacted'] and all(secret not in result['text'] for secret in ('example-sensitive-value','another-sensitive-value','never-expose-refresh'))
        assert json.loads(result['text'])['normal']=='keep this'
        row=(await client.get('/api/applications')).json()['applications'][0]
        assert (await client.post('/api/applications/propose',json={'application_id':row['id'],'argv':['rm','-rf','/']},headers=headers)).status_code==422
        proposal=(await client.post('/api/actions',json={'kind':'launch','target':row['id'],'effect':'Pretend this is harmless'},headers=headers)).json()
        assert proposal['effect']==row['effect'] and not calls
        ticket=(await client.get('/api/reviews')).json()[0]
        approved=await client.post('/api/reviews/'+ticket['id']+'/resolve',json={'approve':True,'code':ticket['code']},headers=headers)
        assert approved.json()['status']=='executed'
        assert calls==[catalog.command(row['id'])]

async def test_stale_application_descriptor_cannot_execute(configured):
    root,catalog,calls,apps=configured
    app=create_app(Settings(state_dir=root/'state',login_token='l'*40))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://127.0.0.1:8787') as client:
        headers=await pair(client)
        identifier=catalog.list()['applications'][0]['id']
        assert (await client.post('/api/applications/propose',json={'application_id':identifier},headers=headers)).status_code==200
        ticket=(await client.get('/api/reviews')).json()[0]
        (apps/'editor.desktop').write_text('[Desktop Entry]\nType=Application\nName=Changed\nExec=another-editor\n')
        assert (await client.post('/api/reviews/'+ticket['id']+'/resolve',json={'approve':True,'code':ticket['code']},headers=headers)).status_code==400
        assert not calls

async def test_private_file_context_blocks_agent_outbound_queries_across_turns(configured):
    root,_,_,_=configured
    class Agent:
        statuses=[]
        async def preflight(self):return {'connected':True}
        async def close(self):pass
        async def stream(self,text,session,request):
            if text=='read':
                assert (await self.client.post('/api/internal/home/lookup',json={'kind':'read','path':'notes.txt'},headers={'authorization':'Bearer '+'p'*40})).status_code==200
            response=await self.client.get('/api/internal/online/search-permit',headers={'authorization':'Bearer '+'p'*40})
            self.statuses.append(response.status_code)
            yield {'type':'done'}
    agent=Agent()
    app=create_app(Settings(state_dir=root/'state',login_token='l'*40,plugin_token='p'*40),hermes=agent)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://127.0.0.1:8787') as client:
        agent.client=client;headers=await pair(client)
        assert (await client.post('/api/information/settings',json={'enabled':True},headers=headers)).status_code==200
        first=await client.post('/api/chat',json={'text':'read'},headers=headers)
        events=[json.loads(line[6:]) for line in first.text.splitlines() if line.startswith('data: ')]
        identifier=next(e['session_id'] for e in events if e['type']=='session')
        blocked=await client.post('/api/chat',json={'text':'Search the web for test documentation','session_id':identifier},headers=headers)
        assert blocked.status_code==403 and 'home-file data' in blocked.json()['detail']
        await client.post('/api/chat',json={'text':'search','session_id':identifier},headers=headers)
        await client.post('/api/chat',json={'text':'search'},headers=headers)
        assert agent.statuses==[403,403,200]
