import importlib.util
import json
from pathlib import Path


path=Path(__file__).resolve().parents[2]/'hermes/plugins/jarvis_desktop/__init__.py'
spec=importlib.util.spec_from_file_location('shortcuts_plugin_test',path)
plugin=importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


def registered_tools():
    tools={}
    class Context:
        def register_tool(self,**kwargs):tools[kwargs['name']]=kwargs
        def register_skill(self,*args):pass
        def register_hook(self,*args):pass
        def register_middleware(self,*args):pass
    plugin.register(Context())
    return tools


def test_reviewed_shortcut_tool_strips_operation_and_preserves_server_defaults(monkeypatch):
    calls=[]
    def call(path,body=None):
        calls.append((path,body))
        return json.dumps({'source':'jarvis_shortcuts/v1','status':'pending','id':'proposal','summary':'At 07:00.','spec':{'name':'Alarm','trigger':'once','time':'07:00'}})
    monkeypatch.setattr(plugin,'call',call)
    tools=registered_tools()
    assert len(tools)==14
    result=json.loads(tools['jarvis_shortcuts']['handler']({'operation':'propose','name':'Alarm','trigger':'once','time':'07:00'}))
    assert calls==[('/shortcuts/proposals',{'name':'Alarm','trigger':'once','time':'07:00'})]
    assert result['source']=='jarvis_shortcuts/v1' and result['status']=='pending'


def test_reviewed_shortcut_tool_lists_and_refuses_authority_fields(monkeypatch):
    calls=[]
    monkeypatch.setattr(plugin,'call',lambda path,body=None:calls.append((path,body)) or '{}')
    tool=registered_tools()['jarvis_shortcuts']
    tool['handler']({'operation':'list'})
    assert calls==[('/shortcuts',None)]
    for body in [{'operation':'approve','id':'proposal'},{'operation':'propose','enabled':True},{'operation':'run'},{'operation':'list','time':'07:00'}]:
        assert json.loads(tool['handler'](body)).get('error')
    assert calls==[('/shortcuts',None)]
    parameters=tool['schema']['parameters']
    assert parameters['additionalProperties'] is False
    assert parameters['properties']['operation']['enum']==['list','propose']
    assert parameters['properties']['message']['maxLength']==500
    assert parameters['properties']['name']['maxLength']==80
    assert parameters['properties']['timezone']['maxLength']==80
    assert parameters['properties']['threshold']['maximum']==50
    assert parameters['properties']['delivery']['enum']==['auto','browser','desktop']
