import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.hermes import HermesClient


SPEC = {'name':'Morning briefing','trigger':'daily','time':'07:00','date':'','timezone':'Asia/Manila','weekdays':[0,1,2,3,4,5,6],'threshold':20,'message':'Good morning.','weather':True,'chime':True,'delivery':'auto'}
PROPOSAL = {'id':'shortcut-proposal-fixture','summary':'Daily at 07:00 Asia/Manila; weather briefing.','spec':SPEC}
RECEIPT = {'source':'jarvis_shortcuts/v1','status':'pending',**PROPOSAL}
PROMPT = 'Set an alarm for 7 AM every day and tell me the weather.'


def client_with(tmp_path, tool=None, pending=(), shortcuts=(), states=None, prompt=PROMPT, chunks=None, progress=False):
    rows=[{'role':'user','content':prompt}]
    if tool is not None:
        rows.append({'role':'tool','tool_name':'jarvis_shortcuts','content':json.dumps(tool)})
    rows.append({'role':'assistant','content':'Your alarm is set and will wake the laptop every day.'})
    payloads=[]
    def handler(request):
        if request.method=='GET':return httpx.Response(200,json={'data':rows})
        payloads.append(json.loads(request.content))
        body=''.join('data: '+json.dumps({'choices':[{'delta':{'content':chunk}}]})+'\n\n' for chunk in (chunks or [rows[-1]['content']]))
        if progress:body+='event: hermes.tool.progress\ndata: {"tool_name":"jarvis_shortcuts"}\n\n'
        body+='data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        return httpx.Response(200,text=body)
    client=HermesClient(Settings(state_dir=tmp_path),httpx.MockTransport(handler))
    client.shortcut_inventory=lambda:{'pending':list(pending),'shortcuts':list(shortcuts),'proposal_states':states or {}}
    client.shortcut_context=lambda:{'timezone':'Asia/Manila','now':'2026-11-06T16:00:00+08:00','location_label':'Cebu City'}
    return client,payloads


@pytest.mark.parametrize('tool',[None,{'error':'Use time in HH:mm format'},RECEIPT])
def test_alarm_claim_needs_exact_live_shortcut_proposal(tmp_path,tool):
    async def run():
        client,_=client_with(tmp_path,tool=tool,pending=[{**PROPOSAL,'spec':{**SPEC,'time':'08:00'}}])
        try:
            events=[e async for e in client.stream(PROMPT,'session','request')]
            text=''.join(e.get('text','') for e in events if e['type']=='delta')
            assert "haven't prepared" in text
            assert 'wake the laptop' not in text and 'alarm is set' not in text
            assert (await client.history('session'))[-1]['text']==text
        finally:await client.close()
    asyncio.run(run())


def test_pending_alarm_is_reviewable_and_needs_no_current_weather_receipt(tmp_path):
    async def run():
        client,payloads=client_with(tmp_path,tool=RECEIPT,pending=[PROPOSAL])
        try:
            events=[e async for e in client.stream(PROMPT,'session','request')]
            text=''.join(e.get('text','') for e in events if e['type']=='delta')
            assert 'prepared' in text and 'permission popup' in text
            assert 'not enabled' in text and PROPOSAL['summary'] in text
            instructions=payloads[0]['messages'][0]['content']
            assert 'Asia/Manila' in instructions and '2026-11-06T16:00:00+08:00' in instructions
            assert '"time":"07:00"' in instructions
            assert 'This turn requires successful jarvis_online calls' not in instructions
            assert 'This turn requires live Linux evidence' not in instructions
            assert (await client.history('session'))[-1]['text']==text
        finally:await client.close()
    asyncio.run(run())


def test_battery_warning_prioritizes_shortcut_over_live_telemetry(tmp_path):
    async def run():
        prompt='Check the battery and warn me whenever it goes below 20 percent.'
        client,payloads=client_with(tmp_path,prompt=prompt)
        try:
            events=[e async for e in client.stream(prompt,'session','request')]
            text=''.join(e.get('text','') for e in events if e['type']=='delta')
            assert "haven't prepared" in text
            assert 'This turn requires live Linux evidence' not in payloads[0]['messages'][0]['content']
        finally:await client.close()
    asyncio.run(run())


@pytest.mark.parametrize('prefix',["I've",'I have','Your alarm is'])
def test_chunked_unsolicited_alarm_claim_is_never_streamed(tmp_path,prefix):
    async def run():
        chunks=[prefix[:1],prefix[1:],' set an alarm for 7 AM. ']
        client,_=client_with(tmp_path,prompt='Say hello.',chunks=chunks,progress=True)
        try:
            events=[e async for e in client.stream('Say hello.','session','request')]
            text=''.join(e.get('text','') for e in events if e['type']=='delta')
            assert "haven't prepared" in text
            assert 'set an alarm' not in text
        finally:await client.close()
    asyncio.run(run())


def test_history_only_calls_approved_shortcut_enabled_when_it_matches_current_saved_spec(tmp_path):
    async def run():
        for saved,enabled in [({'id':'saved','spec':SPEC,'enabled':True},True),({'id':'saved','spec':{**SPEC,'time':'09:00'},'enabled':True},False),({'id':'saved','spec':SPEC,'enabled':False},False)]:
            client,_=client_with(tmp_path,tool=RECEIPT,shortcuts=[saved],states={PROPOSAL['id']:{'status':'approved','shortcut_id':'saved'}})
            try:
                text=(await client.history('session'))[-1]['text']
                assert ('is enabled' in text)==enabled
                assert 'wake the laptop' not in text
            finally:await client.close()
    asyncio.run(run())


def test_alarm_detection_does_not_steal_weather_or_general_questions():
    from app.shortcut_chat import alarm_request
    for text in [PROMPT,'Wake me up at 7 AM tomorrow.','Warn me when my battery falls below 20 percent.','Create a morning briefing for 7 AM.','Set a reminder for 17:30.','Show my shortcuts.']:
        assert alarm_request(text),text
    for text in ['What is the weather at 7 AM tomorrow?','What is an alarm?','Translate "set an alarm for seven" into Spanish.','Check the current battery.','How do I set an alarm?','What is a keyboard shortcut?']:
        assert not alarm_request(text),text


@pytest.mark.parametrize('prompt',['Notify me when the battery reaches 20%.','Set up a warning when my battery gets low.','At 7 AM every morning, read me the weather.'])
def test_natural_warning_and_briefing_requests_use_shortcuts(prompt):
    from app.shortcut_chat import alarm_request
    assert alarm_request(prompt)


def test_shortcut_inventory_receipt_cannot_hide_new_saved_shortcuts():
    from app.shortcut_chat import shortcut_feedback
    rows=[{'role':'user','content':'List my shortcuts.'},{'role':'tool','tool_name':'jarvis_shortcuts','content':json.dumps({'source':'jarvis_shortcuts/v1','shortcuts':[],'pending':[]})}]
    text=shortcut_feedback(rows,{'shortcuts':[{'id':'saved','spec':SPEC,'enabled':True,'summary':PROPOSAL['summary']}],'pending':[]})
    assert 'no saved' not in text
    assert 'No valid' in text


@pytest.mark.parametrize('claim',["I've scheduled your 7 AM alarm.",'Your 7 AM alarm is now set.',"I'll wake you up at 7 AM.",'Done. The morning briefing has been enabled.'])
def test_scheduling_claim_variations_require_verification(claim):
    from app.shortcut_chat import shortcut_claim
    assert shortcut_claim(claim)
