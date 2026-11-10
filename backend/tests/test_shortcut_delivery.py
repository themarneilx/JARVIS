import asyncio
from copy import deepcopy
from pathlib import Path
import wave

import httpx
import pytest

from app.information import Information, OnlineSettings


class DeliveryStore:
    def __init__(self, **spec):
        self.spec = dict(name='Reminder', trigger='manual', message='Ready, sir.', weather=False,
                         chime=False, delivery='auto', timezone='Asia/Manila') | spec
        self.item = dict(id='event', shortcut_id='shortcut', revision=1, name='Reminder',
                         status='pending', delivery=self.spec['delivery'], text='', sources=[], error='',
                         payload={'spec': self.spec, 'snapshot': {'battery_percent': 17}})
        self.revision = 1
        self.claim_owner = self.claim_id = None
        self.options = {'voice_enabled': True}

    def settings(self, payload=None):
        if payload is not None:
            self.options.update(payload)
        return self.options.copy()

    def events(self):
        return [deepcopy(self.item)]

    def event(self, identifier):
        assert identifier == 'event'
        return deepcopy(self.item)

    def valid_event(self, identifier):
        return self.item['revision'] == self.revision and self.item['status'] not in ('cancelled', 'failed', 'delivered', 'muted')

    def claim(self, identifier, owner):
        if self.item['status'] != 'pending' or not self.valid_event(identifier):
            raise ValueError('Event is already claimed or cancelled')
        self.claim_owner, self.claim_id = owner, 'claim'
        self.item['status'] = 'preparing'
        return {'claim_id': self.claim_id, 'event': self.event(identifier)}

    def validate_claim(self, identifier, owner, claim_id):
        if (owner, claim_id) != (self.claim_owner, self.claim_id) or not self.valid_event(identifier):
            raise ValueError('Stale or cancelled event claim')
        return self.event(identifier)

    def mark_preparing(self, identifier, owner, claim_id):
        self.validate_claim(identifier, owner, claim_id)
        self.item['status'] = 'preparing'

    def mark_playing(self, identifier, owner, claim_id):
        self.validate_claim(identifier, owner, claim_id)
        self.item['status'] = 'playing'

    def annotate(self, identifier, text, sources, error=''):
        self.item.update(text=text, sources=sources, error=error)

    def finish(self, identifier, owner, claim_id, status, error=''):
        self.validate_claim(identifier, owner, claim_id)
        self.item['status'] = status
        if error:
            self.item['error'] = error

    def stop(self, identifier):
        self.item['status'] = 'cancelled'


class FixtureTTS:
    def __init__(self, directory):
        self.directory = directory
        self.artifacts = {}
        self.calls = []
        self.started = asyncio.Event()
        self.release = None
        self.error = None
        self.frames = b'\x11\x00\x22\x00' * 2400

    async def synthesize(self, text):
        self.calls.append(text)
        self.started.set()
        if self.release is not None:
            await self.release.wait()
        if self.error:
            raise ValueError(self.error)
        path = self.directory / 'fixture.wav'
        with wave.open(str(path), 'wb') as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(24000)
            output.writeframes(self.frames)
        self.artifacts['fixture'] = {'created': 0, 'path': path}
        return {'id': 'fixture', 'url': '/api/audio/fixture', 'duration': 999}


def information_fixture(tmp_path, enabled=False, handler=None):
    info = Information(tmp_path, transport=httpx.MockTransport(handler or (lambda request: httpx.Response(500))))
    info.save(OnlineSettings(enabled=enabled, location={'id': 1, 'name': 'Cebu', 'country': 'Philippines',
              'country_code': 'PH', 'latitude': 10.3, 'longitude': 123.9, 'timezone': 'Asia/Manila'}))
    return info


def test_chime_prefix_uses_real_pcm_metadata_and_registers_audio(tmp_path):
    async def run():
        from app.shortcut_delivery import ShortcutRunner
        store = DeliveryStore(chime=True)
        tts = FixtureTTS(tmp_path)
        info = information_fixture(tmp_path)
        runner = ShortcutRunner(store, tts, info)
        claim = store.claim('event', 'browser-a')
        try:
            output = await runner.prepare('event', 'browser-a', claim['claim_id'])
            artifact = tts.artifacts[output['url'].rsplit('/', 1)[-1]]
            with wave.open(str(artifact['path'])) as audio:
                assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) == (24000, 2, 2)
                data = audio.readframes(audio.getnframes())
                assert data.endswith(tts.frames)
                assert len(data) > len(tts.frames)
                assert any(data[:-len(tts.frames)])
                assert output['duration'] == pytest.approx(audio.getnframes() / 24000)
            assert output['text'] == 'Ready, sir.'
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_voice_failure_keeps_chime_and_visible_text_without_substitute(tmp_path):
    async def run():
        from app.shortcut_delivery import ShortcutRunner
        store = DeliveryStore(chime=True)
        tts = FixtureTTS(tmp_path)
        tts.error = 'Selected JarvisLuxTTS import failed'
        info = information_fixture(tmp_path)
        runner = ShortcutRunner(store, tts, info)
        claim = store.claim('event', 'browser-a')
        try:
            result = await runner.prepare('event', 'browser-a', claim['claim_id'])
            assert result['url'] and result['duration'] > 0
            assert store.item['text'] == 'Ready, sir.'
            assert 'Selected JarvisLuxTTS import failed' in store.item['error']
            assert len(tts.calls) == 1
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_voice_failure_without_chime_is_explicit_and_keeps_text(tmp_path):
    async def run():
        from app.shortcut_delivery import ShortcutRunner
        store, tts, info = DeliveryStore(), FixtureTTS(tmp_path), information_fixture(tmp_path)
        tts.error = 'Selected voice failed'
        runner = ShortcutRunner(store, tts, info)
        claim = store.claim('event', 'browser-a')
        try:
            with pytest.raises(ValueError, match='Selected voice failed'):
                await runner.prepare('event', 'browser-a', claim['claim_id'])
            assert store.item['text'] == 'Ready, sir.'
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_voice_mute_is_persisted_and_chime_does_not_synthesize(tmp_path):
    async def run():
        from app.shortcut_delivery import ShortcutRunner
        store, tts, info = DeliveryStore(chime=True), FixtureTTS(tmp_path), information_fixture(tmp_path)
        runner = ShortcutRunner(store, tts, info)
        runner.heartbeat('browser-a', True, False, False)
        claim = store.claim('event', 'browser-a')
        try:
            result = await runner.prepare('event', 'browser-a', claim['claim_id'])
            assert store.settings()['voice_enabled'] is False
            assert result['url'] and not tts.calls
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_voice_mute_during_synthesis_discards_speech_but_keeps_chime(tmp_path):
    async def run():
        from app.shortcut_delivery import ShortcutRunner
        store, tts, info = DeliveryStore(chime=True), FixtureTTS(tmp_path), information_fixture(tmp_path)
        tts.release = asyncio.Event()
        runner = ShortcutRunner(store, tts, info)
        claim = store.claim('event', 'browser-a')
        job = asyncio.create_task(runner.prepare('event', 'browser-a', claim['claim_id']))
        try:
            await tts.started.wait()
            runner.heartbeat('browser-a', True, False, False)
            tts.release.set()
            result = await job
            assert result['duration'] == pytest.approx(.65)
            assert 'fixture' not in tts.artifacts and not (tmp_path / 'fixture.wav').exists()
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_stop_cancels_inflight_synthesis_and_leaves_no_artifact(tmp_path):
    async def run():
        from app.shortcut_delivery import ShortcutRunner
        store, tts, info = DeliveryStore(chime=True), FixtureTTS(tmp_path), information_fixture(tmp_path)
        tts.release = asyncio.Event()
        runner = ShortcutRunner(store, tts, info)
        claim = store.claim('event', 'browser-a')
        job = asyncio.create_task(runner.prepare('event', 'browser-a', claim['claim_id']))
        try:
            await tts.started.wait()
            await runner.stop('event')
            assert job.cancelled()
            assert store.item['status'] == 'cancelled'
            assert not tts.artifacts and not list(tmp_path.glob('*.wav'))
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_revision_change_during_synthesis_rejects_and_removes_late_audio(tmp_path):
    async def run():
        from app.shortcut_delivery import ShortcutRunner
        store, tts, info = DeliveryStore(), FixtureTTS(tmp_path), information_fixture(tmp_path)
        tts.release = asyncio.Event()
        runner = ShortcutRunner(store, tts, info)
        claim = store.claim('event', 'browser-a')
        job = asyncio.create_task(runner.prepare('event', 'browser-a', claim['claim_id']))
        try:
            await tts.started.wait()
            store.revision += 1
            tts.release.set()
            with pytest.raises(ValueError, match='[Ss]tale|[Cc]ancelled|changed'):
                await job
            assert not tts.artifacts and not list(tmp_path.glob('*.wav'))
            assert store.item['status'] != 'playing'
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_other_browser_cannot_prepare_an_owned_claim(tmp_path):
    async def run():
        from app.shortcut_delivery import ShortcutRunner
        store, tts, info = DeliveryStore(), FixtureTTS(tmp_path), information_fixture(tmp_path)
        runner = ShortcutRunner(store, tts, info)
        claim = store.claim('event', 'browser-a')
        try:
            with pytest.raises(ValueError, match='claim'):
                await runner.prepare('event', 'browser-b', claim['claim_id'])
            assert not tts.calls
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_revision_change_while_weather_is_pending_does_not_synthesize(tmp_path):
    async def run():
        from app.shortcut_delivery import ShortcutRunner
        started, release = asyncio.Event(), asyncio.Event()
        async def handler(request):
            started.set()
            await release.wait()
            return httpx.Response(503)
        store, tts = DeliveryStore(weather=True), FixtureTTS(tmp_path)
        info = information_fixture(tmp_path, enabled=True, handler=handler)
        runner = ShortcutRunner(store, tts, info)
        claim = store.claim('event', 'browser-a')
        job = asyncio.create_task(runner.prepare('event', 'browser-a', claim['claim_id']))
        try:
            await started.wait()
            store.revision += 1
            release.set()
            with pytest.raises(ValueError, match='[Ss]tale|[Cc]ancelled|changed'):
                await job
            assert not tts.calls and not tts.artifacts
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_weather_failure_preserves_announcement_and_reports_error(tmp_path):
    async def run():
        from app.shortcut_delivery import ShortcutRunner
        store = DeliveryStore(message='Battery is {battery_percent} percent in {location}.', weather=True)
        tts, info = FixtureTTS(tmp_path), information_fixture(tmp_path)
        runner = ShortcutRunner(store, tts, info)
        claim = store.claim('event', 'browser-a')
        try:
            result = await runner.prepare('event', 'browser-a', claim['claim_id'])
            assert result['text'] == 'Battery is 17 percent in Cebu. Weather is unavailable, sir.'
            assert 'disabled' in store.item['error']
            assert not store.item['sources']
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_weather_uses_existing_saved_city_provider_and_spoken_measurements(tmp_path):
    async def run():
        from app.shortcut_delivery import ShortcutRunner
        def handler(request):
            assert request.url.host == 'api.open-meteo.com'
            assert request.url.params['latitude'] == '10.3'
            return httpx.Response(200, json={'current': {'time': '2026-11-06T06:00', 'temperature_2m': 27.2,
                   'weather_code': 3}, 'daily': {'time': ['2026-11-06'], 'temperature_2m_min': [25],
                   'temperature_2m_max': [32], 'precipitation_probability_max': [65]}})
        store, tts = DeliveryStore(weather=True), FixtureTTS(tmp_path)
        info = information_fixture(tmp_path, enabled=True, handler=handler)
        runner = ShortcutRunner(store, tts, info)
        claim = store.claim('event', 'browser-a')
        try:
            result = await runner.prepare('event', 'browser-a', claim['claim_id'])
            assert all(value in result['text'] for value in ('27.2', '25', '32', 'overcast', 'estimate'))
            assert 'https://' not in result['text'] and len(result['text']) <= 1200
            assert store.item['sources'][0]['provider'] == 'Open-Meteo'
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


class PlaybackProcess:
    def __init__(self):
        self.returncode = None
        self.ended = asyncio.Event()
        self.killed = False

    async def wait(self):
        await self.ended.wait()
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9
        self.ended.set()


def test_auto_prefers_live_browser_then_desktop_after_expiry_and_stops_process(tmp_path, monkeypatch):
    async def run():
        import app.shortcut_delivery as delivery
        store, tts, info = DeliveryStore(), FixtureTTS(tmp_path), information_fixture(tmp_path)
        runner = delivery.ShortcutRunner(store, tts, info)
        monkeypatch.setattr(runner, 'capabilities', lambda: {'desktop_audio_available': True})
        clock = [100.0]
        monkeypatch.setattr(delivery, 'monotonic', lambda: clock[0])
        proc, calls = PlaybackProcess(), []
        async def spawn(*args, **kwargs):
            calls.append((args, kwargs))
            return proc
        monkeypatch.setattr(delivery.asyncio, 'create_subprocess_exec', spawn)
        monkeypatch.setenv('API_SERVER_KEY', 'must-not-reach-player')
        runner.heartbeat('browser-a', True, True, False)
        try:
            await runner.tick()
            assert store.item['status'] == 'pending'
            clock[0] += 16
            await runner.tick()
            for _ in range(20):
                await asyncio.sleep(0)
                if calls:
                    break
            assert len(calls) == 1
            argv, kwargs = calls[0]
            assert argv[0] == '/usr/bin/pw-play' and len(argv) == 2
            assert Path(argv[1]) == tts.artifacts['fixture']['path']
            assert 'API_SERVER_KEY' not in kwargs['env']
            assert runner.heartbeat('browser-a', True, True, False)['desktop_playing']
            await runner.tick()
            assert len(calls) == 1
            await runner.stop('event')
            assert proc.killed and store.item['status'] == 'cancelled'
            assert not tts.artifacts
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


@pytest.mark.parametrize('delivery_mode,browser_available,browser_busy,expected', [
    ('browser', False, False, False), ('desktop', True, True, False),
    ('auto', False, True, False), ('desktop', True, False, True),
])
def test_desktop_routing_respects_busy_clients_and_browser_only(tmp_path, monkeypatch, delivery_mode,
                                                            browser_available, browser_busy, expected):
    async def run():
        import app.shortcut_delivery as delivery
        store = DeliveryStore(delivery=delivery_mode)
        tts, info = FixtureTTS(tmp_path), information_fixture(tmp_path)
        runner = delivery.ShortcutRunner(store, tts, info)
        monkeypatch.setattr(runner, 'capabilities', lambda: {'desktop_audio_available': True})
        process, calls = PlaybackProcess(), []
        async def spawn(*args, **kwargs):
            calls.append(args)
            return process
        monkeypatch.setattr(delivery.asyncio, 'create_subprocess_exec', spawn)
        runner.heartbeat('browser-a', browser_available, True, browser_busy)
        try:
            await runner.tick()
            for _ in range(20):
                await asyncio.sleep(0)
            assert bool(calls) is expected
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_desktop_waits_for_client_that_became_busy_during_synthesis(tmp_path, monkeypatch):
    async def run():
        import app.shortcut_delivery as delivery
        store = DeliveryStore(delivery='desktop')
        tts, info = FixtureTTS(tmp_path), information_fixture(tmp_path)
        tts.release = asyncio.Event()
        runner = delivery.ShortcutRunner(store, tts, info)
        monkeypatch.setattr(runner, 'capabilities', lambda: {'desktop_audio_available': True})
        process, calls = PlaybackProcess(), []
        async def spawn(*args, **kwargs):
            calls.append(args)
            return process
        monkeypatch.setattr(delivery.asyncio, 'create_subprocess_exec', spawn)
        runner.heartbeat('browser-a', True, True, False)
        try:
            await runner.tick()
            await tts.started.wait()
            runner.heartbeat('browser-a', True, True, True)
            tts.release.set()
            for _ in range(20):
                await asyncio.sleep(0)
            assert not calls
            runner.heartbeat('browser-a', True, True, False)
            await asyncio.sleep(.3)
            assert calls
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_client_waiting_for_desktop_audio_does_not_override_foreground_claim(tmp_path, monkeypatch):
    async def run():
        import app.shortcut_delivery as delivery
        store, tts, info = DeliveryStore(delivery='desktop'), FixtureTTS(tmp_path), information_fixture(tmp_path)
        runner = delivery.ShortcutRunner(store, tts, info)
        monkeypatch.setattr(runner, 'capabilities', lambda: {'desktop_audio_available': True})
        store.claim('event', 'browser-a')
        try:
            await runner.tick()
            assert store.claim_owner == 'browser-a' and not tts.calls
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_close_after_delivery_preserves_terminal_history(tmp_path):
    async def run():
        from app.shortcut_delivery import ShortcutRunner
        store, tts, info = DeliveryStore(), FixtureTTS(tmp_path), information_fixture(tmp_path)
        runner = ShortcutRunner(store, tts, info)
        claim = store.claim('event', 'browser-a')
        try:
            await runner.prepare('event', 'browser-a', claim['claim_id'])
            store.finish('event', 'browser-a', claim['claim_id'], 'delivered')
            await runner.close()
            assert store.item['status'] == 'delivered'
            assert not tts.artifacts
        finally:
            await info.close()
    asyncio.run(run())


def test_auto_claim_is_consumed_if_browser_appears_before_output(tmp_path, monkeypatch):
    async def run():
        import app.shortcut_delivery as delivery
        store, tts, info = DeliveryStore(), FixtureTTS(tmp_path), information_fixture(tmp_path)
        tts.release = asyncio.Event()
        runner = delivery.ShortcutRunner(store, tts, info)
        monkeypatch.setattr(runner, 'capabilities', lambda: {'desktop_audio_available': True})
        calls = []
        async def spawn(*args, **kwargs):
            calls.append(args)
            return PlaybackProcess()
        monkeypatch.setattr(delivery.asyncio, 'create_subprocess_exec', spawn)
        try:
            await runner.tick()
            await tts.started.wait()
            runner.heartbeat('browser-a', True, True, False)
            tts.release.set()
            for _ in range(20):
                await asyncio.sleep(0)
            assert not calls and store.item['status'] == 'failed'
            assert 'browser became available' in store.item['error']
            assert not tts.artifacts
            await runner.tick()
            assert len(tts.calls) == 1
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_stop_during_desktop_process_creation_collects_and_kills_child(tmp_path, monkeypatch):
    async def run():
        import app.shortcut_delivery as delivery
        store, tts, info = DeliveryStore(), FixtureTTS(tmp_path), information_fixture(tmp_path)
        runner = delivery.ShortcutRunner(store, tts, info)
        monkeypatch.setattr(runner, 'capabilities', lambda: {'desktop_audio_available': True})
        spawning, release = asyncio.Event(), asyncio.Event()
        process = PlaybackProcess()
        async def spawn(*args, **kwargs):
            spawning.set()
            await release.wait()
            return process
        monkeypatch.setattr(delivery.asyncio, 'create_subprocess_exec', spawn)
        try:
            await runner.tick()
            await spawning.wait()
            stopping = asyncio.create_task(runner.stop('event'))
            await asyncio.sleep(0)
            release.set()
            await stopping
            assert process.killed and store.item['status'] == 'cancelled'
            assert not tts.artifacts
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_runner_integrates_real_claims_disable_and_durable_voice_setting(tmp_path):
    async def run():
        from app.shortcut_delivery import ShortcutRunner
        from app.shortcuts import Shortcuts
        store = Shortcuts(tmp_path / 'shortcuts.db')
        saved = store.create({'name': 'Morning', 'trigger': 'manual', 'message': 'Ready at {time}.', 'chime': True})
        event = store.run(saved['id'])
        tts, info = FixtureTTS(tmp_path), information_fixture(tmp_path)
        runner = ShortcutRunner(store, tts, info)
        runner.heartbeat('browser-a', True, False, False)
        claim = store.claim(event['id'], 'browser-a')
        try:
            result = await runner.prepare(event['id'], 'browser-a', claim['claim_id'])
            assert result['url'] and not tts.calls
            assert store.event(event['id'])['status'] == 'playing'
            assert Shortcuts(tmp_path / 'shortcuts.db').settings()['voice_enabled'] is False
            with pytest.raises(ValueError):
                store.claim(event['id'], 'browser-b')
            store.set_enabled(saved['id'], saved['revision'], False)
            await runner.stop(event['id'])
            assert store.event(event['id'])['status'] == 'cancelled'
            assert not tts.artifacts
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_no_chime_and_muted_voice_returns_visible_text_without_audio(tmp_path):
    async def run():
        from app.shortcut_delivery import ShortcutRunner
        store, tts, info = DeliveryStore(), FixtureTTS(tmp_path), information_fixture(tmp_path)
        runner = ShortcutRunner(store, tts, info)
        claim = store.claim('event', 'browser-a')
        try:
            result = await runner.prepare('event', 'browser-a', claim['claim_id'], voice=False)
            assert result == {'url': '', 'duration': 0, 'text': 'Ready, sir.'}
            assert not tts.calls and not tts.artifacts
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_unsupported_speech_sample_width_fails_without_playback(tmp_path):
    async def run():
        from app.shortcut_delivery import ShortcutRunner
        store, tts, info = DeliveryStore(), FixtureTTS(tmp_path), information_fixture(tmp_path)
        async def unsupported_audio(text):
            path = tmp_path / 'float.wav'
            with wave.open(str(path), 'wb') as output:
                output.setnchannels(1)
                output.setsampwidth(4)
                output.setframerate(48000)
                output.writeframes(b'\0' * 4800)
            tts.artifacts['unsupported'] = {'created': 0, 'path': path}
            return {'id': 'unsupported', 'url': '/api/audio/unsupported', 'duration': .025}
        tts.synthesize = unsupported_audio
        runner = ShortcutRunner(store, tts, info)
        claim = store.claim('event', 'browser-a')
        try:
            with pytest.raises(ValueError, match='PCM16'):
                await runner.prepare('event', 'browser-a', claim['claim_id'])
            assert store.item['status'] == 'failed'
            assert not tts.artifacts and not list(tmp_path.glob('*.wav'))
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_global_voice_mute_stops_already_playing_desktop_speech(tmp_path, monkeypatch):
    async def run():
        import app.shortcut_delivery as delivery
        store, tts, info = DeliveryStore(delivery='desktop'), FixtureTTS(tmp_path), information_fixture(tmp_path)
        runner = delivery.ShortcutRunner(store, tts, info)
        monkeypatch.setattr(runner, 'capabilities', lambda: {'desktop_audio_available': True})
        process, started = PlaybackProcess(), asyncio.Event()
        async def spawn(*args, **kwargs):
            started.set()
            return process
        monkeypatch.setattr(delivery.asyncio, 'create_subprocess_exec', spawn)
        try:
            await runner.tick()
            await started.wait()
            for _ in range(10):
                await asyncio.sleep(0)
            runner.heartbeat('browser-a', True, False, False)
            for _ in range(20):
                await asyncio.sleep(0)
            assert process.killed
            assert store.item['status'] == 'cancelled'
            assert not tts.artifacts
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_stop_invalidated_removes_owned_audio_without_rewriting_history(tmp_path):
    async def run():
        from app.shortcut_delivery import ShortcutRunner
        store, tts, info = DeliveryStore(), FixtureTTS(tmp_path), information_fixture(tmp_path)
        runner = ShortcutRunner(store, tts, info)
        claim = store.claim('event', 'browser-a')
        try:
            assert runner.desktop_active is False
            await runner.prepare('event', 'browser-a', claim['claim_id'])
            store.finish('event', 'browser-a', claim['claim_id'], 'delivered')
            await runner.stop_invalidated()
            assert store.item['status'] == 'delivered'
            assert not tts.artifacts and not list(tmp_path.glob('*.wav'))
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())


def test_invalidated_browser_audio_publishes_cancellation_to_other_tabs(tmp_path):
    async def run():
        from app.shortcut_delivery import ShortcutRunner
        store, tts, info = DeliveryStore(), FixtureTTS(tmp_path), information_fixture(tmp_path)
        runner = ShortcutRunner(store, tts, info)
        listener = runner.subscribe()
        claim = store.claim('event', 'browser-a')
        try:
            await runner.prepare('event', 'browser-a', claim['claim_id'])
            store.stop('event')
            await runner.stop_invalidated()
            assert await asyncio.wait_for(listener.get(), timeout=.1) == {'type': 'cancel', 'event_id': 'event'}
            assert not tts.artifacts and not list(tmp_path.glob('*.wav'))
        finally:
            runner.unsubscribe(listener)
            await runner.close()
            await info.close()
    asyncio.run(run())


@pytest.mark.parametrize('voice', [True, False])
def test_prepared_claim_cannot_synthesize_twice(tmp_path, voice):
    async def run():
        from app.shortcut_delivery import ShortcutRunner
        store, tts, info = DeliveryStore(), FixtureTTS(tmp_path), information_fixture(tmp_path)
        runner = ShortcutRunner(store, tts, info)
        claim = store.claim('event', 'browser-a')
        try:
            await runner.prepare('event', 'browser-a', claim['claim_id'], voice=voice)
            with pytest.raises(ValueError, match='already'):
                await runner.prepare('event', 'browser-a', claim['claim_id'])
            assert len(tts.calls) == int(voice)
        finally:
            await runner.close()
            await info.close()
    asyncio.run(run())
