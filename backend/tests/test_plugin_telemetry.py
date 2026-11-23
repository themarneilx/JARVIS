import importlib.util
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[2]/'hermes/plugins/jarvis_desktop/__init__.py'
spec=importlib.util.spec_from_file_location('jarvis_desktop',path)
plugin=importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


def test_overview_preserves_readings_and_faults_without_full_service_inventory():
    data={'sampled_at':123,'cpu_percent':47.2,'gpu':{'vram_total_mb':6141},'services':[{'unit':'running.service','active':'active'},{'unit':'broken.service','active':'failed'}],'desktop':{'clients':[{'class':'Terminal'},{'class':'Terminal'}]}}
    summary=plugin.telemetry_view(data)
    assert summary['cpu_percent']==47.2 and summary['gpu']['vram_total_mb']==6141
    assert summary['services']=={'running':1,'failed':[{'unit':'broken.service','active':'failed'}]}
    assert summary['desktop']['applications']==['Terminal']
    assert plugin.telemetry_view(data,'services')['services']==data['services']
    assert plugin.telemetry_view({'services':None})['services'] is None
    with pytest.raises(ValueError):plugin.telemetry_view(data,'terminal')


def test_summary_preserves_temperature_and_converts_reported_vram_units():
    summary=plugin.verified_summary({'cpu_percent':12,'ram':{'percent':40},'gpu':{'temperature':49,'vram_used_mb':3072,'vram_total_mb':6144},'disk':{'percent':90}})
    assert '49.0°C' in summary and '3.00 of 6.00 GiB' in summary
    assert not any(word in summary for word in ('critical','healthy','high temperature'))
    assert 'unavailable' in plugin.verified_summary({})


def test_general_browser_turn_omits_tools_from_provider_request():
    request = {'messages': [
        {'role': 'system', 'content': 'Jarvis profile\n\nAnswer this turn without tools.'},
        {'role': 'user', 'content': 'What is the capital of Japan?'},
    ], 'tools': [{'type': 'function', 'function': {'name': 'jarvis_telemetry'}}], 'tool_choice': 'auto'}
    changed = plugin.focus_web_chat(request, platform='api_server')['request']
    assert 'tools' not in changed and 'tool_choice' not in changed
    assert changed['messages'] == request['messages']
    assert 'tools' in request
    assert plugin.focus_web_chat(request, platform='cli') is None
    request['messages'][0]['content'] = 'Jarvis profile'
    request['messages'][1]['content'] = 'Answer this turn without tools.'
    assert plugin.focus_web_chat(request, platform='api_server') is None


def test_standalone_question_omits_old_diagnostics_from_model_context():
    system = {'role': 'system', 'content': 'Jarvis profile\n\nAnswer this turn without tools.'}
    prior_chat = [{'role': 'user', 'content': 'Hello'}, {'role': 'assistant', 'content': 'Good evening.'}]
    diagnostic = [
        {'role': 'user', 'content': 'Check CPU and GPU'},
        {'role': 'assistant', 'tool_calls': [{'function': {'name': 'jarvis_telemetry'}}]},
        {'role': 'tool', 'content': 'Measured readings.'},
        {'role': 'assistant', 'content': 'CPU usage is 20%.'},
    ]
    question = {'role': 'user', 'content': 'What is the capital of Japan?'}
    request = {'messages': [system, *prior_chat, *diagnostic, question], 'tools': []}
    focused = plugin.focus_web_chat(request, platform='api_server')['request']
    assert focused['messages'] == [system, *prior_chat, question]
    assert request['messages'] == [system, *prior_chat, *diagnostic, question]

    follow_up = {'role': 'user', 'content': 'Why was it that high?'}
    request['messages'][-1] = follow_up
    focused = plugin.focus_web_chat(request, platform='api_server')['request']
    assert focused['messages'] == [system, *prior_chat, *diagnostic, follow_up]


def test_live_reading_provider_request_hides_unrelated_tools():
    names = ['jarvis_telemetry', 'jarvis_processes', 'jarvis_memory_propose']
    request = {
        'messages': [{'role': 'system', 'content': 'Jarvis profile\n\nTools for this turn: jarvis_telemetry.'}],
        'tools': [{'type': 'function', 'function': {'name': name}} for name in names],
    }
    focused = plugin.focus_web_chat(request, platform='api_server')['request']
    assert [tool['function']['name'] for tool in focused['tools']] == ['jarvis_telemetry']
    assert len(request['tools']) == 3
