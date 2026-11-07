"""Real local Hermes file/app checks. Launch proposals are rejected, never executed."""
import asyncio,json,sys,time
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.config import Settings
from app.hermes import HermesClient


async def main():
    settings=Settings();origin=f'http://127.0.0.1:{settings.port}'
    agent=HermesClient(settings);results=[]
    try:
        async with httpx.AsyncClient(base_url=origin,trust_env=False,timeout=180) as client:
            response=await client.post('/api/auth/login',headers={'origin':origin},json={'token':settings.login_token});response.raise_for_status()
            headers={'origin':origin,'x-csrf-token':response.json()['csrf']}
            async def chat(text,session=None):
                started=time.monotonic();events=[]
                async with client.stream('POST','/api/chat',headers=headers,json={'text':text,'session_id':session}) as response:
                    if response.status_code==403:
                        data=json.loads((await response.aread()).decode())
                        return session,[{'type':'error','message':data.get('detail','')}],round(time.monotonic()-started,2)
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith('data: '):events.append(json.loads(line[6:]))
                identifier=next(e['session_id'] for e in events if e['type']=='session')
                return identifier,events,round(time.monotonic()-started,2)
            session,events,elapsed=await chat('List my home directory using jarvis_home_files. Return a short list.')
            rows=await agent.session_rows(session)
            assert any(r.get('tool_name')=='jarvis_home_files' for r in rows)
            assert any(e['type']=='done' for e in events) and not any(e['type']=='error' for e in events)
            results.append({'home_native_tool':True,'seconds':elapsed,'verified_summary_returned':True})
            _,events,_=await chat('Search the web for NVIDIA RTX 4050 laptop specifications.',session)
            assert any(e['type']=='error' and 'home-file data' in e.get('message','') for e in events)
            results.append({'same_conversation_outbound_refused':True})
            catalog=(await client.get('/api/applications')).json()
            application=catalog['applications'][0]
            session,events,elapsed=await chat('Open '+application['name']+' using the installed catalog. Prepare the launch and wait for my popup approval.')
            rows=await agent.session_rows(session)
            receipts=[]
            for row in rows:
                if row.get('tool_name')=='jarvis_launch_application':
                    try:receipts.append(json.loads(row['content']))
                    except ValueError:pass
            owned=[r for r in receipts if r.get('id') and r.get('kind')=='launch']
            try:
                assert owned,'No actual launch proposal was created'
                actions=(await client.get('/api/actions')).json()
                assert all(next(a for a in actions if a['id']==r['id'])['status']=='pending' for r in owned)
                results.append({'native_application_catalog':any(r.get('tool_name')=='jarvis_applications' for r in rows),'native_launch_proposal':True,'unapproved_execution':False,'seconds':elapsed})
            finally:
                for receipt in owned:
                    action=await client.post('/api/actions/'+receipt['id']+'/resolve',headers=headers,json={'approve':False})
                    action.raise_for_status()
                    assert action.json()['status']=='rejected'
    finally:await agent.close()
    path=ROOT/'.runtime/access-agent-check.json';path.write_text(json.dumps(results,indent=2));path.chmod(0o600)
    print(json.dumps(results,indent=2))


if __name__=='__main__':asyncio.run(main())
