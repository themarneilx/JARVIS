import asyncio
from contextlib import asynccontextmanager, suppress
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import time
import uuid
from typing import Literal
import anyio

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings, ROOT
from .permissions import ActionPolicy, ApprovalStore
from .telemetry import Telemetry
from .hermes import HermesClient, HermesError,online_kinds
from .memory import MemoryManager
from .audio import LocalSTT, JarvisTTS, validate_audio, speech_phrases
from .monitoring import Monitoring
from .reviews import ReviewTickets
from .streaming import with_heartbeat, ClosingStreamingResponse
from .models import ModelManager, ModelError
from .information import Information,Lookup,OnlineSettings
from .maps import Maps,MapSelection
from .home_files import HomeFiles
from .desktop_apps import DesktopApps
from .terminal import DesktopAccess
from .memory import redact
from .shortcuts import Shortcuts, ShortcutSpec
from .shortcut_delivery import ShortcutRunner
from .shortcut_api import shortcut_routes, validate_shortcut_actions


class StrictModel(BaseModel):
    model_config=ConfigDict(extra='forbid')

class Login(StrictModel):
    token: str = Field(max_length=200)

class Chat(StrictModel):
    text: str = Field(min_length=1,max_length=16000)
    session_id: str | None = None
    request_id: uuid.UUID = Field(default_factory=uuid.uuid4)

class Action(StrictModel):
    kind: str = Field(max_length=40)
    target: str = Field(max_length=120)
    effect: str = Field(default='Requested desktop operation',max_length=240)

class Resolve(StrictModel):
    approve: bool

class ReviewResolve(Resolve):
    code: str = Field(min_length=4,max_length=4,pattern=r'^\d{4}$')

class ModelChoice(StrictModel):
    model: str = Field(min_length=1,max_length=300)

class ApplicationChoice(StrictModel):
    application_id: str = Field(pattern=r'^app-[a-f0-9]{24}$')

class TerminalChoice(StrictModel):
    command_id: str = Field(pattern=r'^cmd-[a-f0-9]{24}$')

class TerminalRecipe(StrictModel):
    name: str = Field(min_length=1,max_length=60)
    command: str = Field(min_length=1,max_length=512)
    cwd: str = Field(default='',max_length=512)

class DesktopSettings(StrictModel):
    ask_before_launch: StrictBool

class NativeDesktopTurn(StrictModel):
    session_id: uuid.UUID
    turn_id: str = Field(min_length=1,max_length=200)
    prompt_hash: str = Field(pattern=r'^[a-f0-9]{64}$')

class HomeLookup(StrictModel):
    kind: Literal['list','search','read']
    path: str = Field(default='',max_length=1024)
    query: str = Field(default='',max_length=120)

class MemoryProposal(StrictModel):
    action: str
    target: str
    content: str = Field(default='',max_length=2200)
    old_text: str = Field(default='',max_length=2200)
    reason: str = Field(max_length=300,min_length=1)

class Toggle(StrictModel):
    enabled: bool

class Pin(StrictModel):
    pinned: bool

class Speech(StrictModel):
    text: str = Field(min_length=1,max_length=12000)
    request_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    phrase_index: int | None = Field(default=None,ge=0,le=128)

class SpeechCancel(StrictModel):
    request_id: uuid.UUID

class SpeechDevice(StrictModel):
    device: Literal['cpu','cuda']

class MonitorSettings(StrictModel):
    enabled: bool
    gpu_temperature: float = Field(default=85,ge=60,le=100)
    cpu_percent: float = Field(default=95,ge=50,le=100)
    ram_percent: float = Field(default=92,ge=50,le=99)
    disk_percent: float = Field(default=95,ge=60,le=99)
    battery_percent: float = Field(default=15,ge=5,le=40)
    services: list[str] = Field(default_factory=list,max_length=20)

class Routine(StrictModel):
    name: str = Field(min_length=1,max_length=80)
    interval: int = Field(ge=300,le=604800)

def token_matches(provided,expected):
    return hmac.compare_digest(provided.encode('utf-8'),expected.encode('utf-8'))


def create_app(settings=None, hermes=None, memory_bridge=None):
    settings=settings or Settings()
    agent=hermes or HermesClient(settings)
    models=ModelManager(settings)
    if models.selected_model and hasattr(agent,'set_model'):
        agent.set_model(models.selected_model)
    telemetry=Telemetry()
    memory=MemoryManager(settings,bridge=memory_bridge)
    if isinstance(agent,HermesClient):
        agent.memory_inventory=memory.inventory
    tts,stt=JarvisTTS(settings),LocalSTT(settings)
    information=Information(settings.state_dir)
    maps=Maps(information)
    home_files=HomeFiles(denied_paths=(settings.state_dir,settings.hermes_home))
    applications=DesktopApps()
    desktop_access=DesktopAccess(settings.state_dir/'desktop.db')
    policy=ActionPolicy(services=settings.services,application_catalog=applications,terminal_catalog=desktop_access)
    approvals=ApprovalStore(settings.state_dir/'approvals.db',policy)
    if isinstance(agent,HermesClient):agent.action_inventory=approvals.list
    reviews=ReviewTickets()
    monitoring=Monitoring(settings.state_dir/'monitoring.db')
    shortcuts=Shortcuts(settings.state_dir/'monitoring.db',timezone=lambda:information.config.timezone)
    shortcut_runner=ShortcutRunner(shortcuts,tts,information)
    if isinstance(agent,HermesClient):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        agent.shortcut_inventory=shortcuts.inventory
        agent.shortcut_context=lambda:{'timezone':information.config.timezone,
            'now':datetime.now(ZoneInfo(information.config.timezone)).isoformat(),
            'location_label':information.config.location.name if information.config.location else ''}
    sessions={}
    attempts=[]
    active={}
    chat_lock=asyncio.Lock()
    desktop_request_lock=asyncio.Lock()
    speech_task=None
    speech_id=None
    cancelled_speech={}
    transcriptions={}
    shortcut_runner.foreground_busy=lambda:chat_lock.locked() or bool(speech_task and not speech_task.done()) or bool(transcriptions)

    def shortcut_audio_busy():
        return shortcut_runner.desktop_active or any(row['status'] in ('preparing','playing') for row in shortcuts.events())

    async def request_desktop(kind,target,request):
        internal=request.url.path.startswith('/api/internal/')
        state=active.get(request.headers.get('x-jarvis-native-session','')) if internal else None
        if state and (not state.get('native_turn') or state.get('native_turn')!=request.headers.get('x-jarvis-native-turn')):state=None
        def validate_turn():
            if state and (state['cancel'].is_set() or state['closed'].is_set()):raise ValueError('The requesting conversation was cancelled or closed')
        async with desktop_request_lock:
            validate_turn()
            cache=state.setdefault('desktop_requests',{}) if state else {}
            key=(kind,target)
            if key not in cache:cache[key]=await asyncio.to_thread(desktop_access.request,approvals,kind,target,not internal or state is not None,validate_turn)
            return {**cache[key],'origin':'bound_web_turn' if state else 'unbound_internal' if internal else 'browser'}
    conversation_db=settings.state_dir/'conversations.db'
    with sqlite3.connect(conversation_db) as db:
        db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, epoch INTEGER, retired INTEGER DEFAULT 0)')
        db.execute('CREATE TABLE IF NOT EXISTS private_sessions (id TEXT PRIMARY KEY)')
        db.execute('CREATE TABLE IF NOT EXISTS desktop_native_turns (id TEXT PRIMARY KEY, created REAL)')

    def online_permission():
        if any(state.get('private_context') for state in active.values()):
            raise HTTPException(403,'Internet lookup is paused for this conversation because it contains home-file data. Start a new conversation before online searches.')

    def note_private_context():
        with sqlite3.connect(conversation_db) as db:
            for identifier,state in active.items():
                state['private_context']=True
                db.execute('INSERT OR IGNORE INTO private_sessions VALUES (?)',(identifier,))

    def retire(identifier):
        with sqlite3.connect(conversation_db) as db:
            db.execute('UPDATE sessions SET retired=1 WHERE id=?',(identifier,))

    async def monitor_loop():
        while True:
            await asyncio.sleep(10)
            tts.cleanup()
            if monitoring.settings()['enabled']:
                with suppress(Exception): monitoring.evaluate(await telemetry.sample())

    async def shortcut_loop():
        sampled_at=0
        while True:
            try:
                snapshot=None
                now=time.time()
                if now-sampled_at>=10 and any(row['enabled'] and row['spec']['trigger']=='battery' for row in shortcuts.list()):
                    sampled_at=now
                    try:snapshot=await telemetry.sample()
                    except Exception:snapshot={'battery':None}
                shortcuts.tick(snapshot,now)
                await shortcut_runner.tick()
                shortcuts.scheduler_error=''
            except Exception as exc:
                import logging
                shortcuts.scheduler_error='The scheduler could not complete its latest check. Review local logs before relying on an alarm.'
                logging.getLogger('jarvis.shortcuts').warning('Shortcut scheduling check failed: %s',type(exc).__name__)
            await asyncio.sleep(1)

    @asynccontextmanager
    async def lifespan(app):
        task=asyncio.create_task(monitor_loop())
        shortcut_task=asyncio.create_task(shortcut_loop())
        yield
        task.cancel()
        shortcut_task.cancel()
        with suppress(asyncio.CancelledError): await task
        with suppress(asyncio.CancelledError): await shortcut_task
        await shortcut_runner.close()
        await tts.close(cleanup=True)
        await stt.close()
        await agent.close()
        await models.close()
        await information.close()

    app=FastAPI(title='J.A.R.V.I.S. local command center',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    app.state.settings=settings
    app.state.shortcuts=shortcuts
    app.state.shortcut_runner=shortcut_runner
    app.include_router(shortcut_routes(shortcuts,shortcut_runner,information))
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=list(settings.allowed_hosts))

    @app.middleware('http')
    async def boundary(request,call_next):
        origin=request.headers.get('origin')
        if origin and origin not in settings.origins:
            return JSONResponse({'detail':'Origin not allowed'},403)
        if request.url.path.startswith('/api/'):
            if request.method not in ('GET','HEAD','OPTIONS'):
                if request.url.path.startswith('/api/internal/'):
                    token=request.headers.get('authorization','')
                    if not token_matches(token,'Bearer '+settings.plugin_token):
                        return JSONResponse({'detail':'Plugin authentication required'},401)
                elif request.url.path != '/api/auth/login':
                    session=sessions.get(hashlib.sha256(request.cookies.get('jarvis_session','').encode()).hexdigest())
                    if not session or session['expires']<time.time():
                        return JSONResponse({'detail':'Browser authentication required'},401)
                    if origin not in settings.origins or not token_matches(request.headers.get('x-csrf-token',''),session['csrf']):
                        return JSONResponse({'detail':'Valid origin and CSRF token required'},403)
                elif origin not in settings.origins:
                    return JSONResponse({'detail':'Login requires an allowed browser origin'},403)
                limit=12*1024*1024 if request.url.path=='/api/audio/transcribe' else 65536
                body=bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body)>limit: return JSONResponse({'detail':'Request exceeds size limit'},413)
                request._body=bytes(body)
            if request.url.path.startswith('/api/internal/'):
                if not token_matches(request.headers.get('authorization',''),'Bearer '+settings.plugin_token):
                    return JSONResponse({'detail':'Plugin authentication required'},401)
            elif request.url.path not in ('/api/auth/login','/api/health'):
                sid=hashlib.sha256(request.cookies.get('jarvis_session','').encode()).hexdigest()
                session=sessions.get(sid)
                if not session or session['expires']<time.time():
                    return JSONResponse({'detail':'Browser authentication required'},401)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        if settings.lan_mode:
            response.headers['Strict-Transport-Security']='max-age=86400'
        response.headers['Cache-Control']='no-store' if request.url.path.startswith('/api/') else 'no-cache'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://tile.openstreetmap.org; media-src 'self' blob:; connect-src 'self' https://tiles.openfreemap.org; worker-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        response.headers['Permissions-Policy']='camera=(), geolocation=(), microphone=(self)'
        return response

    @app.exception_handler(ValueError)
    async def validation_error(request,exc):
        return JSONResponse({'detail':str(exc)[:500]},400)

    @app.exception_handler(HermesError)
    async def agent_error(request,exc):
        return JSONResponse({'detail':str(exc)},503)

    @app.exception_handler(ModelError)
    async def model_error(request,exc):
        return JSONResponse({'detail':str(exc)},400)

    @app.get('/api/health')
    async def health(): return {'status':'ok','application':'J.A.R.V.I.S.'}

    @app.post('/api/auth/login')
    async def login(body:Login):
        now=time.time()
        attempts[:]=[t for t in attempts if now-t<60]
        if len(attempts)>=8: raise HTTPException(429,'Too many pairing attempts; wait one minute')
        attempts.append(now)
        if not token_matches(body.token,settings.login_token): raise HTTPException(401,'Invalid local pairing token')
        raw=secrets.token_urlsafe(40); csrf=secrets.token_urlsafe(32)
        sessions[hashlib.sha256(raw.encode()).hexdigest()]={'csrf':csrf,'expires':now+43200}
        response=JSONResponse({'csrf':csrf})
        response.set_cookie('jarvis_session',raw,httponly=True,samesite='strict',max_age=43200,secure=settings.secure_cookie,path='/')
        return response

    @app.get('/api/auth/session')
    async def session(request:Request):
        key=hashlib.sha256(request.cookies.get('jarvis_session','').encode()).hexdigest()
        return {'csrf':sessions[key]['csrf']}

    @app.post('/api/auth/logout')
    async def logout(request:Request):
        owner=hashlib.sha256(request.cookies.get('jarvis_session','').encode()).hexdigest()
        for event_id in shortcuts.owner_events(owner):await shortcut_runner.stop(event_id)
        shortcut_runner.forget_client(owner)
        for task,task_owner in tuple(transcriptions.items()):
            if task_owner==owner:
                task.cancel()
                with suppress(asyncio.CancelledError): await task
        for identifier,state in list(active.items()):
            retire(identifier)
            state['cancel'].set()
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(state['closed'].wait(),4)
        if speech_task and not speech_task.done():
            speech_task.cancel()
        reviews.forget(owner)
        sessions.pop(owner,None)
        response=JSONResponse({'ok':True}); response.delete_cookie('jarvis_session'); return response

    @app.get('/api/status')
    async def status():
        try: result=await agent.preflight()
        except HermesError as exc: result={'connected':False,'message':str(exc)}
        identity=settings.hermes_home/'SOUL.md'
        template=ROOT/'hermes/SOUL.md'
        audio={'tts_checkout':(settings.tts_repo/'audio.py').is_file(),'tts_voice':'JarvisLuxTTS',
               'stt_model':settings.stt_model,'stt_provider':settings.stt_provider,
               'stt_device':'cpu','stt_ready':stt.ready and stt.proc is not None and stt.proc.returncode is None,
               'device':tts.device,'tts_ready':tts.view()['ready']}
        return {'agent':result,'identity':{'installed':identity.is_file(),'matches_template':identity.is_file() and template.is_file() and identity.read_bytes()==template.read_bytes()},'audio':audio,'memory_epoch':memory.epoch,'approved_services':settings.services,'online':information.config.model_dump()}

    @app.get('/api/audio/startup')
    async def startup_audio():
        path=ROOT/'welcome_back_jarvis.mp3'
        if not path.is_file() or path.is_symlink():
            raise HTTPException(404,'Place welcome_back_jarvis.mp3 in the project folder to enable startup audio.')
        return FileResponse(path,media_type='audio/mpeg',headers={'Cache-Control':'private, max-age=3600'})

    @app.get('/api/audio/processing')
    async def processing_audio():
        path=settings.state_dir/'assets'/'processing-readout.wav'
        if not path.is_file() or path.is_symlink() or path.parent.is_symlink() or path.stat().st_size>2*1024*1024:
            raise HTTPException(404,'Processing sound clip is unavailable. See README for the local audio preparation command.')
        return FileResponse(path,media_type='audio/wav',headers={'Cache-Control':'private, no-cache'})

    @app.get('/api/information/settings')
    async def information_settings():return information.config.model_dump()

    @app.post('/api/information/settings')
    async def save_information_settings(body:OnlineSettings):return information.save(body)

    @app.get('/api/information/cities')
    async def cities(query:str):
        if len(query)>100:raise HTTPException(400,'City query is too long')
        return {'results':await information.cities(query)}

    @app.post('/api/information/lookup')
    @app.post('/api/internal/online/lookup')
    async def lookup_information(body:Lookup,request:Request):
        if request.url.path.startswith('/api/internal/') and body.kind not in ('time','location'):online_permission()
        return await maps.lookup(body) if body.kind in ('map','directions') else await information.lookup(body)

    @app.get('/api/information/views/{receipt}')
    async def information_view(receipt:str):return information.presentation(receipt)

    @app.get('/api/maps/{receipt}')
    async def map_view(receipt:str):return maps.get(receipt)

    @app.post('/api/maps/select')
    async def select_map(body:MapSelection):return await maps.select(body)

    @app.get('/api/internal/online/search-permit')
    async def search_permission():
        online_permission()
        return information.permission()

    @app.get('/api/applications')
    @app.get('/api/internal/applications')
    async def application_catalog(request:Request,query:str=''):
        return await asyncio.to_thread(applications.list,query,40 if request.url.path.startswith('/api/internal/') else 100)

    @app.post('/api/applications/propose')
    @app.post('/api/internal/applications/propose')
    async def propose_application(body:ApplicationChoice,request:Request):
        return await request_desktop('launch',body.application_id,request)

    @app.get('/api/desktop/settings')
    async def desktop_settings():return desktop_access.view()

    @app.post('/api/internal/desktop/bind-turn')
    async def bind_desktop_turn(body:NativeDesktopTurn):
        state=active.get(str(body.session_id))
        if state and state.get('native_turn')==body.turn_id:return {'bound':not state['cancel'].is_set() and not state['closed'].is_set()}
        digest=hashlib.sha256((str(body.session_id)+'\0'+body.turn_id).encode()).hexdigest()
        with sqlite3.connect(conversation_db) as db:
            db.execute('DELETE FROM desktop_native_turns WHERE created<?',(time.time()-86400,))
            fresh=db.execute('INSERT OR IGNORE INTO desktop_native_turns VALUES (?,?)',(digest,time.time())).rowcount==1
        if not fresh or not state or state['cancel'].is_set() or state['closed'].is_set() or state.get('native_turn') or not token_matches(body.prompt_hash,state['prompt_hash']):return {'bound':False}
        state['native_turn']=body.turn_id
        return {'bound':True}

    @app.post('/api/desktop/settings')
    async def save_desktop_settings(body:DesktopSettings):
        return await asyncio.to_thread(desktop_access.configure,body.ask_before_launch)

    @app.get('/api/terminal/commands')
    @app.get('/api/internal/terminal/commands')
    async def terminal_commands():return await asyncio.to_thread(desktop_access.catalog)

    @app.post('/api/terminal/commands')
    async def add_terminal_command(body:TerminalRecipe):
        return await asyncio.to_thread(desktop_access.add,body.name,body.command,body.cwd)

    @app.delete('/api/terminal/commands/{identifier}')
    async def remove_terminal_command(identifier:str):
        return await asyncio.to_thread(desktop_access.remove,identifier)

    @app.post('/api/terminal/propose')
    @app.post('/api/internal/terminal/propose')
    async def propose_terminal(body:TerminalChoice,request:Request):
        return await request_desktop('terminal',body.command_id,request)

    @app.post('/api/home/lookup')
    @app.post('/api/internal/home/lookup')
    async def inspect_home(body:HomeLookup,request:Request):
        if request.url.path.startswith('/api/internal/'):note_private_context()
        if body.kind=='read':
            result=await asyncio.to_thread(home_files.read,body.path,8192 if request.url.path.startswith('/api/internal/') else 32768)
            filtered=redact(result['text'])
            return {**result,'text':filtered,'credentials_redacted':filtered!=result['text']}
        return await asyncio.to_thread(home_files.lookup,body.kind,body.path,body.query)

    @app.get('/api/telemetry')
    @app.get('/api/internal/telemetry')
    async def metrics(): return await telemetry.sample()

    @app.get('/api/processes')
    @app.get('/api/internal/processes')
    async def processes(): return await telemetry.processes()

    @app.get('/api/internal/journal')
    async def journal(service:str): return await telemetry.journal(service)

    @app.post('/api/chat')
    async def chat(body:Chat,request:Request):
        if not body.text.strip(): raise HTTPException(400,'Message is empty')
        if shortcut_audio_busy(): raise HTTPException(409,'Stop or finish the shortcut announcement before starting an agent turn')
        if body.session_id:
            try: uuid.UUID(body.session_id)
            except ValueError: raise HTTPException(400,'Invalid session id')
        if chat_lock.locked(): raise HTTPException(409,'An agent turn is already running')
        await chat_lock.acquire()
        try:
            await agent.preflight()
            identifier=body.session_id or str(uuid.uuid4())
            generation=memory.epoch
            with sqlite3.connect(conversation_db) as db:
                if body.session_id:
                    row=db.execute('SELECT epoch,retired FROM sessions WHERE id=?',(identifier,)).fetchone()
                    if not row or row[0]!=generation or row[1]:
                        raise HTTPException(409,'Conversation is unknown, retired, or predates a memory change. Start a new conversation.')
                    if online_kinds(body.text)-{'time','location'} and db.execute('SELECT 1 FROM private_sessions WHERE id=?',(identifier,)).fetchone():
                        raise HTTPException(403,'Internet lookup is paused for this conversation because it contains home-file data. Start a new conversation before online searches.')
                else:
                    db.execute('INSERT INTO sessions(id,epoch) VALUES (?,?)',(identifier,generation))
        except BaseException:
            chat_lock.release()
            raise
        cancellation=asyncio.Event()
        finished=False
        released=False
        def release_turn():
            nonlocal released
            if released:return
            released=True
            try:
                if not finished:retire(identifier)
            finally:
                chat_lock.release()
        async def events():
            nonlocal finished
            with sqlite3.connect(conversation_db) as db:
                private_context=bool(db.execute('SELECT 1 FROM private_sessions WHERE id=?',(identifier,)).fetchone())
            state={'run_id':None,'cancel':cancellation,'closed':asyncio.Event(),'stop_confirmed':False,'private_context':private_context,'native_turn':None,'prompt_hash':hashlib.sha256(body.text.strip().encode()).hexdigest()}
            active[identifier]=state
            def encode(item): return 'data: '+json.dumps(item)+'\n\n'
            try:
                yield encode({'type':'session','session_id':identifier,'epoch':generation})
                yield encode({'type':'state','state':'thinking'})
                if online_kinds(body.text) & {'map','directions'}:yield encode({'type':'map_locating'})
                async for item in agent.stream(body.text.strip(),identifier,str(body.request_id)):
                    if item['type']=='run': state['run_id']=item['run_id']
                    if await request.is_disconnected(): break
                    if item['type']=='done': finished=True
                    yield encode(item)
            except asyncio.CancelledError:
                raise
            except HermesError as exc:
                yield encode({'type':'error','message':str(exc)})
            finally:
                try:
                    if state['run_id'] and not finished:
                        with anyio.move_on_after(3,shield=True):
                            with suppress(Exception): state['stop_confirmed']=await agent.stop(state['run_id'])
                finally:
                    active.pop(identifier,None)
                    try:release_turn()
                    finally:state['closed'].set()
        return ClosingStreamingResponse(with_heartbeat(events(),cancel=cancellation),release_turn,media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})

    @app.get('/api/models')
    async def model_catalog(): return await models.catalog()

    @app.post('/api/models/prepare')
    async def prepare_model(body:ModelChoice):
        if chat_lock.locked(): raise HTTPException(409,'Wait for the current agent turn before preparing a model.')
        async with chat_lock:
            return await models.prepare(body.model)

    @app.post('/api/models/select')
    async def select_model(body:ModelChoice):
        if chat_lock.locked(): raise HTTPException(409,'Wait for the current agent turn before switching models.')
        async with chat_lock:
            selected=await models.select(body.model)
            agent.set_model(selected['name'])
            with sqlite3.connect(conversation_db) as db:
                db.execute('UPDATE sessions SET retired=1')
            return {**selected,'new_session_required':True}

    def pending_reviews():
        actions=[{'source':'action','proposal_id':row['id'],'title':row['kind'].replace('_',' '),'target':row['target'],'effect':row['effect'],'expires':row['expires']} for row in approvals.list() if row['status']=='pending']
        memories=[{'source':'memory','proposal_id':row['id'],'title':row['action']+' memory','target':row['target'],'content':row['content'],'old_text':row['old_text'],'reason':row['reason']} for row in memory.pending()]
        scheduled=[{'source':'shortcut','proposal_id':row['id'],'title':'Create shortcut','target':row['spec']['name'],
                    'effect':row['summary'],'expires':row['expires']} for row in shortcuts.pending()]
        return actions+memories+scheduled

    @app.get('/api/reviews')
    async def review_queue(request:Request):
        owner=hashlib.sha256(request.cookies.get('jarvis_session','').encode()).hexdigest()
        return reviews.issue(owner,pending_reviews())

    @app.post('/api/reviews/{identifier}/resolve')
    async def resolve_review(identifier:str,body:ReviewResolve,request:Request):
        if chat_lock.locked(): raise HTTPException(409,'Wait for the agent turn to finish before resolving a proposal.')
        async with chat_lock:
            owner=hashlib.sha256(request.cookies.get('jarvis_session','').encode()).hexdigest()
            ticket=reviews.consume(owner,identifier,body.code,pending_reviews())
            if ticket['source']=='action':
                return await asyncio.to_thread(approvals.resolve,ticket['proposal_id'],body.approve)
            if ticket['source']=='shortcut':
                if body.approve:
                    proposal=next((row for row in shortcuts.pending() if row['id']==ticket['proposal_id']),None)
                    if not proposal:raise ValueError('Shortcut proposal expired')
                    validate_shortcut_actions(ShortcutSpec.model_validate(proposal['spec']),shortcut_runner,information)
                return {**shortcuts.resolve(ticket['proposal_id'],body.approve),'kind':'shortcut'}
            return await memory.resolve(ticket['proposal_id'],body.approve)

    @app.get('/api/conversations/{identifier}')
    async def conversation(identifier:str):
        try: uuid.UUID(identifier)
        except ValueError: raise HTTPException(400,'Invalid conversation id')
        with sqlite3.connect(conversation_db) as db:
            row=db.execute('SELECT epoch,retired FROM sessions WHERE id=?',(identifier,)).fetchone()
        if not row or row[0]!=memory.epoch or row[1]:
            raise HTTPException(409,'This conversation is retired. Begin a new conversation.')
        await agent.preflight()
        return {'messages':await agent.history(identifier),'epoch':row[0]}

    @app.post('/api/chat/{identifier}/cancel')
    async def cancel(identifier:str):
        state=active.get(identifier)
        stopped=False
        closed=not bool(state)
        if state:
            state['cancel'].set()
            retire(identifier)
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(state['closed'].wait(),4)
            closed=state['closed'].is_set()
            stopped=state['stop_confirmed']
        return {'stream_closed':closed,'agent_stop_confirmed':stopped,'message':'Remote cancellation is confirmed only when this Hermes version supplies a stoppable run id. Start a fresh conversation after cancellation.'}

    @app.get('/api/actions')
    async def actions(): return approvals.list()

    @app.post('/api/actions')
    @app.post('/api/internal/actions')
    async def propose_action(body:Action,request:Request):
        if body.kind=='launch':return await request_desktop('launch',body.target,request)
        if body.kind=='terminal':raise ValueError('Use a saved command from the terminal catalog')
        return await asyncio.to_thread(approvals.propose,body.kind,body.target,body.effect)

    @app.post('/api/actions/{identifier}/resolve')
    async def resolve_action(identifier:str,body:Resolve):
        return await asyncio.to_thread(approvals.resolve,identifier,body.approve)

    @app.get('/api/memory')
    @app.get('/api/internal/memory')
    async def memories(): return await memory.inventory()

    @app.post('/api/memory/proposals')
    async def propose_memory(body:MemoryProposal): return await memory.propose(body.model_dump())

    @app.post('/api/internal/memory/proposals')
    async def suggest_memory(body:MemoryProposal): return await memory.propose(body.model_dump(),automatic=True)

    @app.post('/api/memory/proposals/{identifier}/resolve')
    async def resolve_memory(identifier:str,body:Resolve): return await memory.resolve(identifier,body.approve)

    @app.post('/api/memory/suggestions')
    async def suggestions(body:Toggle): return {'enabled':memory.suggestions(body.enabled)}

    @app.post('/api/memory/{identifier}/pin')
    async def pin(identifier:str,body:Pin): memory.pin(identifier,body.pinned); return {'ok':True}

    @app.post('/api/audio/transcribe')
    async def transcribe(request:Request):
        if shortcut_audio_busy(): raise HTTPException(409,'Wait for the shortcut announcement before recording a new phrase')
        data=await request.body(); mime=request.headers.get('content-type','')
        try: validate_audio(data,mime)
        except ValueError as exc: raise HTTPException(415,str(exc))
        if len(transcriptions)>=2: raise HTTPException(429,'Local transcription is busy. Wait for the current recording or use text input.')
        owner=hashlib.sha256(request.cookies.get('jarvis_session','').encode()).hexdigest()
        job=asyncio.create_task(stt.transcribe(data,mime))
        transcriptions[job]=owner
        async def disconnected():
            while True:
                if (await request.receive())['type']=='http.disconnect':
                    job.cancel()
                    return
        watcher=asyncio.create_task(disconnected())
        try: return await job
        except asyncio.CancelledError: raise HTTPException(409,'Local transcription cancelled')
        except asyncio.TimeoutError: raise HTTPException(504,'Local transcription exceeded its time limit. Text chat remains available.')
        except (ImportError,RuntimeError,OSError) as exc: raise HTTPException(503,f'Local {settings.stt_provider} transcription failed; run npm start -- --prepare-stt and verify the configured local assets. Text chat remains available.') from exc
        finally:
            watcher.cancel()
            with suppress(asyncio.CancelledError): await watcher
            if not job.done():
                job.cancel()
                with suppress(asyncio.CancelledError): await job
            transcriptions.pop(job,None)

    @app.get('/api/audio/settings')
    async def audio_settings(): return tts.view()

    @app.post('/api/audio/settings')
    async def select_audio_device(body:SpeechDevice):
        if shortcut_audio_busy(): raise HTTPException(409,'Stop the shortcut announcement before changing its speech device')
        if speech_task and not speech_task.done(): raise HTTPException(409,'Stop speech before changing its device')
        return await tts.select_device(body.device)

    @app.post('/api/audio/prepare')
    async def prepare_audio():
        try: return await tts.prepare()
        except asyncio.TimeoutError: raise HTTPException(504,'JarvisLuxTTS exceeded its preparation time limit')

    @app.post('/api/audio/plan')
    async def plan_audio(body:Speech):
        if shortcut_audio_busy(): raise HTTPException(409,'A shortcut announcement is already using Jarvis audio')
        return {'phrases':speech_phrases(body.text)}

    @app.post('/api/audio/synthesize')
    async def synthesize(body:Speech):
        nonlocal speech_task,speech_id
        if shortcut_audio_busy(): raise HTTPException(409,'A shortcut announcement is already using Jarvis audio')
        now=time.monotonic()
        for key,expiry in tuple(cancelled_speech.items()):
            if expiry<=now: cancelled_speech.pop(key,None)
        if str(body.request_id) in cancelled_speech:
            raise HTTPException(409,'Speech generation cancelled')
        if speech_task and not speech_task.done(): raise HTTPException(409,'Speech generation is already running')
        speech_id=str(body.request_id)
        operation=tts.synthesize(body.text) if body.phrase_index is None else tts.synthesize(body.text,phrase_index=body.phrase_index)
        speech_task=asyncio.create_task(operation)
        try: return await speech_task
        except asyncio.CancelledError: raise HTTPException(409,'Speech generation cancelled')
        except asyncio.TimeoutError: raise HTTPException(504,'JarvisLuxTTS exceeded its synthesis time limit')

    @app.post('/api/audio/cancel')
    async def cancel_audio(body:SpeechCancel):
        # A cancelled phrase prefetch may reach the server after its cancellation.
        cancelled_speech[str(body.request_id)]=time.monotonic()+300
        if len(cancelled_speech)>1024:
            cancelled_speech.pop(next(iter(cancelled_speech)))
        if speech_id==str(body.request_id) and speech_task and not speech_task.done():
            speech_task.cancel()
            with suppress(asyncio.CancelledError): await speech_task
            return {'cancelled':True}
        return {'cancelled':False}

    @app.get('/api/audio/{identifier}')
    async def audio(identifier:str):
        tts.cleanup()
        item=tts.artifacts.get(identifier)
        if not item: raise HTTPException(404,'Audio expired; synthesize again to replay')
        return FileResponse(item['path'],media_type='audio/wav')

    @app.get('/api/monitoring')
    async def monitor(): return monitoring.view()

    @app.post('/api/monitoring')
    async def monitor_settings(body:MonitorSettings):
        import re
        if any(not re.fullmatch(r'[a-zA-Z0-9_.@-]+\.service',s) for s in body.services): raise HTTPException(400,'Invalid monitored service')
        return monitoring.settings(body.model_dump())

    @app.post('/api/routines')
    async def routine(body:Routine): return monitoring.routine(body.name,body.interval)

    @app.post('/api/routines/{identifier}')
    async def update_routine(identifier:str,body:Toggle): monitoring.update_routine(identifier,body.enabled); return {'ok':True}

    @app.delete('/api/routines/{identifier}')
    async def delete_routine(identifier:str): monitoring.update_routine(identifier,delete=True); return {'ok':True}

    dist=ROOT/'frontend/dist'
    if dist.is_dir(): app.mount('/',StaticFiles(directory=dist,html=True),name='frontend')
    return app
