import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import time

_SECRET_KEY=r'(?:passwords?|passwd|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|auth[_ -]?token|authorization|bearer|private[_ -]?key|secrets?)'
SENSITIVE = re.compile(r'''(?i)["']?'''+_SECRET_KEY+r'''["']?\s*[:=]\s*(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|Bearer\s+[^\s,;}\]]+|[^\s,;}\]]+)|\bBearer\s+[a-zA-Z0-9._~+/=-]{20,}|\b(?:sk-[a-zA-Z0-9_-]{12,}|gh[pousr]_[a-zA-Z0-9_]{15,})|-----BEGIN .*PRIVATE KEY-----''')
SECRET_FIELD=re.compile(_SECRET_KEY+r'|(?:^|[_-])token(?:$|[_-])',re.I)


def redact(text):
    try:value=json.loads(text)
    except (ValueError,TypeError,RecursionError):value=None
    if isinstance(value,(dict,list)):
        changed=False
        def scrub(node,depth=0):
            nonlocal changed
            if depth>32:
                changed=True;return '[redacted nested data]'
            if isinstance(node,dict):
                result={}
                for key,item in node.items():
                    if SECRET_FIELD.search(key):changed=True;result[key]='[redacted credential]'
                    else:result[key]=scrub(item,depth+1)
                return result
            if isinstance(node,list):return [scrub(item,depth+1) for item in node]
            if isinstance(node,str):
                result=SENSITIVE.sub('[redacted credential]',node)
                changed|=result!=node
                return result
            return node
        filtered=scrub(value)
        if changed:return json.dumps(filtered,ensure_ascii=False,indent=2)
    return SENSITIVE.sub('[redacted credential]',text)


def fingerprint(text):
    return hashlib.sha256(' '.join(text.casefold().split()).encode()).hexdigest()


class MemoryManager:
    def __init__(self, settings, bridge=None):
        self.settings=settings
        self.path=settings.state_dir / 'memory-review.db'
        self.bridge_override=bridge
        self.lock=asyncio.Lock()
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS metadata (hash TEXT PRIMARY KEY, reason TEXT, pinned INTEGER DEFAULT 0, deleted INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, payload TEXT, created REAL, status TEXT);
            CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, action TEXT, hash TEXT, at REAL);
            CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT);
            INSERT OR IGNORE INTO preferences VALUES ('suggestions','true');
            INSERT OR IGNORE INTO preferences VALUES ('epoch','0');''')

    def db(self):
        return sqlite3.connect(self.path,timeout=5)

    @property
    def epoch(self):
        with self.db() as db:
            return int(db.execute("SELECT value FROM preferences WHERE key='epoch'").fetchone()[0])

    def suggestions(self, enabled=None):
        with self.db() as db:
            if enabled is not None:
                db.execute("UPDATE preferences SET value=? WHERE key='suggestions'",('true' if enabled else 'false',))
            return db.execute("SELECT value FROM preferences WHERE key='suggestions'").fetchone()[0] == 'true'

    async def bridge(self, payload):
        if self.bridge_override:
            return await self.bridge_override(payload)
        if not self.settings.hermes_python or not self.settings.hermes_source:
            raise ValueError('Native Hermes memory is not connected. Set HERMES_PYTHON and HERMES_SOURCE; no duplicate memory store was created.')
        env=dict(os.environ,HERMES_HOME=str(self.settings.hermes_home),PYTHONPATH=self.settings.hermes_source,HF_HUB_OFFLINE='1',DO_NOT_TRACK='1')
        proc=await asyncio.create_subprocess_exec(self.settings.hermes_python,str(Path(__file__).with_name('memory_worker.py')),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,env=env)
        try:
            output,_=await asyncio.wait_for(proc.communicate(json.dumps(payload).encode()),30)
        except (asyncio.TimeoutError,asyncio.CancelledError):
            proc.kill(); await proc.wait()
            raise
        if proc.returncode:
            raise ValueError('Hermes memory bridge failed or its installed contract changed; original memory files were preserved.')
        try: result=json.loads(output)
        except ValueError as exc: raise ValueError('Unsupported Hermes memory bridge response') from exc
        if result.get('error') and not result.get('success'):
            raise ValueError(redact(result['error'])[:400])
        return result

    async def inventory(self):
        native=await self.bridge({'action':'read'})
        with self.db() as db:
            entries=[]
            for target in ('user','memory'):
                for text in native.get(target,[]):
                    h=fingerprint(text)
                    meta=db.execute('SELECT reason,pinned,deleted FROM metadata WHERE hash=?',(h,)).fetchone()
                    entries.append({'id':h,'target':target,'text':text,'reason':meta[0] if meta else 'Existing Hermes memory; original rationale was not recorded','pinned':bool(meta and meta[1]),'previously_deleted':bool(meta and meta[2])})
            pending=[{'id':r[0],**json.loads(r[1]),'created':r[2]} for r in db.execute("SELECT id,payload,created FROM proposals WHERE status='pending' ORDER BY created")]
            history=[{'action':r[0],'fingerprint':r[1],'at':r[2]} for r in db.execute('SELECT action,hash,at FROM history ORDER BY id DESC LIMIT 30')]
            states=dict(db.execute('SELECT id,status FROM proposals ORDER BY created DESC LIMIT 100'))
        return {'entries':entries,'pending':pending,'history':history,'proposal_states':states,'suggestions':self.suggestions(),'limits':native.get('limits',{}),'epoch':self.epoch}

    def pending(self):
        with self.db() as db:
            return [{'id':row[0], **json.loads(row[1]), 'created':row[2]} for row in db.execute("SELECT id,payload,created FROM proposals WHERE status='pending' ORDER BY created LIMIT 100")]

    async def propose(self, payload, automatic=False):
        payload={k:payload.get(k,'') for k in ('action','target','content','old_text','reason')}
        if payload['action'] not in ('add','patch','remove') or payload['target'] not in ('user','memory'):
            raise ValueError('Invalid memory action or target')
        if automatic and not self.suggestions():
            raise ValueError('Automatic memory suggestions are disabled')
        if not payload['reason'].strip() or len(payload['content'])>2200 or len(payload['old_text'])>2200 or len(payload['reason'])>300:
            raise ValueError('Provide a concise rationale and bounded memory content')
        if payload['action'] in ('add','patch') and (not payload['content'].strip() or SENSITIVE.search(payload['content']+' '+payload['reason'])):
            raise ValueError('Empty or credential-bearing memories are refused')
        inv=await self.inventory()
        if automatic and payload['action'] in ('patch','remove') and any(e['text']==payload['old_text'] and e['pinned'] for e in inv['entries']):
            raise ValueError('Pinned memories can only be changed explicitly by the user')
        if payload['action']=='add' and any(fingerprint(e['text'])==fingerprint(payload['content']) for e in inv['entries']):
            raise ValueError('That memory already exists')
        if payload['action'] in ('patch','remove') and not any(e['text']==payload['old_text'] and e['target']==payload['target'] for e in inv['entries']):
            raise ValueError('Select an exact current entry; stale edits are refused')
        encoded=json.dumps(payload,sort_keys=True)
        with self.db() as db:
            h=fingerprint(payload['content'])
            if automatic and db.execute('SELECT 1 FROM metadata WHERE hash=? AND deleted=1',(h,)).fetchone():
                raise ValueError('This suggestion matches a deleted memory; it will not be recreated')
            for identifier,pending_payload in db.execute("SELECT id,payload FROM proposals WHERE status='pending'"):
                pending=json.loads(pending_payload)
                if pending['action']==payload['action'] and pending['target']==payload['target'] and fingerprint(pending['content'])==fingerprint(payload['content']) and fingerprint(pending['old_text'])==fingerprint(payload['old_text']):
                    return {'id':identifier,**pending}
            identifier=secrets.token_urlsafe(20)
            db.execute('INSERT INTO proposals VALUES (?,?,?,?)',(identifier,encoded,time.time(),'pending'))
        return {'id':identifier,**payload}

    async def resolve(self, identifier, approve):
        async with self.lock:
            with self.db() as db:
                row=db.execute("SELECT payload FROM proposals WHERE id=? AND status='pending'",(identifier,)).fetchone()
                if not row: raise ValueError('Memory proposal unavailable or already resolved')
                payload=json.loads(row[0])
                if not approve:
                    db.execute("UPDATE proposals SET status='rejected',payload='{}' WHERE id=?",(identifier,))
                    return {'status':'rejected'}
                result=await self.bridge({**payload,'approved':True})
                if not result.get('success'):
                    raise ValueError('Hermes did not confirm this memory change')
                old=fingerprint(payload['old_text'])
                h=fingerprint(payload['content'])
                if payload['action'] in ('remove','patch'):
                    db.execute('INSERT INTO metadata(hash,reason,deleted) VALUES (?, ?,1) ON CONFLICT(hash) DO UPDATE SET deleted=1',(old,'Deleted by user'))
                    # Reject obsolete suggestions that could reconstruct the deleted entry.
                    db.execute("UPDATE proposals SET status='obsolete',payload='{}' WHERE status='pending' AND id<>?",(identifier,))
                if payload['action'] != 'remove':
                    db.execute('INSERT INTO metadata(hash,reason,deleted) VALUES (?,?,0) ON CONFLICT(hash) DO UPDATE SET reason=excluded.reason,deleted=0',(h,payload['reason']))
                db.execute('INSERT INTO history(action,hash,at) VALUES (?,?,?)',(payload['action'],old if payload['action']=='remove' else h,time.time()))
                db.execute("UPDATE proposals SET status='approved',payload='{}' WHERE id=?",(identifier,))
                db.execute("UPDATE preferences SET value=CAST(value AS INTEGER)+1 WHERE key='epoch'")
                return {'status':'approved','new_session_required':True,'action':payload['action'],'target':payload['target']}

    def pin(self, h, pinned):
        if not re.fullmatch('[a-f0-9]{64}',h): raise ValueError('Invalid memory identifier')
        with self.db() as db:
            db.execute('INSERT INTO metadata(hash,reason,pinned) VALUES (?,?,?) ON CONFLICT(hash) DO UPDATE SET pinned=excluded.pinned',(h,'Pinned by user',int(pinned)))
