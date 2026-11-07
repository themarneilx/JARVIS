"""Real ASGI disconnect/logout with a blocked protocol fixture, not neural inference."""
import asyncio
import sys

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.stt import LocalSTT


@pytest.mark.parametrize('mode',['disconnect','logout'])
def test_browser_disconnect_or_own_logout_kills_native_worker_and_recovers(tmp_path,monkeypatch,mode):
    marker=tmp_path/'started'
    workers=[]
    program='''
import sys,struct,json,time
from pathlib import Path
while header:=sys.stdin.buffer.read(4):
    raw=sys.stdin.buffer.read(struct.unpack('!I',header)[0])
    marker=Path(sys.argv[1])
    if not marker.exists():
        marker.write_text('started')
        time.sleep(60)
    print(json.dumps({'text':'Ready','duration':1,'language':None,'provider':'parakeet','device':'cpu'}),flush=True)
'''
    async def start(self):
        if self.proc and self.proc.returncode is None: return
        self.proc=await asyncio.create_subprocess_exec(sys.executable,'-u','-c',program,str(marker),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE)
        workers.append(self.proc)
    monkeypatch.setattr(LocalSTT,'start',start)
    async def run():
        app=create_app(Settings(state_dir=tmp_path,login_token='test'))
        origin={'origin':'http://127.0.0.1:8787'}
        transport=httpx.ASGITransport(app)
        async with httpx.AsyncClient(transport=transport,base_url='http://127.0.0.1:8787') as client:
            login=await client.post('/api/auth/login',json={'token':'test'},headers=origin)
            headers={**origin,'x-csrf-token':login.json()['csrf'],'content-type':'audio/webm'}
            raw=b'\x1aE\xdf\xa3fixture'
            incoming=asyncio.Queue()
            if mode=='disconnect':
                await incoming.put({'type':'http.request','body':raw,'more_body':False})
                scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','scheme':'http','method':'POST','path':'/api/audio/transcribe','raw_path':b'/api/audio/transcribe','root_path':'','query_string':b'','server':('127.0.0.1',8787),'client':('127.0.0.1',1234),'headers':[(b'host',b'127.0.0.1:8787'),(b'cookie',('jarvis_session='+client.cookies.get('jarvis_session')).encode()),*[(key.encode(),value.encode()) for key,value in headers.items()]]}
                async def send(message): pass
                request=asyncio.create_task(app(scope,incoming.get,send))
            else:
                request=asyncio.create_task(client.post('/api/audio/transcribe',content=raw,headers=headers))
            try:
                for _ in range(200):
                    if marker.exists(): break
                    await asyncio.sleep(.01)
                assert marker.exists()
                if mode=='disconnect': await incoming.put({'type':'http.disconnect'})
                else:
                    async with httpx.AsyncClient(transport=transport,base_url='http://127.0.0.1:8787') as other:
                        login2=await other.post('/api/auth/login',json={'token':'test'},headers=origin)
                        await other.post('/api/auth/logout',headers={**origin,'x-csrf-token':login2.json()['csrf']})
                    assert workers[0].returncode is None
                    logout=await client.post('/api/auth/logout',headers={**origin,'x-csrf-token':login.json()['csrf']})
                    assert logout.status_code==200
                await asyncio.wait_for(workers[0].wait(),2)
                await asyncio.wait_for(request,2)
                assert workers[0].returncode is not None
                login=await client.post('/api/auth/login',json={'token':'test'},headers=origin)
                response=await client.post('/api/audio/transcribe',content=raw,headers={**headers,'x-csrf-token':login.json()['csrf']})
                assert response.json()['text']=='Ready'
            finally:
                if not request.done(): request.cancel()
                for worker in workers:
                    if worker.returncode is None: worker.kill();await worker.wait()
    asyncio.run(run())
