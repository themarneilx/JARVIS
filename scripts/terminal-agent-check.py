"""Real Hermes diagnostic; launching requires an explicit --allow-launch flag."""
import asyncio
import json
from pathlib import Path
import sys
import time
import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.config import Settings
from app.hermes import HermesClient


async def main():
    settings=Settings()
    origin=f'http://127.0.0.1:{settings.port}'
    agent=HermesClient(settings)
    owned=[]
    async with httpx.AsyncClient(base_url=origin,trust_env=False,timeout=180) as client:
        result=await client.post('/api/auth/login',headers={'origin':origin},json={'token':settings.login_token})
        result.raise_for_status()
        headers={'origin':origin,'x-csrf-token':result.json()['csrf']}
        policy=(await client.get('/api/desktop/settings')).json()
        may_launch=policy.get('ask_before_launch') is False
        if may_launch and '--allow-launch' not in sys.argv:
            await agent.close()
            raise RuntimeError('Desktop launches are preauthorized. Pass --allow-launch to test fastfetch, or enable approval in Settings. This diagnostic never changes your policy.')
        catalog=(await client.get('/api/terminal/commands')).json()
        fastfetch=next(row for row in catalog['commands'] if row['command']=='fastfetch' and row['cwd']=='')
        start=time.monotonic()
        events=[]
        try:
            async with client.stream('POST','/api/chat',headers=headers,json={'text':'can you open up a terminal emulator and run fastfetch'}) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith('data: '):events.append(json.loads(line[6:]))
            identifier=next(e['session_id'] for e in events if e['type']=='session')
            rows=await agent.session_rows(identifier)
            for row in rows:
                if row.get('tool_name') in ('jarvis_run_terminal','jarvis_launch_application'):
                    try:receipt=json.loads(row['content'])
                    except ValueError:continue
                    if receipt.get('id'):owned.append(receipt)
            tools={r.get('tool_name') for r in rows if r.get('role')=='tool'}
            assert {'jarvis_terminal_commands','jarvis_run_terminal'}<=tools, 'Hermes did not call both native terminal tools'
            assert not any(e['type']=='error' for e in events), 'The agent reported an error'
            assert any(e['type']=='done' for e in events), 'The agent did not complete'
            actions=(await client.get('/api/actions')).json()
            expected='executed' if may_launch else 'pending'
            assert owned and all(r['kind']=='terminal' and r['target']==fastfetch['id'] and next(a for a in actions if a['id']==r['id'])['status']==expected for r in owned)
            assert all(r.get('origin')=='bound_web_turn' for r in owned), 'Native tool context did not bind to the browser turn'
            text=''.join(e.get('text','') for e in events if e['type']=='delta')
            assert ('Kitty accepted' in text if may_launch else 'fastfetch' in text and 'approval' in text)
            evidence={'native_catalog_tool':True,'native_terminal_proposal_tool':True,'trusted_native_turn':True,'pending_without_execution':not may_launch,'verified_feedback':True,'seconds':round(time.monotonic()-start,2),'preauthorized_launch_accepted':may_launch,'command_completion_verified':False}
            path=ROOT/'.runtime/terminal-agent-check.json'
            path.write_text(json.dumps(evidence,indent=2)+'\n');path.chmod(0o600)
            print(json.dumps(evidence,indent=2))
        finally:
            for action in owned:
                if action.get('status')!='pending':continue
                result=await client.post('/api/actions/'+action['id']+'/resolve',json={'approve':False},headers=headers)
                result.raise_for_status()
            await agent.close()


if __name__=='__main__':asyncio.run(main())
