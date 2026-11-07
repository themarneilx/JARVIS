import asyncio,uuid
import httpx
from app.config import Settings
from app.main import create_app
from app.audio import JarvisTTS


def test_stale_cancel_cannot_kill_a_new_synthesis(tmp_path,monkeypatch):
    async def run():
        started=asyncio.Event();cancelled=[]
        async def synth(self,text):
            started.set()
            try:await asyncio.sleep(60)
            except asyncio.CancelledError:cancelled.append(True);raise
        monkeypatch.setattr(JarvisTTS,'synthesize',synth)
        app=create_app(Settings(state_dir=tmp_path,login_token='test'))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://127.0.0.1:8787') as c:
            origin={'origin':'http://127.0.0.1:8787'}
            login=await c.post('/api/auth/login',json={'token':'test'},headers=origin)
            h={**origin,'x-csrf-token':login.json()['csrf']}
            current=str(uuid.uuid4())
            task=asyncio.create_task(c.post('/api/audio/synthesize',json={'text':'hello','request_id':current},headers=h))
            await started.wait()
            switch=await c.post('/api/audio/settings',json={'device':'cuda'},headers=h)
            assert switch.status_code==409
            assert (await c.get('/api/audio/settings')).json()['device']=='cpu'
            stale=await c.post('/api/audio/cancel',json={'request_id':str(uuid.uuid4())},headers=h)
            assert not stale.json()['cancelled'] and not cancelled
            matched=await c.post('/api/audio/cancel',json={'request_id':current},headers=h)
            assert matched.json()['cancelled'] and cancelled
            assert (await task).status_code==409
            started.clear()
            late=await c.post('/api/audio/synthesize',json={'text':'late prefetched phrase','request_id':current},headers=h)
            assert late.status_code==409 and not started.is_set()
            before_start=str(uuid.uuid4())
            assert not (await c.post('/api/audio/cancel',json={'request_id':before_start},headers=h)).json()['cancelled']
            assert (await c.post('/api/audio/synthesize',json={'text':'late request','request_id':before_start},headers=h)).status_code==409
    asyncio.run(run())
