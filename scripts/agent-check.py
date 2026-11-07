"""Real provider checks. Requires the local application and restricted Hermes gateway."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time
import subprocess

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.config import Settings
from app.hermes import HermesClient
from app.runtime import discover_runtime
from app.models import ModelManager


async def main(probe=False):
    settings = Settings()
    runtime = discover_runtime(ROOT)
    report = {'runtime': {'version': runtime.version, 'commit': runtime.commit}, 'mocked': False}
    agent = HermesClient(settings)
    models=ModelManager(settings)
    if models.selected_model:agent.set_model(models.selected_model)
    try:
        report['preflight'] = await agent.preflight()
    finally:
        await agent.close()
        await models.close()
    origin = f'http://127.0.0.1:{settings.port}'
    async with httpx.AsyncClient(base_url=origin, trust_env=False, timeout=180) as browser:
        report['ollama_allocation'] = (await browser.get(settings.ollama_url + '/api/ps')).json()
        response = await browser.post('/api/auth/login', headers={'Origin': origin}, json={'token': settings.login_token})
        response.raise_for_status()
        headers = {'Origin': origin, 'X-CSRF-Token': response.json()['csrf']}
        for key, route in [('application', '/api/status'), ('memory', '/api/memory')]:
            response = await browser.get(route)
            response.raise_for_status()
            value = response.json()
            report[key] = value if key == 'application' else {'entry_count': len(value['entries']), 'limits': value['limits']}
        if not probe:
            events = []
            started = time.monotonic()
            first_delta = None
            async with browser.stream('POST', '/api/chat', headers=headers, json={'text': 'Identify yourself briefly. Then call jarvis_telemetry and jarvis_processes, both, and report the current CPU usage, GPU temperature and one running process from the tool results. Do not guess any readings.'}) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        item=json.loads(line[6:])
                        events.append(item)
                        if item['type']=='delta' and first_delta is None:
                            first_delta=round(time.monotonic()-started,2)
            report['turn'] = {'elapsed_seconds': round(time.monotonic() - started, 2), 'events': events}
            report['turn']['first_text_seconds']=first_delta
            report['ollama_after']=(await browser.get(settings.ollama_url+'/api/ps')).json()
            for label,command in [('placement',['ollama','ps']),('gpu',['nvidia-smi','--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu','--format=csv,noheader']),('ram',['free','-b'])]:
                report[label]=subprocess.check_output(command,text=True,timeout=5).strip()
            (ROOT / '.runtime/agent-check.json').write_text(json.dumps(report, indent=2))
            assert not any(e['type'] == 'error' for e in events), 'Agent reported an error'
            assert any(e['type'] == 'done' for e in events), 'No successful completion'
            assert len({e['label'] for e in events if e['type']=='tool'})>=2, 'Both live tools must execute'
            expected_model=report['application']['agent']['context']['model']
            assert any(m.get('context_length',0)>=64000 and m['name']==expected_model for m in report['ollama_after']['models']), 'Actual selected-model 64K allocation was not verified'
            session = next(e['session_id'] for e in events if e['type'] == 'session')
            response = await browser.get(f'/api/conversations/{session}')
            response.raise_for_status()
            report['history'] = response.json()
        await browser.post('/api/auth/logout', headers=headers, json={})
    (ROOT / '.runtime/agent-check.json').write_text(json.dumps(report, indent=2))
    summary={k:v for k,v in report.items() if k not in ('turn','history','preflight','application','ollama_allocation')}
    if 'turn' in report:
        summary['turn']={k:v for k,v in report['turn'].items() if k!='events'}
        summary['answer']=''.join(e['text'] for e in report['turn']['events'] if e['type']=='delta')
        summary['tools']=sorted({e['label'] for e in report['turn']['events'] if e['type']=='tool'})
        summary['history_messages']=len(report['history']['messages'])
    else:
        summary['application']=report['application']
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', action='store_true')
    args = parser.parse_args()
    asyncio.run(main(args.probe))
