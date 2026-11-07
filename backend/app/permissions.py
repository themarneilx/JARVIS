from dataclasses import dataclass, field
from contextlib import nullcontext
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import threading
import time


def execute(argv):
    try:
        desktop_keys={'PATH','HOME','USER','LOGNAME','SHELL','LANG','DISPLAY','WAYLAND_DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS','HYPRLAND_INSTANCE_SIGNATURE','XDG_CURRENT_DESKTOP','XDG_SESSION_TYPE','DESKTOP_SESSION','XDG_DATA_DIRS','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME','QT_QPA_PLATFORM','GTK_THEME','NVIDIA_VISIBLE_DEVICES','__GLX_VENDOR_LIBRARY_NAME','__NV_PRIME_RENDER_OFFLOAD','GBM_BACKEND'}
        env={key:value for key,value in os.environ.items() if key in desktop_keys or key.startswith('LC_')}
        p = subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,timeout=20, check=False)
        return {'ok': p.returncode == 0, 'returncode': p.returncode, 'message': 'Operation completed' if p.returncode == 0 else 'Operation failed; inspect the selected service or desktop session'}
    except (OSError, subprocess.TimeoutExpired):
        return {'ok': False, 'message': 'Command unavailable or timed out'}


@dataclass
class ActionPolicy:
    services: tuple[str, ...] = ()
    applications: dict[str, tuple[str, ...]] = field(default_factory=dict)
    application_catalog: object | None = None
    terminal_catalog: object | None = None

    def command(self, kind: str, target: str) -> list[str]:
        if kind == 'terminal' and self.terminal_catalog is not None:
            return self.terminal_catalog.command(target)
        if kind in ('service_restart','service_start','service_stop'):
            if target not in self.services or not re.fullmatch(r'[a-zA-Z0-9_.@-]+\.service', target):
                raise ValueError('Service is not in the approved user-service allowlist')
            return ['systemctl','--user',kind.removeprefix('service_'),target]
        if kind == 'workspace' and re.fullmatch(r'[1-9][0-9]?', target):
            return ['hyprctl','dispatch','workspace',target]
        if kind == 'volume' and re.fullmatch(r'(?:[0-9]|[1-9][0-9]|100)', target):
            return ['wpctl','set-volume','@DEFAULT_AUDIO_SINK@',f'{target}%']
        if kind == 'brightness' and re.fullmatch(r'(?:[1-9]|[1-9][0-9]|100)', target):
            return ['brightnessctl','set',f'{target}%']
        if kind == 'launch' and self.application_catalog is not None:
            return self.application_catalog.command(target)
        if kind == 'launch' and target in self.applications:
            return list(self.applications[target])
        raise ValueError('Unsupported action or invalid target')


class ApprovalStore:
    def __init__(self, path: Path, policy: ActionPolicy, executor=execute):
        self.path, self.policy, self.executor = path, policy, executor
        self.lock = threading.Lock()
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS actions (id TEXT PRIMARY KEY, kind TEXT, target TEXT, effect TEXT, expires REAL, status TEXT, result TEXT, created REAL)')

    def db(self):
        return sqlite3.connect(self.path, timeout=5)

    def propose(self, kind, target, effect, ttl=120):
        self.policy.command(kind, target)
        action = {'id':secrets.token_urlsafe(24), 'kind':kind,'target':target,'effect':effect[:1600], 'expires':time.time()+min(ttl,300), 'status':'pending', 'created':time.time()}
        with self.db() as db:
            db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?)', (action['id'], kind, target, action['effect'], action['expires'], 'pending', None, action['created']))
        return action

    def list(self):
        with self.db() as db:
            db.row_factory = sqlite3.Row
            db.execute("UPDATE actions SET status='expired' WHERE status='pending' AND expires < ?", (time.time(),))
            return [dict(row) for row in db.execute('SELECT * FROM actions ORDER BY created DESC LIMIT 50')]

    def resolve(self, identifier, approve, authorization='review'):
        guard=getattr(self.policy.terminal_catalog,'lock',None) or nullcontext()
        with guard, self.lock, self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT * FROM actions WHERE id=?',(identifier,)).fetchone()
            if not row or row['status'] != 'pending' or row['expires'] < time.time():
                raise ValueError('Approval is unknown, expired, or already consumed')
            argv = self.policy.command(row['kind'],row['target']) if approve else None
            status = 'executing' if approve else 'rejected'
            db.execute('UPDATE actions SET status=? WHERE id=?',(status,identifier))
            db.commit()
            if not approve:
                return {'status':'rejected'}
            try:result = self.executor(argv)
            except Exception:result={'ok':False,'message':'Desktop execution failed'}
            result={**result,'authorization':authorization}
            status = 'executed' if result.get('ok') else 'failed'
            db.execute('UPDATE actions SET status=?,result=? WHERE id=?',(status,json.dumps(result),identifier))
            return {'status':status,'result':result,'kind':row['kind']}
