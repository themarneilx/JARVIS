"""Copy the reviewed project plugin into the dedicated Hermes home before launch."""
from datetime import datetime,timezone
from pathlib import Path
import os,shutil,sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.runtime import profile_home


def sync():
    home=profile_home(ROOT,os.getenv('HERMES_HOME'))
    source=ROOT/'hermes/plugins/jarvis_desktop'
    target=home/'plugins/jarvis_desktop'
    if (home/'plugins').is_symlink() or target.is_symlink():raise ValueError('Native plugin directories must not be symlinks')
    expected={p.relative_to(source):p.read_bytes() for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    if target.exists():
        if any(p.is_symlink() for p in target.rglob('*')):raise ValueError('Native plugin files must not be symlinks')
        actual={p.relative_to(target):p.read_bytes() for p in target.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        if actual==expected:return
        backups=home/'backups';backups.mkdir(mode=0o700,exist_ok=True)
        shutil.copytree(target,backups/('jarvis-plugin-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')))
    for relative,data in expected.items():
        path=target/relative;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        path.write_bytes(data);path.chmod(0o600)
    print('Updated the dedicated Jarvis plugin; previous files are backed up. Global Hermes was unchanged.')


if __name__=='__main__':sync()
