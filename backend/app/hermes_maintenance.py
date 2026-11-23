import os
from pathlib import Path

from .runtime import discover_runtime


def update_command(root: Path, source: str, python: str) -> tuple[str, list[str]]:
    overrides = {'HERMES_SOURCE': source, 'HERMES_PYTHON': python}
    runtime = discover_runtime(root, environ=overrides)
    shared = Path.home() / '.hermes/hermes-agent'
    launcher = Path.home() / '.local/bin/hermes'
    if (runtime.source.resolve() != shared.resolve() or not (shared / '.git').exists()
            or not launcher.is_file() or not os.access(launcher, os.X_OK)):
        raise ValueError('The shared Hermes source installation is unavailable. Use the updater for your install.')

    kitty = Path('/usr/bin/kitty')
    runner = root / 'scripts/update-hermes.py'
    interpreter = root / '.venv/bin/python'
    if not kitty.is_file() or not os.access(kitty, os.X_OK) or not runner.is_file() or not interpreter.is_file():
        raise ValueError('Hermes update needs Kitty and the Jarvis Python environment on this PC.')
    return runtime.version, [
        str(kitty), '--detach', '--session', 'none', '--hold', '--title', 'Hermes update',
        '--directory', str(root), '--', str(interpreter), str(runner),
    ]
