"""Deliver authorized shortcut snapshots through the selected local voice."""
import asyncio
import math
import os
from pathlib import Path
import secrets
import stat
import struct
from time import monotonic, time
from datetime import datetime
import wave
from zoneinfo import ZoneInfo

from .audio import speech_text
from .information import Lookup, clean, number
from .memory import redact


class ShortcutRunner:
    def __init__(self, store, tts, information):
        self.store = store
        self.tts = tts
        self.information = information
        self._clients = {}
        self._preparing = {}
        self._artifacts = {}
        self._spoken = {}
        self._desktop_task = None
        self._desktop_event = None
        self._process = None
        self._cancel_subscribers = set()
        self._browser_events = set()
        self._closed = False
        self.foreground_busy = lambda: False

    @property
    def desktop_active(self):
        return self._desktop_event is not None

    def heartbeat(self, owner, available, voice_enabled, busy):
        self._clients[owner] = {'seen': monotonic(), 'available': bool(available), 'busy': bool(busy)}
        if self.store.settings()['voice_enabled'] != bool(voice_enabled):
            self.store.settings({'voice_enabled': bool(voice_enabled)})
        if (not voice_enabled and self._desktop_event is not None and self._spoken.get(self._desktop_event)
                and self._process is not None and self._process.returncode is None):
            self.store.stop(self._desktop_event)
            self._desktop_task.cancel()
        self._live_clients()
        return {'desktop_playing': self.desktop_active}

    def _live_clients(self):
        now = monotonic()
        self._clients = {owner: value for owner, value in self._clients.items() if now - value['seen'] < 15}
        return list(self._clients.values())

    def other_client_busy(self, owner):
        self._live_clients()
        return any(client['busy'] for key, client in self._clients.items() if key != owner)

    def forget_client(self, owner):
        self._clients.pop(owner, None)

    def subscribe(self):
        queue = asyncio.Queue(maxsize=64)
        self._cancel_subscribers.add(queue)
        return queue

    def unsubscribe(self, queue):
        self._cancel_subscribers.discard(queue)

    def publish_cancel(self, event_id):
        notice = {'type': 'cancel', 'event_id': event_id}
        for queue in tuple(self._cancel_subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(notice)
            except asyncio.QueueFull:
                pass

    def track_browser_event(self, event_id):
        self._browser_events.add(event_id)

    def forget_browser_event(self, event_id):
        self._browser_events.discard(event_id)

    def capabilities(self):
        player = Path('/usr/bin/pw-play')
        return {'desktop_audio_available': player.is_file() and os.access(player, os.X_OK)}

    def _validate(self, event_id, owner, claim_id):
        if self._closed or not self.store.valid_event(event_id):
            raise ValueError('Shortcut changed or was cancelled before delivery')
        return self.store.validate_claim(event_id, owner, claim_id)

    def _drop_audio(self, event_id, identifiers=None):
        if identifiers is None:
            self._spoken.pop(event_id, None)
        owned = self._artifacts.get(event_id, set())
        for identifier in list(owned if identifiers is None else identifiers):
            if identifier not in owned:
                continue
            artifact = self.tts.artifacts.pop(identifier, None)
            if artifact:
                path = Path(artifact['path'])
                if path.parent.resolve() == self.tts.directory.resolve():
                    path.unlink(missing_ok=True)
            owned.discard(identifier)
        if not owned:
            self._artifacts.pop(event_id, None)

    def _remember(self, event_id, identifier):
        self._artifacts.setdefault(event_id, set()).add(identifier)

    def _spec(self, event):
        return event['payload']['spec']

    async def _render(self, event, owner, claim_id):
        spec = self._spec(event)
        config = self.information.config
        now = datetime.now(ZoneInfo(spec.get('timezone') or config.timezone))
        snapshot = event.get('payload', {}).get('snapshot', {})
        battery = snapshot.get('battery_percent')
        if isinstance(battery, bool) or not isinstance(battery, (float, int)) or not math.isfinite(battery) or not 0 <= battery <= 100:
            battery = 'unavailable'
        else:
            battery = f'{battery:g}'
        values = {'time': now.strftime('%I:%M %p').lstrip('0'), 'date': now.strftime('%A, %B %d, %Y'),
                  'location': clean(config.location.name, 100) if config.location else 'location unavailable',
                  'battery_percent': battery}
        text = spec.get('message', '').format_map(values)
        text = speech_text(text)
        sources, errors = [], []
        if spec.get('weather'):
            try:
                report = await self.information.lookup(Lookup(kind='weather'))
                self._validate(event['id'], owner, claim_id)
                current = report['current']
                temperature = number(current['temperature_2m'])
                today = report['forecast'][0]
                low, high = number(today['low_c']), number(today['high_c'])
                condition = {0: 'clear', 1: 'mainly clear', 2: 'partly cloudy', 3: 'overcast', 45: 'foggy',
                             48: 'foggy', 51: 'light drizzle', 53: 'drizzle', 55: 'dense drizzle',
                             61: 'light rain', 63: 'rain', 65: 'heavy rain', 80: 'rain showers',
                             81: 'rain showers', 82: 'heavy showers', 95: 'thunderstorms',
                             96: 'thunderstorms with hail', 99: 'thunderstorms with hail'}.get(current.get('weather_code'), '')
                place = clean(report['location']['name'], 100)
                weather = (f'In {place}, it is {temperature:g} degrees Celsius'
                           + (f' and {condition}' if condition else '')
                           + f". Today's low is {low:g} and high is {high:g} degrees Celsius. Open-Meteo weather estimate.")
                text = f'{text} {weather}'.strip()
                sources.append({'title': 'Open-Meteo weather', 'provider': 'Open-Meteo',
                                'url': 'https://open-meteo.com/', 'as_of': clean(report.get('as_of'), 60)})
            except (ValueError, KeyError, IndexError, TypeError, OSError) as exc:
                self._validate(event['id'], owner, claim_id)
                text = f'{text} Weather is unavailable, sir.'.strip()
                errors.append('Weather unavailable: ' + self._error(exc))
        self._validate(event['id'], owner, claim_id)
        return speech_text(text or 'Your shortcut is ready, sir.')[:1200], sources, errors

    @staticmethod
    def _error(exc):
        return clean(redact(str(exc)), 400) or 'The selected local provider failed'

    def _read_pcm(self, artifact):
        path = Path(artifact['path'])
        if path.parent.resolve() != self.tts.directory.resolve():
            raise ValueError('Speech output is outside the local audio directory')
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 64 * 1024 * 1024:
                raise ValueError('Speech output is not a bounded regular WAV file')
            with wave.open(source, 'rb') as audio:
                rate, channels, width = audio.getframerate(), audio.getnchannels(), audio.getsampwidth()
                frames = audio.getnframes()
                if width != 2 or not 1 <= channels <= 8 or not 8000 <= rate <= 192000 or audio.getcomptype() != 'NONE' or not 0 < frames <= rate * 300:
                    raise ValueError('Speech output must be PCM16 WAV with supported channel and sample rates')
                data = audio.readframes(frames)
                if len(data) != frames * channels * width:
                    raise ValueError('Speech output contains incomplete PCM frames')
                return rate, channels, data, frames / rate

    @staticmethod
    def _chime(rate, channels):
        result = bytearray()
        tone_frames = int(rate * .5)
        for index in range(tone_frames):
            progress = index / rate
            fade = min(1, progress / .012) * math.exp(-7 * progress)
            tone = math.sin(math.tau * 880 * progress) + .45 * math.sin(math.tau * 1320 * progress)
            sample = int(6000 * fade * tone)
            result.extend(struct.pack('<h', sample) * channels)
        result.extend(b'\0' * (int(rate * .15) * channels * 2))
        return bytes(result)

    def _make_audio(self, event_id, rate, channels, data):
        identifier = secrets.token_hex(24)
        path = self.tts.directory / (identifier + '.wav')
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, 'wb') as destination:
                with wave.open(destination, 'wb') as output:
                    output.setnchannels(channels)
                    output.setsampwidth(2)
                    output.setframerate(rate)
                    output.writeframes(data)
            self.tts.artifacts[identifier] = {'created': time(), 'path': path}
            self._remember(event_id, identifier)
            return {'url': '/api/audio/' + identifier, 'duration': len(data) / (rate * channels * 2)}
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    async def prepare(self, event_id, owner, claim_id, voice=True):
        event = self._validate(event_id, owner, claim_id)
        if event_id in self._preparing or event['status'] == 'playing':
            raise ValueError('Shortcut audio is already preparing or prepared')
        self._preparing[event_id] = asyncio.current_task()
        try:
            self.store.mark_preparing(event_id, owner, claim_id)
            text, sources, errors = await self._render(event, owner, claim_id)
            self._validate(event_id, owner, claim_id)
            self.store.annotate(event_id, text, sources, '; '.join(errors))
            spec = self._spec(event)
            spoken = bool(voice and self.store.settings()['voice_enabled'])
            audio = None
            rate, channels, data = 48000, 1, b''
            if spoken:
                try:
                    audio = await self.tts.synthesize(text)
                    self._remember(event_id, audio['id'])
                    self._validate(event_id, owner, claim_id)
                    rate, channels, data, duration = self._read_pcm(self.tts.artifacts[audio['id']])
                except Exception as exc:
                    self._validate(event_id, owner, claim_id)
                    self._drop_audio(event_id)
                    errors.append('Speech unavailable: ' + self._error(exc))
                    self.store.annotate(event_id, text, sources, '; '.join(errors))
                    if not spec.get('chime'):
                        raise ValueError(errors[-1]) from exc
                    audio, rate, channels, data = None, 48000, 1, b''
            if not self.store.settings()['voice_enabled']:
                self._drop_audio(event_id)
                audio, rate, channels, data = None, 48000, 1, b''
            self._validate(event_id, owner, claim_id)
            if spec.get('chime'):
                result = self._make_audio(event_id, rate, channels, self._chime(rate, channels) + data)
                if audio:
                    self._drop_audio(event_id, [audio['id']])
            elif audio:
                result = {'url': audio['url'], 'duration': duration}
            else:
                result = {'url': '', 'duration': 0}
            self._validate(event_id, owner, claim_id)
            self.store.mark_playing(event_id, owner, claim_id)
            self._spoken[event_id] = bool(audio)
            return {**result, 'text': text}
        except asyncio.CancelledError:
            self._drop_audio(event_id)
            self.store.stop(event_id)
            raise
        except Exception as exc:
            self._drop_audio(event_id)
            try:
                self._validate(event_id, owner, claim_id)
                self.store.finish(event_id, owner, claim_id, 'failed', self._error(exc))
            except ValueError:
                pass
            raise
        finally:
            self._preparing.pop(event_id, None)

    @staticmethod
    def _desktop_environment():
        keys = {'PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'DISPLAY', 'WAYLAND_DISPLAY',
                'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_SESSION_TYPE',
                'PIPEWIRE_RUNTIME_DIR'}
        return {key: value for key, value in os.environ.items() if key in keys or key.startswith('LC_')}

    async def _start_player(self, path):
        spawning = asyncio.create_task(asyncio.create_subprocess_exec(
            '/usr/bin/pw-play', str(path), stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            env=self._desktop_environment()))
        try:
            self._process = await asyncio.shield(spawning)
        except asyncio.CancelledError:
            # Collect a process created during cancellation so the caller can stop it.
            self._process = await spawning
            raise

    async def _deliver_desktop(self, event_id, claim_id):
        try:
            prepared = await self.prepare(event_id, 'desktop', claim_id)
            self._validate(event_id, 'desktop', claim_id)
            if not prepared['url']:
                self.store.finish(event_id, 'desktop', claim_id, 'muted')
                return
            while self.foreground_busy() or any(client['busy'] for client in self._live_clients()):
                await asyncio.sleep(.25)
                self._validate(event_id, 'desktop', claim_id)
            event = self._validate(event_id, 'desktop', claim_id)
            if event['delivery'] == 'auto' and any(client['available'] for client in self._live_clients()):
                raise ValueError('A paired browser became available before automatic desktop playback. Run the shortcut again in the browser.')
            if not self.store.settings()['voice_enabled']:
                self._drop_audio(event_id)
                if not self._spec(event).get('chime'):
                    self.store.finish(event_id, 'desktop', claim_id, 'muted')
                    return
                prepared = self._make_audio(event_id, 48000, 1, self._chime(48000, 1))
            identifier = prepared['url'].rsplit('/', 1)[-1]
            artifact = self.tts.artifacts[identifier]
            await self._start_player(artifact['path'])
            self._validate(event_id, 'desktop', claim_id)
            if self._spoken.get(event_id) and not self.store.settings()['voice_enabled']:
                self.store.finish(event_id, 'desktop', claim_id, 'muted')
                return
            result = await asyncio.wait_for(self._process.wait(), timeout=prepared['duration'] + 15)
            self._validate(event_id, 'desktop', claim_id)
            if result:
                raise ValueError('Local desktop playback failed. Check the PipeWire output device.')
            self.store.finish(event_id, 'desktop', claim_id, 'delivered')
        except asyncio.CancelledError:
            self.store.stop(event_id)
            raise
        except Exception as exc:
            try:
                self._validate(event_id, 'desktop', claim_id)
                self.store.finish(event_id, 'desktop', claim_id, 'failed', self._error(exc))
            except ValueError:
                pass
        finally:
            if self._process is not None:
                if self._process.returncode is None:
                    try:
                        self._process.kill()
                    except ProcessLookupError:
                        pass
                    await self._process.wait()
                self._process = None
            self._drop_audio(event_id)
            self._desktop_event = None

    async def tick(self):
        if self._closed:
            return
        for identifier in list(self._artifacts):
            self._artifacts[identifier].intersection_update(self.tts.artifacts)
            if not self._artifacts[identifier]:
                self._artifacts.pop(identifier)
                self._spoken.pop(identifier, None)
        for identifier in list(set(self._preparing) | self._browser_events):
            if not self.store.valid_event(identifier):
                await self.stop(identifier)
        if self._desktop_event is not None and not self.store.valid_event(self._desktop_event):
            await self.stop(self._desktop_event)
        if self._desktop_task is not None:
            if not self._desktop_task.done():
                return
            self._desktop_task = None
        events = self.store.events()
        if any(event['status'] in ('preparing', 'playing') for event in events):
            return
        clients = self._live_clients()
        if self.foreground_busy() or any(client['busy'] for client in clients):
            return
        browser = any(client['available'] for client in clients)
        for event in reversed(events):
            if event['status'] != 'pending' or not self.store.valid_event(event['id']):
                continue
            delivery = event['delivery']
            if delivery == 'browser' or (delivery == 'auto' and browser):
                continue
            try:
                claim = self.store.claim(event['id'], 'desktop')
            except ValueError:
                continue
            if not self.capabilities()['desktop_audio_available']:
                self.store.finish(event['id'], 'desktop', claim['claim_id'], 'failed',
                                  'Local desktop audio is unavailable; /usr/bin/pw-play is required.')
                continue
            self._desktop_event = event['id']
            self._desktop_task = asyncio.create_task(self._deliver_desktop(event['id'], claim['claim_id']))
            return

    async def stop(self, event_id):
        try:
            event = self.store.event(event_id)
        except ValueError:
            event = None
        if event is not None and event['status'] in ('pending', 'preparing', 'playing'):
            self.store.stop(event_id)
        self.publish_cancel(event_id)
        self.forget_browser_event(event_id)
        jobs = {self._preparing.get(event_id)}
        if self._desktop_event == event_id:
            jobs.add(self._desktop_task)
        jobs.discard(None)
        jobs.discard(asyncio.current_task())
        for task in jobs:
            task.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
        self._drop_audio(event_id)

    async def stop_invalidated(self):
        identifiers = set(self._preparing) | set(self._artifacts) | self._browser_events
        if self._desktop_event is not None:
            identifiers.add(self._desktop_event)
        for identifier in identifiers:
            if not self.store.valid_event(identifier):
                await self.stop(identifier)

    async def close(self):
        self._closed = True
        identifiers = set(self._preparing)
        if self._desktop_event is not None:
            identifiers.add(self._desktop_event)
        for identifier in identifiers:
            await self.stop(identifier)
        for identifier in list(self._artifacts):
            self._drop_audio(identifier)
        self._clients.clear()
