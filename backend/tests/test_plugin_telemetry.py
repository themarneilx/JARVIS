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
