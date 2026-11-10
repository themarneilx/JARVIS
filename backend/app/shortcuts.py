"""Persisted local schedules and one-use delivery claims; no agent execution."""
from datetime import date, datetime, time as clock_time, timedelta
import hashlib
import hmac
import json
import math
from pathlib import Path
import secrets
import sqlite3
import string
import time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator


class ShortcutSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)
    trigger: Literal['manual', 'once', 'daily', 'battery']
    time: str = Field(default='', pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$|^$')
    date: str = Field(default='', max_length=10)
    timezone: str = Field(default='', max_length=80)
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)), max_length=7)
    threshold: int = Field(default=10, ge=1, le=50, strict=True)
    message: str = Field(default='Sir, it is {time}. Your alarm is due.', max_length=500)
    weather: StrictBool = False
    chime: StrictBool = True
    delivery: Literal['auto', 'browser', 'desktop'] = 'auto'

    @field_validator('name')
    @classmethod
    def name_text(cls, value):
        value = ' '.join(value.split())
        if not value: raise ValueError('Give the shortcut a name')
        return value

    @field_validator('timezone')
    @classmethod
    def timezone_name(cls, value):
        if value:
            try: ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError): raise ValueError('Choose a valid IANA timezone')
        return value

    @field_validator('date')
    @classmethod
    def date_text(cls, value):
        if value:
            try: date.fromisoformat(value)
            except ValueError: raise ValueError('Use a date in YYYY-MM-DD format')
        return value

    @field_validator('weekdays', mode='before')
    @classmethod
    def weekday_list(cls, value):
        if not isinstance(value, list) or any(type(day) is not int or day not in range(7) for day in value):
            raise ValueError('Choose weekdays from Monday (0) through Sunday (6)')
        return sorted(set(value))

    @field_validator('message')
    @classmethod
    def message_template(cls, value):
        if any(ord(char) < 32 and char not in '\n\t' for char in value): raise ValueError('Announcement contains unsupported control characters')
        try:
            for _, field, format_spec, conversion in string.Formatter().parse(value):
                if field is not None and (field not in {'time', 'date', 'location', 'battery_percent'} or format_spec or conversion):
                    raise ValueError('Use only {time}, {date}, {location} and {battery_percent} placeholders')
        except ValueError as exc: raise ValueError('Invalid announcement template: '+str(exc))
        return value.strip()

    @model_validator(mode='after')
    def useful_trigger(self):
        if self.trigger in ('once', 'daily') and not self.time: raise ValueError('Choose an alarm time')
        if self.trigger == 'daily' and not self.weekdays: raise ValueError('Choose at least one day')
        if self.trigger != 'once' and self.date: raise ValueError('A specific date belongs to a one-time alarm')
        if self.trigger in ('manual', 'battery') and self.time: raise ValueError('This trigger does not use a clock time')
        if not (self.chime or self.message or self.weather): raise ValueError('Choose at least one shortcut action')
        return self


def local_timestamp(day, value, zone):
    naive = datetime.combine(day, clock_time.fromisoformat(value))
    aware = naive.replace(tzinfo=ZoneInfo(zone), fold=0)
    timestamp = aware.timestamp()
    if datetime.fromtimestamp(timestamp, ZoneInfo(zone)).replace(tzinfo=None) != naive:
        raise ValueError('That local time does not exist because of a daylight-saving change')
    return timestamp


def next_daily(spec, now):
    day = datetime.fromtimestamp(now, ZoneInfo(spec.timezone)).date()
    for offset in range(9):
        candidate = day + timedelta(days=offset)
        if candidate.weekday() not in spec.weekdays: continue
        try: timestamp = local_timestamp(candidate, spec.time, spec.timezone)
        except ValueError: continue
        if timestamp > now: return timestamp
    raise ValueError('Could not find the next selected day')


def normalize_spec(value, default_timezone='Asia/Manila', now=None):
    now = time.time() if now is None else now
    spec = value if isinstance(value, ShortcutSpec) else ShortcutSpec.model_validate(value)
    spec = spec.model_copy(update={'timezone': spec.timezone or default_timezone})
    ShortcutSpec.timezone_name(spec.timezone)
    next_run = None
    if spec.trigger == 'once':
        day = date.fromisoformat(spec.date) if spec.date else datetime.fromtimestamp(now, ZoneInfo(spec.timezone)).date()
        for offset in range(2 if not spec.date else 1):
            candidate = day + timedelta(days=offset)
            try: timestamp = local_timestamp(candidate, spec.time, spec.timezone)
            except ValueError:
                if spec.date: raise
                continue
            if timestamp > now:
                next_run = timestamp
                spec = spec.model_copy(update={'date': candidate.isoformat()})
                break
        if next_run is None: raise ValueError('The alarm time has passed. Choose a future date and time')
    elif spec.trigger == 'daily': next_run = next_daily(spec, now)
    return spec, next_run


def describe(spec):
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    when = {'manual': 'When run manually', 'battery': f'When battery is at or below {spec.threshold}% while discharging',
            'once': f'At {spec.time} on {spec.date} ({spec.timezone})',
            'daily': f"At {spec.time}, {', '.join(days[day] for day in spec.weekdays)} ({spec.timezone})"}[spec.trigger]
    actions = []
    if spec.chime: actions.append('play a chime')
    if spec.message: actions.append('say: '+spec.message)
    if spec.weather: actions.append('read current weather for the saved city')
    destination = {'auto': 'browser when available, otherwise desktop speakers', 'browser': 'open browser', 'desktop': 'desktop speakers'}[spec.delivery]
    return when+'; '+ '; '.join(actions)+'. Output: '+destination+'.'


class Shortcuts:
    def __init__(self, path, timezone=lambda: 'Asia/Manila'):
        self.path = Path(path)
        self.timezone = timezone
        if self.path.is_symlink(): raise ValueError('Shortcut state cannot be a symlink')
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS shortcuts (
              id TEXT PRIMARY KEY, revision INTEGER NOT NULL, spec TEXT NOT NULL,
              enabled INTEGER NOT NULL, created REAL, updated REAL, next_run REAL,
              last_run REAL, last_error TEXT DEFAULT '', battery_armed INTEGER DEFAULT 1,
              battery_cycle INTEGER DEFAULT 0, battery_since REAL);
            CREATE TABLE IF NOT EXISTS shortcut_proposals (
              id TEXT PRIMARY KEY, spec TEXT NOT NULL, digest TEXT NOT NULL,
              status TEXT NOT NULL, created REAL, expires REAL, shortcut_id TEXT);
            CREATE TABLE IF NOT EXISTS shortcut_events (
              id TEXT PRIMARY KEY, shortcut_id TEXT NOT NULL, revision INTEGER NOT NULL,
              occurrence TEXT NOT NULL, name TEXT, payload TEXT NOT NULL,
              status TEXT NOT NULL, due REAL, created REAL, delivery TEXT,
              text TEXT DEFAULT '', sources TEXT DEFAULT '[]', error TEXT DEFAULT '',
              owner TEXT, claim_id TEXT, claim_until REAL, manual INTEGER DEFAULT 0,
              UNIQUE(shortcut_id, revision, occurrence));
            CREATE TABLE IF NOT EXISTS shortcut_settings (id INTEGER PRIMARY KEY, payload TEXT);
            INSERT OR IGNORE INTO shortcut_settings VALUES (1,'{"voice_enabled":true}');
            ''')
        self.path.chmod(0o600)

    def db(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _view(row):
        if row is None: raise ValueError('Shortcut does not exist')
        value = dict(row)
        spec = ShortcutSpec.model_validate_json(value.pop('spec'))
        return {key: value[key] for key in ('id', 'revision', 'next_run', 'last_run', 'last_error')} | {
            'enabled': bool(value['enabled']), 'spec': spec.model_dump(), 'summary': describe(spec)}

    @staticmethod
    def _event_view(row):
        if row is None: raise ValueError('Shortcut event does not exist')
        return {key: row[key] for key in ('id', 'shortcut_id', 'revision', 'name', 'status', 'due', 'created', 'delivery', 'text', 'error')} | {
            'payload': json.loads(row['payload']), 'sources': json.loads(row['sources'])}

    def list(self):
        with self.db() as db: return [self._view(row) for row in db.execute('SELECT * FROM shortcuts ORDER BY created DESC')]

    def get(self, identifier):
        with self.db() as db: return self._view(db.execute('SELECT * FROM shortcuts WHERE id=?', (identifier,)).fetchone())

    def settings(self, payload=None):
        with self.db() as db:
            if payload is not None:
                if set(payload) != {'voice_enabled'} or type(payload['voice_enabled']) is not bool: raise ValueError('Invalid shortcut speech setting')
                db.execute('UPDATE shortcut_settings SET payload=? WHERE id=1', (json.dumps(payload),))
            return json.loads(db.execute('SELECT payload FROM shortcut_settings WHERE id=1').fetchone()[0])

    def _insert(self, db, spec, next_run, now):
        if db.execute('SELECT count(*) FROM shortcuts').fetchone()[0] >= 100: raise ValueError('Limit of 100 shortcuts reached')
        identifier = 'sc-'+secrets.token_hex(12)
        db.execute('INSERT INTO shortcuts(id,revision,spec,enabled,created,updated,next_run) VALUES (?,1,?,1,?,?,?)', (identifier, spec.model_dump_json(), now, now, next_run))
        return self._view(db.execute('SELECT * FROM shortcuts WHERE id=?', (identifier,)).fetchone())

    def create(self, value, now=None):
        now = time.time() if now is None else now
        spec, next_run = normalize_spec(value, self.timezone(), now)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            return self._insert(db, spec, next_run, now)

    def update(self, identifier, revision, value, now=None):
        now = time.time() if now is None else now
        spec, next_run = normalize_spec(value, self.timezone(), now)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM shortcuts WHERE id=?', (identifier,)).fetchone()
            if not row or row['revision'] != revision: raise ValueError('Shortcut changed; refresh before editing')
            self._cancel_events(db, identifier)
            db.execute('UPDATE shortcuts SET spec=?,revision=revision+1,updated=?,next_run=?,last_error=?,battery_armed=1,battery_since=NULL WHERE id=?', (spec.model_dump_json(), now, next_run, '', identifier))
            return self._view(db.execute('SELECT * FROM shortcuts WHERE id=?', (identifier,)).fetchone())

    @staticmethod
    def _cancel_events(db, identifier):
        db.execute("UPDATE shortcut_events SET status='cancelled',error='Shortcut disabled, changed or removed' WHERE shortcut_id=? AND status IN ('pending','preparing','playing')", (identifier,))

    def set_enabled(self, identifier, revision, enabled, now=None):
        now = time.time() if now is None else now
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM shortcuts WHERE id=?', (identifier,)).fetchone()
            if not row or row['revision'] != revision: raise ValueError('Shortcut changed; refresh before updating')
            spec = ShortcutSpec.model_validate_json(row['spec'])
            next_run = normalize_spec(spec, self.timezone(), now)[1] if enabled else row['next_run']
            self._cancel_events(db, identifier)
            db.execute('UPDATE shortcuts SET enabled=?,revision=revision+1,updated=?,next_run=?,battery_armed=1,battery_since=NULL WHERE id=?', (int(enabled), now, next_run, identifier))
            return self._view(db.execute('SELECT * FROM shortcuts WHERE id=?', (identifier,)).fetchone())

    def delete(self, identifier, revision):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision FROM shortcuts WHERE id=?', (identifier,)).fetchone()
            if not row or row['revision'] != revision: raise ValueError('Shortcut changed; refresh before removing')
            self._cancel_events(db, identifier)
            db.execute('DELETE FROM shortcuts WHERE id=?', (identifier,))

    def propose(self, value, now=None):
        now = time.time() if now is None else now
        spec, _ = normalize_spec(value, self.timezone(), now)
        digest = hashlib.sha256(spec.model_dump_json().encode()).hexdigest()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE shortcut_proposals SET status='expired' WHERE status='pending' AND expires<=?", (now,))
            row = db.execute("SELECT * FROM shortcut_proposals WHERE digest=? AND status='pending' AND expires>?", (digest, now)).fetchone()
            if row is None:
                if db.execute("SELECT count(*) FROM shortcut_proposals WHERE status='pending'").fetchone()[0] >= 50: raise ValueError('Review pending shortcut requests first')
                identifier = 'sp-'+secrets.token_hex(12)
                db.execute('INSERT INTO shortcut_proposals VALUES (?,?,?,?,?,?,NULL)', (identifier, spec.model_dump_json(), digest, 'pending', now, now+600))
                row = db.execute('SELECT * FROM shortcut_proposals WHERE id=?', (identifier,)).fetchone()
            return {'source': 'jarvis_shortcuts/v1', 'status': 'pending', 'id': row['id'], 'spec': spec.model_dump(), 'summary': describe(spec)}

    def pending(self):
        with self.db() as db:
            db.execute("UPDATE shortcut_proposals SET status='expired' WHERE status='pending' AND expires<=?", (time.time(),))
            return [{'id': row['id'], 'spec': json.loads(row['spec']), 'summary': describe(ShortcutSpec.model_validate_json(row['spec'])), 'expires': row['expires']} for row in db.execute("SELECT * FROM shortcut_proposals WHERE status='pending' ORDER BY created")]

    def inventory(self):
        pending = self.pending()
        with self.db() as db:
            states = {row['id']: {'status': 'approved', 'shortcut_id': row['shortcut_id']} if row['status'] == 'approved' else row['status'] for row in db.execute('SELECT * FROM shortcut_proposals ORDER BY created DESC LIMIT 200')}
        return {'shortcuts': self.list(), 'pending': pending, 'proposal_states': states}

    def resolve(self, identifier, approve):
        now = time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM shortcut_proposals WHERE id=?', (identifier,)).fetchone()
            if not row or row['status'] != 'pending' or row['expires'] <= now: raise ValueError('Shortcut proposal expired or was already resolved')
            if not approve:
                db.execute("UPDATE shortcut_proposals SET status='rejected' WHERE id=?", (identifier,))
                return {'status': 'rejected', 'source': 'shortcut', 'id': identifier}
            spec, next_run = normalize_spec(json.loads(row['spec']), self.timezone(), now)
            shortcut = self._insert(db, spec, next_run, now)
            db.execute("UPDATE shortcut_proposals SET status='approved',shortcut_id=? WHERE id=?", (shortcut['id'], identifier))
            return {'status': 'approved', 'source': 'shortcut', 'id': identifier, 'shortcut_id': shortcut['id'], 'summary': shortcut['summary'], 'name': spec.name}

    def _enqueue(self, db, row, occurrence, due, snapshot, now, manual=False):
        spec = ShortcutSpec.model_validate_json(row['spec'])
        identifier = 'se-'+secrets.token_hex(12)
        status = 'missed' if now-due > 300 else 'pending'
        db.execute('INSERT OR IGNORE INTO shortcut_events(id,shortcut_id,revision,occurrence,name,payload,status,due,created,delivery,manual,error) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', (
            identifier, row['id'], row['revision'], occurrence, spec.name,
            json.dumps({'spec': spec.model_dump(), 'snapshot': snapshot}), status, due, now, spec.delivery, int(manual),
            'Alarm was missed while Jarvis was not available' if status == 'missed' else ''))
        db.execute('UPDATE shortcuts SET last_run=? WHERE id=?', (now, row['id']))
        return db.execute('SELECT * FROM shortcut_events WHERE shortcut_id=? AND revision=? AND occurrence=?', (row['id'], row['revision'], occurrence)).fetchone()

    @staticmethod
    def _disarm_once(db, event):
        if event is None or event['manual']:
            return
        spec = ShortcutSpec.model_validate(json.loads(event['payload'])['spec'])
        if spec.trigger == 'once':
            db.execute('UPDATE shortcuts SET enabled=0 WHERE id=? AND revision=?', (event['shortcut_id'], event['revision']))

    def run(self, identifier, now=None):
        now = time.time() if now is None else now
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM shortcuts WHERE id=?', (identifier,)).fetchone()
            if row is None: raise ValueError('Shortcut does not exist')
            if db.execute("SELECT count(*) FROM shortcut_events WHERE status IN ('pending','preparing','playing')").fetchone()[0] >= 30: raise ValueError('Shortcut notification queue is full')
            return self._event_view(self._enqueue(db, row, secrets.token_hex(12), now, {}, now, manual=True))

    def tick(self, snapshot=None, now=None):
        now = time.time() if now is None else now
        battery = (snapshot or {}).get('battery') or {}
        percent, charging = battery.get('percent'), battery.get('charging')
        measured = type(percent) in (int, float) and math.isfinite(percent) and 0 <= percent <= 100
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            expired = db.execute("SELECT * FROM shortcut_events WHERE status='pending' AND due<?", (now-300,)).fetchall()
            for event in expired:
                db.execute("UPDATE shortcut_events SET status='missed',error='No audio delivery was available within five minutes' WHERE id=?", (event['id'],))
                self._disarm_once(db, event)
            interrupted = db.execute("SELECT * FROM shortcut_events WHERE status IN ('preparing','playing') AND claim_until<?", (now,)).fetchall()
            for event in interrupted:
                db.execute("UPDATE shortcut_events SET status='failed',error='Audio delivery was interrupted; replay manually if needed' WHERE id=?", (event['id'],))
                self._disarm_once(db, event)
            for row in db.execute('SELECT * FROM shortcuts WHERE enabled=1').fetchall():
                spec = ShortcutSpec.model_validate_json(row['spec'])
                if spec.trigger in ('once', 'daily') and row['next_run'] is not None and row['next_run'] <= now:
                    event = self._enqueue(db, row, 'time:'+str(int(row['next_run'])), row['next_run'], {}, now)
                    if event['status'] == 'missed':
                        self._disarm_once(db, event)
                    next_run = next_daily(spec, now) if spec.trigger == 'daily' else None
                    db.execute('UPDATE shortcuts SET next_run=? WHERE id=?', (next_run, row['id']))
                elif spec.trigger == 'battery':
                    if snapshot is None: continue
                    if charging is True or (measured and percent >= spec.threshold+5):
                        if not row['battery_armed']:
                            db.execute('UPDATE shortcuts SET battery_armed=1,battery_cycle=battery_cycle+1,battery_since=NULL WHERE id=?', (row['id'],))
                        else: db.execute('UPDATE shortcuts SET battery_since=NULL WHERE id=?', (row['id'],))
                    elif measured and charging is False and percent <= spec.threshold and row['battery_armed']:
                        since = row['battery_since']
                        if since is None: db.execute('UPDATE shortcuts SET battery_since=? WHERE id=?', (now, row['id']))
                        elif now-since >= 10:
                            self._enqueue(db, row, 'battery:'+str(row['battery_cycle']), now, {'battery_percent': percent}, now)
                            db.execute('UPDATE shortcuts SET battery_armed=0,battery_since=NULL WHERE id=?', (row['id'],))
                    else: db.execute('UPDATE shortcuts SET battery_since=NULL WHERE id=?', (row['id'],))
            db.execute("DELETE FROM shortcut_events WHERE status NOT IN ('pending','preparing','playing') AND id NOT IN (SELECT id FROM shortcut_events ORDER BY created DESC LIMIT 200)")
            db.execute("DELETE FROM shortcut_proposals WHERE status!='pending' AND id NOT IN (SELECT id FROM shortcut_proposals ORDER BY created DESC LIMIT 200)")

    def events(self):
        with self.db() as db: return [self._event_view(row) for row in db.execute("SELECT * FROM shortcut_events ORDER BY CASE WHEN status IN ('pending','preparing','playing') THEN 0 ELSE 1 END,created DESC LIMIT 200")]

    def event(self, identifier):
        with self.db() as db: return self._event_view(db.execute('SELECT * FROM shortcut_events WHERE id=?', (identifier,)).fetchone())

    def owner_events(self, owner):
        with self.db() as db: return [row['id'] for row in db.execute("SELECT id FROM shortcut_events WHERE owner=? AND status IN ('preparing','playing')", (owner,))]

    @staticmethod
    def _current(db, event):
        if event is None or event['status'] not in ('pending', 'preparing', 'playing'): return False
        shortcut = db.execute('SELECT enabled,revision FROM shortcuts WHERE id=?', (event['shortcut_id'],)).fetchone()
        return bool(shortcut and shortcut['revision'] == event['revision'] and (shortcut['enabled'] or event['manual']))

    def valid_event(self, identifier):
        with self.db() as db: return self._current(db, db.execute('SELECT * FROM shortcut_events WHERE id=?', (identifier,)).fetchone())

    def claim(self, identifier, owner):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM shortcut_events WHERE id=?', (identifier,)).fetchone()
            if not self._current(db, row) or row['status'] != 'pending': raise ValueError('Shortcut event is no longer available')
            if time.time()-row['due'] > 300: raise ValueError('Shortcut event expired')
            if db.execute("SELECT 1 FROM shortcut_events WHERE id!=? AND status IN ('preparing','playing') AND claim_until>? LIMIT 1", (identifier, time.time())).fetchone():
                raise ValueError('Another shortcut announcement is already in progress')
            claim_id = secrets.token_urlsafe(24)
            db.execute("UPDATE shortcut_events SET status='preparing',owner=?,claim_id=?,claim_until=? WHERE id=?", (owner, claim_id, time.time()+300, identifier))
            return {'claim_id': claim_id, 'event': self._event_view(db.execute('SELECT * FROM shortcut_events WHERE id=?', (identifier,)).fetchone())}

    def _claimed(self, db, identifier, owner, claim_id):
        row = db.execute('SELECT * FROM shortcut_events WHERE id=?', (identifier,)).fetchone()
        if not self._current(db, row) or row['owner'] != owner or row['claim_until'] is None or row['claim_until'] <= time.time() or not hmac.compare_digest(row['claim_id'] or '', claim_id):
            raise ValueError('Shortcut audio claim expired, changed or belongs to another browser')
        return row

    def validate_claim(self, identifier, owner, claim_id):
        with self.db() as db: return self._event_view(self._claimed(db, identifier, owner, claim_id))

    def mark_preparing(self, identifier, owner, claim_id):
        return self.validate_claim(identifier, owner, claim_id)

    def mark_playing(self, identifier, owner, claim_id):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self._claimed(db, identifier, owner, claim_id)
            db.execute("UPDATE shortcut_events SET status='playing',claim_until=? WHERE id=?", (time.time()+300, identifier))

    def annotate(self, identifier, text, sources, error=''):
        with self.db() as db:
            row = db.execute('SELECT * FROM shortcut_events WHERE id=?', (identifier,)).fetchone()
            if not self._current(db, row): raise ValueError('Shortcut event was cancelled or changed')
            db.execute('UPDATE shortcut_events SET text=?,sources=?,error=? WHERE id=?', (str(text)[:1500], json.dumps(sources[:4]), str(error)[:500], identifier))

    def finish(self, identifier, owner, claim_id, status, error=''):
        if status not in ('delivered', 'failed', 'muted'): raise ValueError('Invalid delivery result')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._claimed(db, identifier, owner, claim_id)
            db.execute('UPDATE shortcut_events SET status=?,error=CASE WHEN ?!=\'\' THEN ? ELSE error END WHERE id=?', (status, str(error)[:500], str(error)[:500], identifier))
            spec = ShortcutSpec.model_validate(json.loads(row['payload'])['spec'])
            if status in ('delivered', 'muted', 'failed', 'cancelled') and spec.trigger == 'once' and not row['manual']:
                db.execute('UPDATE shortcuts SET enabled=0 WHERE id=? AND revision=?', (row['shortcut_id'], row['revision']))
            if status == 'failed': db.execute('UPDATE shortcuts SET last_error=? WHERE id=?', (str(error)[:500], row['shortcut_id']))
        return self.event(identifier)

    def stop(self, identifier):
        with self.db() as db:
            event = db.execute('SELECT * FROM shortcut_events WHERE id=?', (identifier,)).fetchone()
            db.execute("UPDATE shortcut_events SET status='cancelled',error='Stopped by the user' WHERE id=? AND status IN ('pending','preparing','playing')", (identifier,))
            self._disarm_once(db, event)
        return self.event(identifier)
