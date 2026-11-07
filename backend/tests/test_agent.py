import asyncio
import json
import httpx
import pytest
from app.config import Settings
from app.hermes import HermesClient,HermesError,SAFE_TOOLS

def safe_settings(tmp_path):
    home=tmp_path/'profile'; home.mkdir(exist_ok=True)
    (home/'config.yaml').write_text(json.dumps({'model':{'provider':'custom','base_url':'http://127.0.0.1:11434/v1','default':'local-qwen:latest'},'platform_toolsets':{'api_server':['jarvis_desktop','no_mcp']},'plugins':{'enabled':['jarvis_desktop']},'auxiliary':{'background_review':{'enabled':False}}}))
    return Settings(state_dir=tmp_path,hermes_key='test',hermes_home=home)


def test_safe_tool_discovery_current_envelope(tmp_path):
    def handler(request):
        if request.url.path=='/api/show':
            assert 'authorization' not in request.headers
            return httpx.Response(200,json={'parameters':'num_ctx 64000'})
        if request.url.path=='/v1/capabilities':return httpx.Response(200,json={'features':{'run_stop':True}})
        return httpx.Response(200,json={'object':'list','data':[{'enabled':True,'tools':sorted(SAFE_TOOLS)}]})
    async def run():
        client=HermesClient(safe_settings(tmp_path),httpx.MockTransport(handler))
        try:assert (await client.preflight())['connected']
        finally:await client.close()
    asyncio.run(run())


def test_rejects_ignored_context_override_before_chat(tmp_path):
    def handler(request):
        if request.url.path=='/v1/capabilities':return httpx.Response(200,json={})
        if request.url.path=='/api/show':return httpx.Response(200,json={'parameters':'num_ctx 4096'})
        return httpx.Response(200,json={'data':[{'enabled':True,'tools':sorted(SAFE_TOOLS)}]})
    async def run():
        client=HermesClient(safe_settings(tmp_path),httpx.MockTransport(handler))
        try:
            with pytest.raises(HermesError,match='64,000'):
                await client.preflight()
        finally:await client.close()
    asyncio.run(run())


def test_rejects_unrestricted_hermes(tmp_path):
    def handler(request):
        if request.url.path=='/v1/capabilities':return httpx.Response(200,json={})
        return httpx.Response(200,json={'data':[{'enabled':True,'tools':['jarvis_telemetry','terminal']}]})
    async def run():
        client=HermesClient(safe_settings(tmp_path),httpx.MockTransport(handler))
        try:
            with pytest.raises(HermesError):await client.preflight()
        finally:await client.close()
    asyncio.run(run())


def test_stream_does_not_duplicate_history_or_expose_tool_arguments(tmp_path):
    def handler(request):
        if request.method=='GET':return httpx.Response(200,json={'data':[{'role':'user','content':'Check CPU and GPU'},{'role':'tool','content':json.dumps({'source':'jarvis_desktop/v1','covered':['cpu','gpu'],'verified_summary':'Verified readings.'})}]})
        assert request.headers['x-hermes-session-id']=='session-test'
        body=json.loads(request.content)
        assert body['messages'][-1]=={'role':'user','content':'Check CPU and GPU'}
        assert [m['role'] for m in body['messages']]==['system','user']
        data='event: hermes.tool.progress\ndata: '+json.dumps({'tool_name':'jarvis_telemetry','args':{'secret':'NEVER-EXPOSE'}})+'\n\n'
        data+='data: '+json.dumps({'choices':[{'delta':{'content':'Verified readings.'}}]})+'\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(200,content=data,headers={'content-type':'text/event-stream'})
    async def run():
        client=HermesClient(Settings(state_dir=tmp_path,hermes_key='test'),httpx.MockTransport(handler))
        try:
            result=[r async for r in client.stream('Check CPU and GPU','session-test','request-test')]
            assert result[-1]['type']=='done'
            assert 'NEVER-EXPOSE' not in json.dumps(result)
            assert any(r['type']=='tool' for r in result)
        finally:await client.close()
    asyncio.run(run())


def test_live_claim_without_tool_execution_is_not_shown(tmp_path):
    async def run():
        transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'data':[]}) if request.method=='GET' else httpx.Response(200,text='data: {"choices":[{"delta":{"content":"CPU is 15%"}}]}\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'))
        client=HermesClient(Settings(state_dir=tmp_path,hermes_key='test'),transport)
        received=[]
        try:
            with pytest.raises(HermesError,match='unverified'):
                async for item in client.stream('Give me a system status report','session','request'):received.append(item)
            assert not any(item['type']=='delta' for item in received)
        finally:await client.close()
    asyncio.run(run())


def test_system_report_uses_current_tool_result_in_stream_and_history(tmp_path):
    verified='CPU usage is 12.0%; RAM usage is 40.0%. GPU temperature is 49.0°C.'
    rows=[{'role':'user','content':'Give me a system status report'},{'role':'tool','content':json.dumps({'source':'jarvis_desktop/v1','covered':['cpu','ram','gpu','battery','disk'],'verified_summary':verified})},{'role':'assistant','content':'Invented capacity is 8 GB.'}]
    def handler(request):
        if request.method=='GET':return httpx.Response(200,json={'data':rows})
        return httpx.Response(200,text='event: hermes.tool.progress\ndata: {"tool_name":"jarvis_telemetry"}\n\ndata: {"choices":[{"delta":{"content":"Invented capacity is 8 GB."}}]}\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n')
    async def run():
        client=HermesClient(Settings(state_dir=tmp_path,hermes_key='test'),httpx.MockTransport(handler))
        try:
            result=[e async for e in client.stream(rows[0]['content'],'session','request')]
            assert [e['text'] for e in result if e['type']=='delta']==[verified]
            assert (await client.history('session'))[-1]['text']==verified
        finally:await client.close()
    asyncio.run(run())


def test_overlapping_tool_reports_are_not_repeated():
    from app.hermes import tool_summary
    def receipt(covered,text):return {'role':'tool','content':json.dumps({'source':'jarvis_desktop/v1','covered':covered,'verified_summary':text})}
    rows=[{'role':'user','content':'Check CPU and GPU'},receipt(['cpu','gpu','ram'],'CPU and GPU report.'),receipt(['gpu'],'GPU duplicate.')]
    assert tool_summary(rows,{'cpu','gpu'})=='CPU and GPU report.'


def test_unrelated_or_only_running_tool_cannot_authorize_gpu_claim(tmp_path):
    def handler(request):
        if request.method=='GET':return httpx.Response(200,json={'data':[{'role':'user','content':'Check the current GPU temperature'},{'role':'tool','content':json.dumps({'source':'jarvis_desktop/v1','covered':['processes'],'verified_summary':'Process data only.'})}]})
        return httpx.Response(200,text='event: hermes.tool.progress\ndata: {"tool_name":"jarvis_processes","status":"running"}\n\ndata: {"choices":[{"delta":{"content":"GPU temperature is 17 degrees Celsius."}}]}\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n')
    async def run():
        client=HermesClient(Settings(state_dir=tmp_path,hermes_key='test'),httpx.MockTransport(handler))
        try:
            with pytest.raises(HermesError,match='relevant'):
                [e async for e in client.stream('Check the current GPU temperature','session','request')]
        finally:await client.close()
    asyncio.run(run())


def test_incomplete_stream_is_error(tmp_path):
    async def run():
        client=HermesClient(Settings(state_dir=tmp_path,hermes_key='test'),httpx.MockTransport(lambda r:httpx.Response(200,text='data: {"choices": [{"delta": {"content": "partial"}}]}\n\n')))
        try:
            with pytest.raises(HermesError): [r async for r in client.stream('hi','session-test','req-test')]
        finally:await client.close()
    asyncio.run(run())
