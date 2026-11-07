"""Real read-only provider diagnostics; no model compatibility is inferred."""
import asyncio,json,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.information import Information,Lookup


async def main():
    service=Information(ROOT/'.runtime')
    results=[]
    try:
        for request in [Lookup(kind='time'),Lookup(kind='location'),Lookup(kind='weather'),Lookup(kind='exchange_rates'),Lookup(kind='stocks',symbol='NVDA'),Lookup(kind='news',query='Philippines weather')]:
            start=time.monotonic()
            try:
                result=await service.lookup(request)
                results.append({'kind':request.kind,'ok':True,'seconds':round(time.monotonic()-start,3),'summary':result['verified_summary'],'as_of':result.get('as_of')})
            except Exception as exc:results.append({'kind':request.kind,'ok':False,'error':str(exc)})
    finally:await service.close()
    path=ROOT/'.runtime/information-check.json';path.write_text(json.dumps(results,indent=2));path.chmod(0o600)
    print(json.dumps(results,indent=2))
    return 0 if all(item['ok'] for item in results) else 1


if __name__=='__main__':sys.exit(asyncio.run(main()))
