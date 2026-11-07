"""Browser-owned command recipes. Agent tools can select IDs, never supply argv."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import secrets
import sqlite3
import stat
import threading

from .home_files import HomeFiles
from .memory import redact


_BLOCKED = {'sudo','sudoedit','su','pkexec','doas','runuser','gksu','gksudo','kdesu','kdesudo',
            'sh','bash','zsh','dash','fish','ksh','csh','tcsh','env','xargs','eval','exec',
            'chroot','unshare','nsenter','systemctl','loginctl','reboot','shutdown','poweroff','halt'}


class DesktopAccess:
    def __init__(self, path, home=None, bin_dir=None):
        self.path=Path(path)
        self.home=Path.home() if home is None else Path(home)
        self.bin_dir=Path('/usr/bin') if bin_dir is None else Path(bin_dir)
        self.files=HomeFiles(self.home)
        self.lock=threading.RLock()
        if self.path.is_symlink():raise ValueError('Desktop permission database must be a regular file')
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS policy (id INTEGER PRIMARY KEY CHECK(id=1), ask INTEGER NOT NULL)')
            first_run=db.execute('INSERT OR IGNORE INTO policy VALUES (1,1)').rowcount==1
            db.execute('CREATE TABLE IF NOT EXISTS commands (id TEXT PRIMARY KEY, name TEXT NOT NULL, command TEXT NOT NULL, cwd TEXT NOT NULL, fingerprint TEXT NOT NULL)')
        self.path.chmod(0o600)
        if first_run and (self.bin_dir/'kitty').is_file():
            for name in ('fastfetch','btop','htop','nvtop'):
                if (self.bin_dir/name).is_file():
                    try:self.add(name,name,'')
                    except ValueError:pass

    def db(self):
        return sqlite3.connect(self.path,timeout=5)

    def _rows(self):
        with self.db() as db:
            db.row_factory=sqlite3.Row
            return [dict(row) for row in db.execute('SELECT * FROM commands ORDER BY name LIMIT 50')]

    def view(self):
        with self.db() as db:ask=bool(db.execute('SELECT ask FROM policy WHERE id=1').fetchone()[0])
        return {'ask_before_launch':ask,'scope':'Installed applications and exact saved terminal commands only'}

    def configure(self,ask):
        if type(ask) is not bool:raise ValueError('The approval setting must be a boolean')
        with self.lock,self.db() as db:db.execute('UPDATE policy SET ask=? WHERE id=1',(int(ask),))
        return self.view()

    def auto_allowed(self,kind):
        return kind in ('launch','terminal') and not self.view()['ask_before_launch']

    def _directory(self,cwd):
        parts=self.files._parts(cwd)
        with self.files._directory(parts):pass
        return str(self.home.joinpath(*parts))

    def _prepare(self,command,cwd):
        if not isinstance(command,str) or not 1<=len(command)<=512 or any(ord(c)<32 or c in ';&|<>`$' for c in command):
            raise ValueError('Use one command with quoted arguments; shell operators, variables and scripts via a shell are unavailable')
        if redact(command)!=command:raise ValueError('Do not save passwords or access tokens in terminal commands')
        try:argv=shlex.split(command)
        except ValueError:raise ValueError('The command contains unmatched quotes') from None
        if not argv or len(argv)>48:raise ValueError('Use one command with at most 47 arguments')
        name=argv[0]
        if '/' in name:
            if Path(name).parent!=self.bin_dir:raise ValueError('Select an installed program from /usr/bin')
            name=Path(name).name
        if name in _BLOCKED:raise ValueError('Privilege escalation, shell wrappers and service operations are unavailable here')
        program=self.bin_dir/name
        try:
            resolved=program.resolve(strict=True)
            info=resolved.stat()
            if not resolved.is_relative_to(self.bin_dir.resolve()) or resolved.name in _BLOCKED or not stat.S_ISREG(info.st_mode) or info.st_mode&(stat.S_ISUID|stat.S_ISGID) or not os.access(resolved,os.X_OK):raise OSError()
            kitty=self.bin_dir/'kitty'
            kitty_info=kitty.stat()
            if not stat.S_ISREG(kitty_info.st_mode) or not os.access(kitty,os.X_OK):raise OSError()
        except OSError:raise ValueError('The selected program or Kitty is unavailable; install it locally first') from None
        directory=self._directory(cwd)
        identity=lambda value:(value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns)
        fingerprint=hashlib.sha256(json.dumps([str(resolved),identity(info),identity(kitty_info),argv[1:],directory]).encode()).hexdigest()
        return [str(kitty),'--detach','--session','none','--hold','--directory',directory,'--',str(resolved),*argv[1:]],fingerprint

    def add(self,name,command,cwd):
        if not isinstance(name,str) or not 1<=len(name.strip())<=60 or any(ord(c)<32 for c in name):raise ValueError('Use a command name of 1 to 60 characters')
        _,fingerprint=self._prepare(command,cwd)
        identifier='cmd-'+secrets.token_hex(12)
        with self.lock,self.db() as db:
            existing=db.execute('SELECT id FROM commands WHERE fingerprint=?',(fingerprint,)).fetchone()
            if existing:return self.entry(existing[0])
            if db.execute('SELECT COUNT(*) FROM commands').fetchone()[0]>=50:raise ValueError('Remove a command before adding more than 50')
            db.execute('INSERT OR IGNORE INTO commands VALUES (?,?,?,?,?)',(identifier,name.strip(),command,cwd,fingerprint))
        return self.entry(identifier)

    def entry(self,identifier):
        row=next((row for row in self._rows() if row['id']==identifier),None)
        if not row:raise ValueError('Saved command was removed or is unknown. Choose a current command in Settings.')
        _,fingerprint=self._prepare(row['command'],row['cwd'])
        if fingerprint!=row['fingerprint']:raise ValueError('The program changed since this command was saved. Remove and save it again in Settings.')
        return {k:row[k] for k in ('id','name','command','cwd')}

    def catalog(self):
        rows=[]
        for item in self._rows():
            try:rows.append({**self.entry(item['id']),'available':True})
            except ValueError as exc:rows.append({**{k:item[k] for k in ('id','name','command','cwd')},'available':False,'error':str(exc)})
        return {'commands':rows,'ask_before_launch':self.view()['ask_before_launch'],'terminal':'Kitty'}

    def command(self,identifier):
        row=self.entry(identifier)
        return self._prepare(row['command'],row['cwd'])[0]

    def effect(self,identifier):
        row=self.entry(identifier)
        return f"Open Kitty and run exactly: {row['command']} (working directory: Home{('/'+row['cwd']) if row['cwd'] else ''}). Kitty stays open after the command exits"

    def remove(self,identifier):
        with self.lock,self.db() as db:db.execute('DELETE FROM commands WHERE id=?',(identifier,))
        return {'status':'removed'}

    def request(self,approvals,kind,target,allow_auto=True,validate_turn=None):
        with self.lock:
            if validate_turn:validate_turn()
            effect=self.effect(target) if kind=='terminal' else approvals.policy.application_catalog.effect(target)
            action=approvals.propose(kind,target,effect)
            if allow_auto and self.auto_allowed(kind):
                outcome=approvals.resolve(action['id'],True,authorization='desktop_setting')
                # This authority comes only from the authenticated browser setting.
                return {**action,**outcome,'authorization':'desktop_setting'}
            return action
