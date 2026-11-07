import asyncio,json
import httpx
from app.config import Settings
from app.hermes import HermesClient


def test_simple_greetings_and_names_cannot_include_unsolicited_diagnostics(tmp_path):
    async def run():
        def handler(request):
            if request.method=='GET':return httpx.Response(200,json={'data':[]})
            return httpx.Response(200,text='data: '+json.dumps({'choices':[{'delta':{'content':'I am someone else. CPU is 88%, and my system requires three sentences.'}}]})+'\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n')
        agent=HermesClient(Settings(state_dir=tmp_path),httpx.MockTransport(handler))
        async def inventory():return {'entries':[{'target':'memory','text':'User name changed to Alex, address adjusted to "sir".'}]}
        agent.memory_inventory=inventory
        try:
            for question,expected in [('Hello Jarvis.','Hello, sir.'),("What's your name again?",'My name is Jarvis, sir.'),("And what's my name?",'Your name is Alex, sir.')]:
                events=[e async for e in agent.stream(question,'session','request')]
                assert ''.join(e.get('text','') for e in events if e['type']=='delta')==expected
        finally:await agent.close()
    asyncio.run(run())


def test_unknown_user_name_is_not_inferred_from_account_or_ambiguous_memory(tmp_path):
    from app.conversation_style import simple_reply, simple_intent
    entries=[{'target':'memory','text':"Jarvis is a local assistant; actual name is Someone, the user's real name."}]
    assert simple_reply('user_name',entries)=="What would you like me to call you, sir?"
    assert simple_intent('Hello Jarvis, check my GPU.') is None
    assert simple_intent('What is the name of your model?') is None


def test_history_applies_the_same_greeting_constraint_and_failure_stays_failure(tmp_path):
    async def run():
        rows=[{'role':'user','content':'Hello Jarvis.'},{'role':'assistant','content':'My name is Jarvis. CPU is 88%.'}]
        def handler(request):
            if request.method=='GET':return httpx.Response(200,json={'data':rows})
            return httpx.Response(503)
        agent=HermesClient(Settings(state_dir=tmp_path),httpx.MockTransport(handler))
        try:
            assert [r['text'] for r in await agent.history('session')]==['Hello Jarvis.','Hello, sir.']
            from app.hermes import HermesError
            import pytest
            with pytest.raises(HermesError):
                async for _ in agent.stream('Hello Jarvis.','session','request'):pass
        finally:await agent.close()
    asyncio.run(run())


def test_conflicting_or_deleted_names_are_not_revived():
    from app.conversation_style import simple_reply
    one={'target':'user','text':"User's preferred name: Alex."}
    two={'target':'memory','text':'User name changed to Sam, address adjusted to sir.'}
    assert simple_reply('user_name',[one,two])=="What would you like me to call you, sir?"
    assert simple_reply('user_name',[{**one,'previously_deleted':True}])=="What would you like me to call you, sir?"
