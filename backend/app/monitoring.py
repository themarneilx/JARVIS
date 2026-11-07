import json
import secrets
import sqlite3
import time


class ThresholdMonitor:
    def __init__(self):
        self.states={}

    def check(self,key,value,*,high,low,sustain=30,cooldown=600,now=None):
        if value is None: return False
        now=time.monotonic() if now is None else now
        s=self.states.setdefault(key,{'since':None,'active':False,'last':float('-inf')})
        if value<=low:
            s['since']=None; s['active']=False
        elif value>=high:
            if s['since'] is None: s['since']=now
            if not s['active'] and now-s['since']>=sustain and now-s['last']>=cooldown:
                s.update(active=True,last=now)
                return True
        return False


class Monitoring:
    def __init__(self,path):
        self.path=path
        self.thresholds=ThresholdMonitor()
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, payload TEXT);
            INSERT OR IGNORE INTO settings VALUES (1,'{"enabled":false,"gpu_temperature":85,"cpu_percent":95,"ram_percent":92,"disk_percent":95,"battery_percent":15,"services":[]}');
            CREATE TABLE IF NOT EXISTS alerts (id TEXT PRIMARY KEY, at REAL, message TEXT, acknowledged INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS routines (id TEXT PRIMARY KEY, name TEXT, interval INTEGER, enabled INTEGER, next REAL);
            CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, routine_id TEXT, at REAL, payload TEXT);''')

    def db(self): return sqlite3.connect(self.path,timeout=5)

    def settings(self,payload=None):
        with self.db() as db:
            if payload is not None: db.execute('UPDATE settings SET payload=? WHERE id=1',(json.dumps(payload),))
            return json.loads(db.execute('SELECT payload FROM settings WHERE id=1').fetchone()[0])

    def view(self):
        with self.db() as db:
            db.row_factory=sqlite3.Row
            return {'settings':self.settings(),'alerts':[dict(r) for r in db.execute('SELECT * FROM alerts ORDER BY at DESC LIMIT 30')],'routines':[dict(r) for r in db.execute('SELECT * FROM routines')],'reports':[{**dict(r),'payload':json.loads(r['payload'])} for r in db.execute('SELECT * FROM reports ORDER BY at DESC LIMIT 10')]}

    def routine(self,name,interval):
        identifier=secrets.token_urlsafe(16)
        with self.db() as db:
            db.execute('INSERT INTO routines VALUES (?,?,?,?,?)',(identifier,name,interval,1,time.time()+interval))
        return {'id':identifier}

    def update_routine(self,identifier,enabled=None,delete=False):
        with self.db() as db:
            if delete: db.execute('DELETE FROM routines WHERE id=?',(identifier,))
            else: db.execute('UPDATE routines SET enabled=?,next=?+interval WHERE id=?',(int(enabled),time.time(),identifier))

    def evaluate(self,snapshot):
        config=self.settings()
        if not config['enabled']: return
        values={
            'CPU usage':(snapshot.get('cpu_percent'),config['cpu_percent'],10),
            'RAM usage':(snapshot['ram']['percent'],config['ram_percent'],5),
            'Disk usage':(snapshot['disk']['percent'],config['disk_percent'],3),
            'GPU temperature':((snapshot.get('gpu') or {}).get('temperature'),config['gpu_temperature'],7),
        }
        battery=snapshot.get('battery')
        if battery and not battery['charging']:
            values['Battery depletion']=(100-battery['percent'],100-config['battery_percent'],5)
        for unit in config['services']:
            match=next((s for s in snapshot.get('services') or [] if s['unit']==unit),None)
            if match: values[f'Service {unit} failed']=(100 if match['active']=='failed' else 0,50,25)
        with self.db() as db:
            for key,(value,threshold,margin) in values.items():
                if self.thresholds.check(key,value,high=threshold,low=threshold-margin):
                    message=f'{key}: {value:.1f}; configured threshold {threshold:.1f}'
                    db.execute('INSERT INTO alerts(id,at,message) VALUES (?,?,?)',(secrets.token_hex(12),time.time(),message))
            for identifier,name,interval,enabled,next_at in db.execute('SELECT * FROM routines WHERE enabled=1 AND next<=?',(time.time(),)).fetchall():
                summary={key:snapshot.get(key) for key in ('sampled_at','cpu_percent','ram','gpu','battery','disk','uptime_seconds','unavailable')}
                db.execute('INSERT INTO reports VALUES (?,?,?,?)',(secrets.token_hex(12),identifier,time.time(),json.dumps(summary)))
                db.execute('UPDATE routines SET next=? WHERE id=?',(time.time()+interval,identifier))
            db.execute('DELETE FROM alerts WHERE id NOT IN (SELECT id FROM alerts ORDER BY at DESC LIMIT 100)')
            db.execute('DELETE FROM reports WHERE id NOT IN (SELECT id FROM reports ORDER BY at DESC LIMIT 30)')
