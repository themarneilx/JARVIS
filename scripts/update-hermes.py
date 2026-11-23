#!/usr/bin/env python3
"""Run the shared Hermes updater from a local interactive terminal."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.process_control import stop_recorded


def main():
    if os.geteuid() == 0 or not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise ValueError('Open the Hermes updater in a terminal as your normal desktop user.')

    launcher = Path.home() / '.local/bin/hermes'
    runtime = ROOT / '.runtime'
    runtime.mkdir(mode=0o700, exist_ok=True)
    descriptor = os.open(runtime / 'hermes-update.lock', os.O_CREAT | os.O_NOFOLLOW | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('A Hermes update terminal is already open.') from None

        env = {
            key: value for key, value in os.environ.items()
            if key in {'HOME', 'USER', 'LOGNAME', 'LANG', 'TERM', 'COLORTERM', 'XDG_RUNTIME_DIR',
                       'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_STATE_HOME', 'DBUS_SESSION_BUS_ADDRESS'}
            or key.startswith('LC_')
        }
        env['PATH'] = f'{Path.home() / ".local/bin"}:/usr/bin:/bin'
        env['HERMES_HOME'] = str(Path.home() / '.hermes')

        subprocess.run([str(launcher), 'update', '--plan'], env=env, check=True)
        print('\nThis updates the Hermes installation used by Jarvis and your regular Hermes profile.')
        print('Jarvis will stop, and Hermes may restart or refresh its own gateway services.')
        if input('Type UPDATE to proceed, or press Enter to cancel: ').strip() != 'UPDATE':
            print('Update cancelled.')
            return

        for name in ('backend', 'hermes'):
            stop_recorded(ROOT, name, wait_seconds=20)
        subprocess.run([str(launcher), 'update'], env=env, check=True)
        print('\nHermes updater finished. Jarvis will verify the installation on its next startup.')

    if input('Start Jarvis now? [y/N] ').strip().casefold() in {'y', 'yes'}:
        project_env = os.environ | {'HERMES_HOME': str(ROOT / 'hermes/runtime')}
        subprocess.run(['/usr/bin/npm', 'start', '--', '--no-browser'], cwd=ROOT, env=project_env, check=True)


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        sys.exit('\nHermes update terminal closed.')
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        sys.exit(f'\nHermes maintenance stopped: {exc}')
