import pytest
from httpx import ASGITransport, AsyncClient
from app.config import Settings
from app.main import create_app

pytestmark = pytest.mark.anyio

@pytest.fixture
def anyio_backend(): return 'asyncio'

async def test_review_ticket_requires_browser_and_its_exact_code(tmp_path):
    app = create_app(Settings(state_dir=tmp_path, login_token='l'*40, plugin_token='p'*40))
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://127.0.0.1:8787') as client:
        assert (await client.get('/api/reviews')).status_code == 401
        login = await client.post('/api/auth/login', json={'token':'l'*40}, headers={'origin':'http://127.0.0.1:8787'})
        headers = {'origin':'http://127.0.0.1:8787','x-csrf-token':login.json()['csrf']}
        proposal = (await client.post('/api/actions', json={'kind':'workspace','target':'2','effect':'Switch to workspace 2'}, headers=headers)).json()
        response = await client.get('/api/reviews')
        assert response.status_code == 200
        ticket = response.json()[0]
        assert ticket['proposal_id'] == proposal['id'] and ticket['target'] == '2'
        assert len(ticket['code']) == 4 and ticket['code'].isdigit()
        assert (await client.get('/api/reviews')).json()[0]['id'] == ticket['id']
        wrong = '0000' if ticket['code'] != '0000' else '9999'
        assert (await client.post('/api/reviews/'+ticket['id']+'/resolve', json={'approve':True,'code':wrong}, headers=headers)).status_code == 400
        assert (await client.post('/api/reviews/'+ticket['id']+'/resolve', json={'approve':False,'code':ticket['code']}, headers=headers)).json()['status'] == 'rejected'
        assert (await client.post('/api/reviews/'+ticket['id']+'/resolve', json={'approve':True,'code':ticket['code']}, headers=headers)).status_code == 400
        assert (await client.get('/api/reviews')).json() == []

async def test_plugin_and_another_paired_browser_cannot_use_review_ticket(tmp_path):
    app = create_app(Settings(state_dir=tmp_path, login_token='l'*40, plugin_token='p'*40))
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://127.0.0.1:8787') as one, AsyncClient(transport=ASGITransport(app=app), base_url='http://127.0.0.1:8787') as two:
        headers=[]
        for client in (one,two):
            login=await client.post('/api/auth/login',json={'token':'l'*40},headers={'origin':'http://127.0.0.1:8787'})
            headers.append({'origin':'http://127.0.0.1:8787','x-csrf-token':login.json()['csrf']})
        await one.post('/api/actions',json={'kind':'volume','target':'30'},headers=headers[0])
        response=await one.get('/api/reviews')
        assert response.status_code == 200
        ticket=response.json()[0]
        assert (await two.post('/api/reviews/'+ticket['id']+'/resolve',json={'approve':False,'code':ticket['code']},headers=headers[1])).status_code == 400
        one.cookies.clear()
        assert (await one.get('/api/reviews',headers={'authorization':'Bearer '+'p'*40})).status_code == 401
        assert (await one.post('/api/internal/reviews/'+ticket['id']+'/resolve',json={'approve':True,'code':ticket['code']},headers={'authorization':'Bearer '+'p'*40})).status_code in (404,405)

async def test_memory_proposals_are_reviewable_without_loading_native_memory(tmp_path):
    async def no_bridge(payload): raise AssertionError('Polling proposals must not load a native model or memory subprocess')
    app=create_app(Settings(state_dir=tmp_path,login_token='l'*40),memory_bridge=no_bridge)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://127.0.0.1:8787') as client:
        login=await client.post('/api/auth/login',json={'token':'l'*40},headers={'origin':'http://127.0.0.1:8787'})
        headers={'origin':'http://127.0.0.1:8787','x-csrf-token':login.json()['csrf']}
        # A proposal is inserted directly to isolate polling from native storage validation.
        import sqlite3,json,time
        with sqlite3.connect(tmp_path/'memory-review.db') as db:
            db.execute('INSERT INTO proposals VALUES (?,?,?,?)',('proposal',json.dumps({'action':'add','target':'user','content':'Prefer concise responses','old_text':'','reason':'Explicit preference'}),time.time(),'pending'))
        response=await client.get('/api/reviews')
        assert response.status_code == 200
        ticket=response.json()[0]
        assert ticket['source']=='memory' and ticket['content']=='Prefer concise responses'
        assert (await client.post('/api/reviews/'+ticket['id']+'/resolve',json={'approve':False,'code':ticket['code']},headers=headers)).json()['status']=='rejected'

def test_review_expiry_and_proposal_change_are_enforced(monkeypatch):
    from app.reviews import ReviewTickets
    clock=[1000]
    monkeypatch.setattr('app.reviews.time.time',lambda:clock[0])
    reviews=ReviewTickets()
    proposal={'source':'action','proposal_id':'id','target':'2','expires':1100}
    ticket=reviews.issue('browser',[proposal])[0]
    with pytest.raises(ValueError,match='changed'):
        reviews.consume('browser',ticket['id'],ticket['code'],[{**proposal,'target':'3'}])
    clock[0]=1101
    with pytest.raises(ValueError,match='expired'):
        reviews.consume('browser',ticket['id'],ticket['code'],[proposal])

async def test_approved_ticket_executes_only_original_validated_action_once(tmp_path,monkeypatch):
    from app.permissions import ApprovalStore
    calls=[]
    monkeypatch.setattr('app.main.ApprovalStore',lambda path,policy:ApprovalStore(path,policy,executor=lambda argv:calls.append(argv) or {'ok':True}))
    app=create_app(Settings(state_dir=tmp_path,login_token='l'*40))
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://127.0.0.1:8787') as client:
        login=await client.post('/api/auth/login',json={'token':'l'*40},headers={'origin':'http://127.0.0.1:8787'})
        headers={'origin':'http://127.0.0.1:8787','x-csrf-token':login.json()['csrf']}
        await client.post('/api/actions',json={'kind':'volume','target':'30','effect':'Set output to 30%'},headers=headers)
        ticket=(await client.get('/api/reviews')).json()[0]
        url='/api/reviews/'+ticket['id']+'/resolve'
        body={'approve':True,'code':ticket['code']}
        assert not calls
        assert (await client.post(url,json=body,headers=headers)).json()['status']=='executed'
        assert calls==[['wpctl','set-volume','@DEFAULT_AUDIO_SINK@','30%']]
        assert (await client.post(url,json=body,headers=headers)).status_code==400
        assert len(calls)==1

async def test_model_switch_and_review_resolution_refused_during_preflight(tmp_path):
    import asyncio
    entered,finish=asyncio.Event(),asyncio.Event()
    class Agent:
        async def preflight(self):entered.set();await finish.wait();return {'connected':True}
        async def close(self):pass
        async def stream(self,*args):yield {'type':'done'}
    app=create_app(Settings(state_dir=tmp_path,login_token='l'*40),hermes=Agent())
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://127.0.0.1:8787') as client:
        login=await client.post('/api/auth/login',json={'token':'l'*40},headers={'origin':'http://127.0.0.1:8787'})
        headers={'origin':'http://127.0.0.1:8787','x-csrf-token':login.json()['csrf']}
        turn=asyncio.create_task(client.post('/api/chat',json={'text':'hello'},headers=headers))
        await asyncio.wait_for(entered.wait(),1)
        try:
            assert (await client.post('/api/models/select',json={'model':'unselected:latest'},headers=headers)).status_code==409
            assert (await client.post('/api/reviews/unused/resolve',json={'approve':True,'code':'1234'},headers=headers)).status_code==409
        finally:
            finish.set()
            assert (await turn).status_code==200
