"""Exercise real native Hermes online tools using fresh, non-browser sessions."""
import asyncio,json,sys,time,uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.config import Settings
from app.hermes import HermesClient
from app.models import ModelManager


async def main():
    settings=Settings();agent=HermesClient(settings);models=ModelManager(settings)
    if models.selected_model:agent.set_model(models.selected_model)
    results=[]
    try:
        await agent.preflight()
        for prompt in ["What's my location?", "What's the weather like today?", "What's the current exchange rate to the US dollar?",'Use jarvis_online twice: current weather for my saved city, then the USD/PHP exchange rate.','Search the web for NVIDIA RTX 4050 laptop specifications.','What is the NVDA stock price?','Find news headlines about the Philippines.','What time is it now?']:
            session=str(uuid.uuid4());start=time.monotonic()
            try:
                events=[e async for e in agent.stream(prompt,session,str(uuid.uuid4()))]
                rows=await agent.session_rows(session)
                tools=[r.get('tool_name') for r in rows if r.get('role')=='tool']
                if prompt=="What's the current exchange rate to the US dollar?":
                    answer=''.join(e.get('text','') for e in events if e['type']=='delta')
                    assert 'USD' in answer and 'PHP' in answer,'The default currency question must report USD/PHP rather than a same-currency result'
                results.append({'prompt':prompt,'ok':True,'seconds':round(time.monotonic()-start,2),'tools':tools,'answer':''.join(e.get('text','') for e in events if e['type']=='delta')})
            except Exception as exc:
                rows=await agent.session_rows(session)
                results.append({'prompt':prompt,'ok':False,'seconds':round(time.monotonic()-start,2),'error':str(exc),'receipts':[{'tool':r.get('tool_name'),'content':r.get('content','')[:1000]} for r in rows if r.get('role')=='tool']})
            print(json.dumps(results[-1]),flush=True)
    finally:await agent.close();await models.close()
    path=ROOT/'.runtime/online-agent-check.json';path.write_text(json.dumps(results,indent=2));path.chmod(0o600)
    return 0 if all(item['ok'] for item in results) else 1


if __name__=='__main__':sys.exit(asyncio.run(main()))
