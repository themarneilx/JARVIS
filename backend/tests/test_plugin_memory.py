import importlib.util,io,json
from pathlib import Path
from urllib.error import HTTPError

path=Path(__file__).resolve().parents[2]/'hermes/plugins/jarvis_desktop/__init__.py'
spec=importlib.util.spec_from_file_location('memory_plugin_test',path)
plugin=importlib.util.module_from_spec(spec);spec.loader.exec_module(plugin)


def test_validation_errors_reach_the_model_without_echoing_input(monkeypatch):
    class Opener:
        def open(self,*args,**kwargs):
            body={'detail':[{'loc':['body','reason'],'msg':'String should have at most 300 characters','input':'NEVER-ECHO-CREDENTIAL'}]}
            raise HTTPError('http://127.0.0.1/api/internal/memory/proposals',422,'Invalid',{},io.BytesIO(json.dumps(body).encode()))
    monkeypatch.setattr(plugin.urllib.request,'build_opener',lambda *args:Opener())
    result=json.loads(plugin.call('/memory/proposals',{}))
    assert '300 characters' in result['error']
    assert 'NEVER-ECHO' not in json.dumps(result)


def test_memory_tool_contract_requires_content_and_bounds_reason():
    tools={}
    class Context:
        def register_tool(self,**kwargs):tools[kwargs['name']]=kwargs
        def register_skill(self,*args):pass
        def register_hook(self,*args):pass
        def register_middleware(self,*args):pass
    plugin.register(Context())
    schema=tools['jarvis_memory_propose']['schema']['parameters']
    assert 'content' in schema['required']
    assert schema['properties']['reason']['maxLength']==300
    assert schema['properties']['content']['maxLength']==2200


def test_native_turn_context_is_forwarded_outside_model_arguments(monkeypatch):
    observed=[]
    class Opener:
        def open(self,request,**kwargs):
            observed.append(request)
            class Response:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def read(self,*args):return b'{}'
            return Response()
    monkeypatch.setattr(plugin.urllib.request,'build_opener',lambda *args:Opener())
    plugin.native_turn_start(session_id='session',turn_id='native-turn',user_message='Run fastfetch')
    plugin.native_tool_context(session_id='session',turn_id='native-turn',next_call=lambda:plugin.call('/terminal/propose',{'command_id':'cmd-fixture'}))
    assert json.loads(observed[0].data)['prompt_hash'] and 'Run fastfetch' not in observed[0].data.decode()
    assert dict(observed[1].header_items())['X-jarvis-native-turn']=='native-turn'
    assert dict(observed[1].header_items())['X-jarvis-native-session']=='session'
    assert json.loads(observed[1].data)=={'command_id':'cmd-fixture'}
    plugin.call('/terminal/propose',{'command_id':'cmd-fixture'})
    assert 'X-jarvis-native-turn' not in dict(observed[-1].header_items())
