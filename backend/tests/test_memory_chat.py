import asyncio,json
import httpx,pytest
from app.config import Settings
from app.hermes import HermesClient


PROPOSAL={'id':'review-fixture','action':'add','target':'user','content':"User's name is Alex. Address the user formally as sir.",'old_text':'','reason':'Explicit user preference'}
PROMPT='My name is Alex. Please remember that and address me formally as sir.'


def client_with(tmp_path,tool=None,pending=(),entries=(),states=None):
    rows=[{'role':'user','content':PROMPT}]
    if tool:rows.append({'role':'tool','tool_name':'jarvis_memory_propose','content':json.dumps(tool)})
    rows.append({'role':'assistant','content':'Your name is locked into core memory forever. How can I assist you? '})
    def handler(request):
        if request.method=='GET':return httpx.Response(200,json={'data':rows})
        return httpx.Response(200,text='data: '+json.dumps({'choices':[{'delta':{'content':rows[-1]['content']}}]})+'\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n')
    client=HermesClient(Settings(state_dir=tmp_path),httpx.MockTransport(handler))
    async def inventory():return {'entries':list(entries),'pending':list(pending),'proposal_states':states or {}}
    client.memory_inventory=inventory
    return client


@pytest.mark.parametrize('tool',[None,{'error':'The old entry does not match current memory.'},{'error':'reason: String should have at most 300 characters'}])
def test_missing_or_failed_proposal_cannot_claim_saved(tmp_path,tool):
    async def run():
        client=client_with(tmp_path,tool=tool)
        try:
            events=[e async for e in client.stream(PROMPT,'session','request')]
            text=''.join(e.get('text','') for e in events if e['type']=='delta')
            assert "haven't saved" in text
            assert 'locked' not in text and 'forever' not in text
            assert (await client.history('session'))[-1]['text']==text
        finally:await client.close()
    asyncio.run(run())


def test_pending_receipt_requires_the_exact_live_review(tmp_path):
    async def run():
        receipt={'source':'jarvis_memory/v1','status':'pending',**PROPOSAL}
        for pending,should_match in [([PROPOSAL],True),([{**PROPOSAL,'content':'Something unrelated'}],False),([],False)]:
            client=client_with(tmp_path,tool=receipt,pending=pending)
            try:
                events=[e async for e in client.stream(PROMPT,'session','request')]
                text=''.join(e.get('text','') for e in events if e['type']=='delta')
                if should_match:
                    assert 'USER.md' in text and 'approve' in text.casefold() and 'not saved' in text.casefold()
                else:assert "haven't saved" in text
            finally:await client.close()
    asyncio.run(run())


def test_history_reports_approval_only_when_the_native_fact_is_present(tmp_path):
    async def run():
        receipt={'source':'jarvis_memory/v1','status':'pending',**PROPOSAL}
        for entries,saved in [([{'target':'user','text':PROPOSAL['content']}],True),([],False)]:
            client=client_with(tmp_path,tool=receipt,entries=entries,states={PROPOSAL['id']:'approved'})
            try:
                text=(await client.history('session'))[-1]['text']
                assert ('is saved in USER.md' in text)==saved
                if not saved:assert 'not present' in text
            finally:await client.close()
    asyncio.run(run())


def test_memory_intent_does_not_steal_name_queries_or_hardware_questions():
    from app.memory_chat import memory_request
    for text in [PROMPT,'save it to core memory','you did not save it to user.md and memory.md','Forget my saved deployment preference.']:
        assert memory_request(text)
    for text in ["What's my name?",'Do you remember my name?','Check current RAM memory usage.','How does memory work?','Translate "my name is Alex" into Cebuano.','Translate "Call me Alex from now on" into Spanish.']:
        assert not memory_request(text)


def test_history_drops_orphaned_assistant_rows_from_a_truncated_page(tmp_path):
    async def run():
        rows=[{'role':'assistant','content':'I have saved your name permanently.'},{'role':'user','content':'Hello Jarvis.'},{'role':'assistant','content':'Hello, sir.'}]
        client=HermesClient(Settings(state_dir=tmp_path),httpx.MockTransport(lambda r:httpx.Response(200,json={'data':rows})))
        try:assert [r['text'] for r in await client.history('session')]==['Hello Jarvis.','Hello, sir.']
        finally:await client.close()
    asyncio.run(run())


@pytest.mark.parametrize('prompt',["Call me Alex from now on.","Say hello."])
@pytest.mark.parametrize('apostrophe',["I have",'I’ve'])
def test_early_chunked_saved_claim_is_never_streamed_before_failed_tool(tmp_path,prompt,apostrophe):
    async def run():
        rows=[{'role':'user','content':prompt},{'role':'assistant','content':'I have saved your name in USER.md.'},{'role':'tool','tool_name':'jarvis_memory_propose','content':'{"error":"Proposal rejected"}'}]
        chunks=[apostrophe[0],apostrophe[1:],' sav','ed your name in USER.md. ']
        body=''.join('data: '+json.dumps({'choices':[{'delta':{'content':part}}]})+'\n\n' for part in chunks)
        body+='event: hermes.tool.progress\ndata: {"tool_name":"jarvis_memory_propose"}\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        client=HermesClient(Settings(state_dir=tmp_path),httpx.MockTransport(lambda r:httpx.Response(200,json={'data':rows}) if r.method=='GET' else httpx.Response(200,text=body)))
        async def inventory():return {'entries':[],'pending':[]}
        client.memory_inventory=inventory
        try:
            events=[e async for e in client.stream(prompt,'session','request')]
            text=''.join(e.get('text','') for e in events if e['type']=='delta')
            assert 'I have saved' not in text
            assert "haven't saved" in text
        finally:await client.close()
    asyncio.run(run())
