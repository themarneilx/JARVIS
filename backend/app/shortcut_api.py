"""Browser-only shortcut controls and a proposal-only native agent bridge."""
import asyncio
from contextlib import suppress
import hashlib
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .shortcuts import ShortcutSpec


class Body(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Save(Body):
    spec: ShortcutSpec
    authorized: StrictBool


class Edit(Save):
    revision: int = Field(ge=1, strict=True)


class Enable(Body):
    enabled: StrictBool
    revision: int = Field(ge=1, strict=True)


class Client(Body):
    available: StrictBool
    voice_enabled: StrictBool
    busy: StrictBool


class Claim(Body):
    claim_id: str = Field(min_length=20, max_length=100)


class Audio(Claim):
    voice: StrictBool = True


class Finish(Claim):
    status: Literal['delivered', 'failed', 'muted']
    error: str = Field(default='', max_length=500)


def validate_shortcut_actions(spec, runner, information):
    if spec.weather:
        information.permission()
        if information.config.location is None: raise ValueError('Save your city in Settings before adding a weather briefing')
    if spec.delivery == 'desktop' and not runner.capabilities()['desktop_audio_available']:
        raise ValueError('Local desktop audio is unavailable in this backend session; choose browser delivery or launch within your desktop session')


def shortcut_routes(store, runner, information):
    router = APIRouter(prefix='/api')

    def owner(request):
        return hashlib.sha256(request.cookies.get('jarvis_session', '').encode()).hexdigest()

    def validate_actions(spec):
        validate_shortcut_actions(spec, runner, information)

    def capabilities():
        return {**runner.capabilities(), 'timezone': information.config.timezone, 'scheduler_error': getattr(store, 'scheduler_error', ''),
                'location_label': information.config.location.name if information.config.location else '',
                'weather_available': information.config.enabled and information.config.location is not None}

    @router.get('/shortcuts')
    async def overview():
        return {'shortcuts': store.list(), 'events': store.events(), 'capabilities': capabilities(), 'pending_count': len(store.pending())}

    @router.get('/internal/shortcuts')
    async def native_inventory():
        return store.inventory()

    @router.post('/internal/shortcuts/proposals')
    async def propose(body: ShortcutSpec):
        validate_actions(body)
        return store.propose(body)

    @router.post('/shortcuts')
    async def create(body: Save):
        if not body.authorized: raise HTTPException(403, 'Explicitly authorize this shortcut before enabling it')
        validate_actions(body.spec)
        return store.create(body.spec)

    @router.put('/shortcuts/{identifier}')
    async def edit(identifier: str, body: Edit):
        if not body.authorized: raise HTTPException(403, 'Review and authorize the edited shortcut')
        validate_actions(body.spec)
        current = store.update(identifier, body.revision, body.spec)
        await runner.stop_invalidated()
        return current

    @router.post('/shortcuts/{identifier}/enabled')
    async def enabled(identifier: str, body: Enable):
        if body.enabled: validate_actions(ShortcutSpec.model_validate(store.get(identifier)['spec']))
        current = store.set_enabled(identifier, body.revision, body.enabled)
        await runner.stop_invalidated()
        return current

    @router.delete('/shortcuts/{identifier}')
    async def delete(identifier: str, revision: int):
        if revision < 1: raise ValueError('Missing shortcut revision')
        store.delete(identifier, revision)
        await runner.stop_invalidated()
        return {'ok': True}

    @router.post('/shortcuts/{identifier}/run')
    async def run(identifier: str):
        validate_actions(ShortcutSpec.model_validate(store.get(identifier)['spec']))
        return store.run(identifier)

    @router.get('/shortcuts/events')
    async def events():
        return {'events': store.events()}

    @router.get('/shortcuts/stream')
    async def cancellation_stream(request: Request):
        queue = runner.subscribe()
        async def stream():
            try:
                yield ': ready\n\n'
                while not await request.is_disconnected():
                    try:
                        notice = await asyncio.wait_for(queue.get(), timeout=12)
                    except TimeoutError:
                        yield ': keepalive\n\n'
                        continue
                    yield 'data: ' + json.dumps(notice, separators=(',', ':')) + '\n\n'
            finally:
                runner.unsubscribe(queue)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @router.post('/shortcuts/client')
    async def heartbeat(body: Client, request: Request):
        return runner.heartbeat(owner(request), body.available, body.voice_enabled, body.busy)

    @router.post('/shortcuts/events/{identifier}/claim')
    async def claim(identifier: str, request: Request):
        if store.event(identifier)['delivery'] == 'desktop': raise HTTPException(403, 'This announcement is assigned to desktop playback')
        if runner.desktop_active: raise HTTPException(409, 'A desktop announcement is already in progress')
        if runner.foreground_busy() or runner.other_client_busy(owner(request)): raise HTTPException(409, 'Wait for foreground speech or the agent turn before playing an announcement')
        result = store.claim(identifier, owner(request))
        runner.track_browser_event(identifier)
        return result

    @router.post('/shortcuts/events/{identifier}/audio')
    async def prepare(identifier: str, body: Audio, request: Request):
        browser = owner(request)
        store.validate_claim(identifier, browser, body.claim_id)
        task = asyncio.create_task(runner.prepare(identifier, browser, body.claim_id, body.voice))
        try:
            while not task.done():
                if await request.is_disconnected():
                    task.cancel()
                    raise asyncio.CancelledError()
                await asyncio.sleep(.1)
            return await task
        except asyncio.CancelledError:
            task.cancel()
            with suppress(asyncio.CancelledError): await task
            if store.valid_event(identifier):
                with suppress(ValueError): store.finish(identifier, browser, body.claim_id, 'failed', 'Browser disconnected during announcement preparation')
            raise

    @router.post('/shortcuts/events/{identifier}/finish')
    async def finish(identifier: str, body: Finish, request: Request):
        result = store.finish(identifier, owner(request), body.claim_id, body.status, body.error)
        runner.forget_browser_event(identifier)
        return result

    @router.post('/shortcuts/events/{identifier}/stop')
    async def stop(identifier: str):
        await runner.stop(identifier)
        return store.stop(identifier)

    return router
