"""Read-only discovery of a Hermes installation and its committed Python environment."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class HermesRuntime:
    source: Path
    python: Path
    version: str = 'unknown'
    commit: str = ''


def profile_home(project:Path, selected:str|None=None):
    expected=project.resolve()/'hermes/runtime'
    chosen=Path(selected).expanduser() if selected else expected
    if chosen.resolve()!=expected:
        raise ValueError('J.A.R.V.I.S. launchers require the dedicated project hermes/runtime home; unset inherited HERMES_HOME.')
    for name in ('.env','config.yaml','SOUL.md','memories','memories/USER.md','memories/MEMORY.md'):
        if (expected/name).is_symlink():
            raise ValueError('The dedicated profile identity, configuration and memories must not be symlinks.')
    return expected


def _runtime(source:Path,python:Path):
    if not (source/'hermes_cli/main.py').is_file() or not python.is_file():
        raise ValueError('Hermes source or Python interpreter is missing')
    try:
        stamp=json.loads((source/'install-stamp.json').read_text())
    except (OSError,ValueError):
        stamp={}
    return HermesRuntime(source,python,str(stamp.get('baseVersion','unknown')),str(stamp.get('commit','')))


def discover_runtime(project:Path,user_home:Path|None=None,environ:Mapping[str,str]|None=None):
    user_home=user_home or Path.home()
    environ=os.environ if environ is None else environ
    configured_source=environ.get('HERMES_SOURCE')
    configured_python=environ.get('HERMES_PYTHON')
    if configured_source and configured_python:
        return _runtime(Path(configured_source).expanduser(),Path(configured_python).expanduser())
    if bool(configured_source)!=bool(configured_python):
        raise ValueError('Set both HERMES_SOURCE and HERMES_PYTHON for an explicit Hermes runtime')
    local=project/'.runtime/hermes-venv'
    if (local/'bin/hermes').is_file():
        return _runtime(project/'.runtime/hermes-agent',local/'bin/python')
    source=user_home/'.hermes/hermes-agent'
    if (source/'hermes_cli/main.py').is_file():
        key=hashlib.sha256(str(source.resolve()).encode()).hexdigest()[:16]
        state=user_home/'.hermes/installs'/key
        facts=state/'facts.json'
        if facts.is_file():
            try:
                recorded=json.loads(facts.read_text())['packages']['venv']['environment']
                generation=Path(recorded)
            except (OSError,ValueError,KeyError,TypeError) as exc:
                raise ValueError('Hermes committed dependency metadata is invalid') from exc
            if not generation.resolve().is_relative_to((state/'environments').resolve()) or not (generation/'pyvenv.cfg').is_file():
                raise ValueError('Hermes dependency environment is missing or outside its committed install')
            return _runtime(source,generation/'bin/python')
        for name in ('.venv','venv'):
            python=source/name/'bin/python'
            if python.is_file():return _runtime(source,python)
    raise ValueError('Hermes runtime not found. Install Hermes or configure HERMES_SOURCE and HERMES_PYTHON.')
