import hashlib
import json
from pathlib import Path
import pytest
from app.runtime import discover_runtime, profile_home


def managed_install(tmp_path):
    home=tmp_path/'user'
    source=home/'.hermes/hermes-agent'
    (source/'hermes_cli').mkdir(parents=True)
    (source/'hermes_cli/main.py').touch()
    (source/'install-stamp.json').write_text(json.dumps({'baseVersion':'0.22.6','commit':'installed-sha'}))
    key=hashlib.sha256(str(source.resolve()).encode()).hexdigest()[:16]
    state=home/'.hermes/installs'/key
    generation=state/'environments/generation-a/venv'
    (generation/'bin').mkdir(parents=True)
    (generation/'bin/python').touch()
    (generation/'pyvenv.cfg').write_text('version_info = 3.14.9\n')
    (state/'facts.json').write_text(json.dumps({'packages':{'venv':{'environment':str(generation)}}}))
    return home,source,state,generation


def test_reuses_installed_managed_runtime_without_changing_identity(tmp_path):
    home,source,state,generation=managed_install(tmp_path)
    original=(state/'facts.json').read_bytes()
    runtime=discover_runtime(tmp_path/'project',home,{})
    assert runtime.source==source
    assert runtime.python==generation/'bin/python'
    assert runtime.version=='0.22.6'
    assert (state/'facts.json').read_bytes()==original
    assert not (home/'.hermes/SOUL.md').exists()


def test_resolves_current_generation_on_every_launch(tmp_path):
    home,source,state,old=managed_install(tmp_path)
    new=state/'environments/generation-b/venv'
    (new/'bin').mkdir(parents=True)
    (new/'bin/python').touch();(new/'pyvenv.cfg').touch()
    (state/'facts.json').write_text(json.dumps({'packages':{'venv':{'environment':str(new)}}}))
    assert discover_runtime(tmp_path/'project',home,{}).python==new/'bin/python'


def test_refuses_environment_outside_committed_install(tmp_path):
    home,source,state,generation=managed_install(tmp_path)
    (state/'facts.json').write_text(json.dumps({'packages':{'venv':{'environment':'/tmp/untrusted'}}}))
    with pytest.raises(ValueError):discover_runtime(tmp_path/'project',home,{})


def test_no_installation_reports_actionable_error(tmp_path):
    with pytest.raises(ValueError,match='Hermes'):
        discover_runtime(tmp_path/'project',tmp_path/'user',{})


def test_launcher_refuses_global_or_symlinked_profile(tmp_path):
    project=tmp_path/'project'
    expected=project/'hermes/runtime'
    expected.mkdir(parents=True)
    assert profile_home(project,str(expected))==expected
    with pytest.raises(ValueError,match='dedicated'):
        profile_home(project,str(tmp_path/'user/.hermes'))
    global_config=tmp_path/'global.yaml';global_config.write_text('model: private')
    (expected/'config.yaml').symlink_to(global_config)
    with pytest.raises(ValueError,match='symlink'):
        profile_home(project,str(expected))
