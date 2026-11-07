"""Input and worker protocol tests; real recognition is tested separately."""
import asyncio
import io
import json
import struct
import sys
import wave

import numpy as np
import pytest

from app.config import Settings


def wav_bytes(seconds=1,rate=48000,channels=2):
    output=io.BytesIO()
    with wave.open(output,'wb') as wav:
        wav.setnchannels(channels); wav.setsampwidth(2); wav.setframerate(rate)
        wav.writeframes((np.sin(np.arange(int(seconds*rate))*2*np.pi*440/rate)*6000).astype('<i2').repeat(channels).tobytes())
    return output.getvalue()


def test_decoder_resamples_to_bounded_mono_and_rejects_invalid_audio():
    from app.stt import decode_audio
    signal=decode_audio(wav_bytes())
    assert signal.dtype==np.float32 and signal.shape==(16000,)
    assert np.max(np.abs(signal))<1 and np.max(np.abs(signal))>.1
    with pytest.raises(ValueError): decode_audio(b'RIFF'+b'\0'*8+b'WAVEbad')
    with pytest.raises(ValueError): decode_audio(wav_bytes(seconds=66,rate=8000,channels=1))


def test_parakeet_is_the_default_without_silent_model_fallback(tmp_path):
    settings=Settings(state_dir=tmp_path)
    assert settings.stt_provider=='parakeet'
    assert settings.stt_model.endswith('parakeet-tdt-0.6b-v3.q8_0.gguf')
    assert settings.stt_library.endswith('libnemo_speech_asr_c.so')
    with pytest.raises(ValueError): Settings(state_dir=tmp_path,stt_provider='remote')


def test_stt_cancel_kills_its_worker_and_new_request_recovers(tmp_path,monkeypatch):
    from app.stt import LocalSTT
    marker=tmp_path/'started'
    program='''
import sys,struct,json,time
from pathlib import Path
while header:=sys.stdin.buffer.read(4):
    raw=sys.stdin.buffer.read(struct.unpack('!I',header)[0])
    path=Path(sys.argv[1])
    if not path.exists():
        path.write_text('started')
        time.sleep(60)
    print(json.dumps({'text':'Jarvis, are you there?','duration':1,'language':None,'provider':'parakeet','device':'cpu'}),flush=True)
'''
    async def start(self):
        if self.proc and self.proc.returncode is None: return
        self.proc=await asyncio.create_subprocess_exec(sys.executable,'-u','-c',program,str(marker),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE)
    monkeypatch.setattr(LocalSTT,'start',start)
    async def run():
        stt=LocalSTT(Settings(state_dir=tmp_path))
        task=asyncio.create_task(stt.transcribe(wav_bytes(),'audio/wav'))
        for _ in range(100):
            if marker.exists(): break
            await asyncio.sleep(.01)
        assert marker.exists()
        worker=stt.proc
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert worker.returncode is not None and stt.proc is None
        result=await stt.transcribe(wav_bytes(),'audio/wav')
        assert result['provider']=='parakeet' and result['text']=='Jarvis, are you there?'
        await stt.close()
    asyncio.run(run())


def test_stt_inference_is_serialized_and_silence_does_not_load_model(tmp_path,monkeypatch):
    from app.stt import LocalSTT
    from app.stt_worker import transcribe_signal
    class NeverLoad:
        def __init__(self,*args): raise AssertionError('Silence must not load a neural model')
    settings=Settings(state_dir=tmp_path)
    result,model=transcribe_signal(np.zeros(16000,dtype=np.float32),settings,None,parakeet_factory=NeverLoad)
    assert result['text']=='' and model is None
    program='''
import sys,struct,json,time
while header:=sys.stdin.buffer.read(4):
    raw=sys.stdin.buffer.read(struct.unpack('!I',header)[0])
    time.sleep(.05)
    print(json.dumps({'text':str(len(raw)),'duration':1,'language':None,'provider':'parakeet','device':'cpu'}),flush=True)
'''
    starts=[]
    async def start(self):
        if self.proc and self.proc.returncode is None: return
        starts.append(True)
        self.proc=await asyncio.create_subprocess_exec(sys.executable,'-u','-c',program,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE)
    monkeypatch.setattr(LocalSTT,'start',start)
    async def run():
        stt=LocalSTT(settings)
        raw=wav_bytes()
        try:
            results=await asyncio.gather(*(stt.transcribe(raw,'audio/wav') for _ in range(2)))
            assert [r['text'] for r in results]==[str(len(raw))]*2 and len(starts)==1
        finally: await stt.close()
    asyncio.run(run())
