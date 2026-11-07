"""Protocol fixtures exercise startup/cleanup, not the real voice model."""
import asyncio
import sys

import httpx
import pytest

from app.audio import JarvisTTS, speech_text
from app.config import Settings
from app.main import create_app


def test_spoken_phrases_normalize_before_split_and_preserve_all_text():
    from app.audio import speech_phrases
    text = '# Status\n**Ready**, sir. ' + 'Your system readings are available. ' * 25 + '\n```sh\nsecret-command\n```\npassword=private123'
    chunks = speech_phrases(text)
    assert len(chunks) > 1 and all(0 < len(c) <= 220 for c in chunks)
    assert len(chunks[0]) <= 160
    assert ' '.join(chunks) == speech_text(text)
    assert not any('secret-command' in c or 'private123' in c for c in chunks)
    assert speech_phrases('At your service, sir.') == ['At your service, sir.']
    with pytest.raises(ValueError):
        speech_phrases('')


def test_spoken_phrases_keep_decimal_and_abbreviation_together():
    from app.audio import speech_phrases
    text = 'The GPU is using 2.75 GB. Dr. Smith requested this report. ' * 8
    chunks = speech_phrases(text)
    assert ' '.join(chunks) == speech_text(text)
    assert all(not c.endswith(('2.', 'Dr.')) for c in chunks[:-1])
    huge = 'x' * 500
    assert ''.join(speech_phrases(huge)) == huge


def test_prepare_reuses_original_engine_and_can_recover_after_cancellation(tmp_path):
    repo = tmp_path / 'voice'
    repo.mkdir()
    (repo / 'audio.py').write_text('''
from pathlib import Path
class Wave:
    def cpu(self): return self
    def numpy(self): return self
    def squeeze(self): return self
class StreamJarvisTTS:
    def __init__(self, **kwargs):
        with open(Path(__file__).with_name('loads'), 'a') as f: f.write('load\\n')
        self.encoded_prompt = 'original-reference'
        self.device = kwargs['device']
        self.num_steps, self.t_shift, self.speed, self.return_smooth = 3, 1, kwargs['speed'], False
        self.lux_tts = self
    def generate_speech(self, text, prompt, **kwargs):
        assert prompt == 'original-reference' and kwargs['num_steps'] == 3
        import time
        if text == 'block': time.sleep(60)
        with open(Path(__file__).with_name('spoken'), 'a') as f: f.write(text + '\\n')
        return Wave()
''')
    (repo / 'soundfile.py').write_text('''
import wave
def write(path, *args, **kwargs):
    with wave.open(path, 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(48000)
        f.writeframes(b'\\x00\\x00' * 4800)
''')

    async def run():
        tts = JarvisTTS(Settings(state_dir=tmp_path / 'state', tts_repo=repo, tts_python=sys.executable))
        try:
            await asyncio.gather(tts.prepare(), tts.prepare())
            assert (repo / 'loads').read_text().splitlines() == ['load']
            from app.audio import speech_phrases
            source = 'a '*80 + '53.0 degrees Celsius. This is an example, followed by -5.25 degrees.'
            phrases = speech_phrases(source)
            for index in range(len(phrases)):
                await tts.synthesize(source, phrase_index=index)
            assert (repo / 'spoken').read_text().splitlines() == phrases
            with pytest.raises(ValueError): await tts.synthesize(source, phrase_index=999)
            result = await tts.synthesize('At your service, sir.')
            assert result['duration'] == .1
            assert (repo / 'loads').read_text().splitlines() == ['load']
            blocked = asyncio.create_task(tts.synthesize('block'))
            await asyncio.sleep(.1)
            blocked.cancel()
            with pytest.raises(asyncio.CancelledError): await blocked
            await tts.prepare()
            assert len((repo / 'loads').read_text().splitlines()) == 2
            await tts.synthesize('Ready again.')
        finally:
            await tts.close(cleanup=True)
        assert not list(tts.directory.glob('*.wav'))
    asyncio.run(run())


@pytest.mark.parametrize('available,free,expected', [(False,3*1024**3,'CUDA is unavailable'), (True,1024**3,'free VRAM')])
def test_cuda_guard_rejects_unavailable_or_full_gpu_before_loading_voice(tmp_path,available,free,expected):
    repo=tmp_path/'voice'
    repo.mkdir()
    (repo/'audio.py').write_text("raise RuntimeError('Voice must not load before the guard passes')")
    (repo/'soundfile.py').write_text('')
    (repo/'torch.py').write_text(f'class cuda:\n    @staticmethod\n    def is_available(): return {available}\n    @staticmethod\n    def mem_get_info(): return {free}, 6*1024**3\n')
    async def run():
        tts=JarvisTTS(Settings(state_dir=tmp_path/'state',tts_repo=repo,tts_python=sys.executable,tts_device='cuda'))
        with pytest.raises(ValueError,match=expected): await tts.prepare()
        assert tts.proc is None and not tts.view()['ready']
    asyncio.run(run())


def test_speech_device_selection_is_private_persisted_and_validated(tmp_path):
    async def run():
        settings = Settings(state_dir=tmp_path)
        tts = JarvisTTS(settings)
        assert tts.view()['device'] == 'cpu'
        await tts.select_device('cuda')
        assert JarvisTTS(settings).view()['device'] == 'cuda'
        assert (tmp_path/'speech-settings.json').stat().st_mode & 0o077 == 0
        with pytest.raises(ValueError): await tts.select_device('shell')
        await tts.select_device('cpu')
        assert JarvisTTS(settings).view()['device'] == 'cpu'
        (tmp_path/'speech-settings.json').unlink()
        other = tmp_path/'other'
        other.write_text('{"version":1,"device":"cuda"}')
        (tmp_path/'speech-settings.json').symlink_to(other)
        with pytest.raises(ValueError): JarvisTTS(settings)
        with pytest.raises(ValueError): await tts.select_device('cuda')
    asyncio.run(run())


def test_preparation_and_phrase_planning_require_browser_csrf(tmp_path, monkeypatch):
    async def run():
        calls = []
        async def prepare(self): calls.append(True); return {'ready': True}
        monkeypatch.setattr(JarvisTTS, 'prepare', prepare)
        app = create_app(Settings(state_dir=tmp_path, login_token='test'))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1:8787') as c:
            origin = {'origin': 'http://127.0.0.1:8787'}
            assert (await c.post('/api/audio/prepare', headers=origin)).status_code == 401
            assert (await c.post('/api/audio/settings', json={'device':'cuda'}, headers=origin)).status_code == 401
            login = await c.post('/api/auth/login', json={'token': 'test'}, headers=origin)
            assert (await c.post('/api/audio/prepare', headers=origin)).status_code == 403
            headers = {**origin, 'x-csrf-token': login.json()['csrf']}
            assert (await c.post('/api/audio/settings', json={'device':'cuda'}, headers=origin)).status_code == 403
            assert (await c.post('/api/audio/settings', json={'device':'shell'}, headers=headers)).status_code == 422
            selected = await c.post('/api/audio/settings', json={'device':'cuda'}, headers=headers)
            assert selected.json()['device'] == 'cuda' and not selected.json()['ready']
            assert (await c.get('/api/audio/settings')).json()['device'] == 'cuda'
            assert (await c.post('/api/audio/prepare', headers=headers)).json()['ready']
            response = await c.post('/api/audio/plan', json={'text': 'At your service, sir.'}, headers=headers)
            assert response.json() == {'phrases': ['At your service, sir.']}
            assert (await c.post('/api/audio/plan', json={'text': 'x'*12001}, headers=headers)).status_code == 422
            assert calls == [True]
    asyncio.run(run())
