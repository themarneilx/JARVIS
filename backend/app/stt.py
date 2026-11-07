"""Bounded audio decoding and an isolated, resident local STT worker."""
import asyncio
import io
import json
import os
from pathlib import Path
import struct
import sys

MAX_RECORDING_BYTES=12*1024*1024
MAX_AUDIO_SECONDS=65
RATE=16000


def decode_audio(data):
    import av
    import numpy as np
    try:
        with av.open(io.BytesIO(data)) as container:
            if not container.streams.audio: raise ValueError('Recording has no audio stream')
            if container.duration and container.duration/av.time_base>MAX_AUDIO_SECONDS:
                raise ValueError('Recordings must be at most 60 seconds')
            stream=container.streams.audio[0]
            resampler=av.AudioResampler(format='s16',layout='mono',rate=RATE)
            chunks=[]
            count=0
            def append(frames):
                nonlocal count
                for frame in frames:
                    samples=frame.to_ndarray().flatten()
                    count+=len(samples)
                    if count>MAX_AUDIO_SECONDS*RATE: raise ValueError('Recording exceeds duration limit')
                    chunks.append(samples)
            for frame in container.decode(stream): append(resampler.resample(frame))
            append(resampler.resample(None))
        return np.concatenate(chunks).astype(np.float32)/32768 if chunks else np.zeros(0,dtype=np.float32)
    except av.FFmpegError as exc:
        raise ValueError('Audio could not be decoded. Record again or use text input.') from exc


class LocalSTT:
    def __init__(self,settings):
        self.settings=settings
        self.lock=asyncio.Lock()
        self.proc=None
        self.ready=False

    async def start(self):
        if self.proc and self.proc.returncode is None: return
        env={key:value for key,value in os.environ.items() if key in ('PATH','HOME','LANG','LC_ALL','LC_CTYPE','TMPDIR')}
        env.update(PYTHONPATH=str(Path(__file__).resolve().parents[1]),PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',DO_NOT_TRACK='1',CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='2')
        self.proc=await asyncio.create_subprocess_exec(sys.executable,'-m','app.stt_worker',self.settings.stt_provider,self.settings.stt_model,self.settings.stt_library,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,env=env,limit=128*1024)
        self.ready=False

    async def transcribe(self,data,mime):
        from .audio import validate_audio
        validate_audio(data,mime)
        async with self.lock:
            try:
                await self.start()
                self.proc.stdin.write(struct.pack('!I',len(data))+data)
                await self.proc.stdin.drain()
                result=json.loads(await asyncio.wait_for(self.proc.stdout.readline(),90))
                if not isinstance(result,dict): raise RuntimeError('Invalid local STT response')
                if result.get('error')=='invalid_audio': raise ValueError('Audio could not be decoded or exceeds the duration limit')
                if result.get('error'): raise RuntimeError('Local speech recognition failed')
                if not isinstance(result.get('text'),str) or len(result['text'])>16000 or not isinstance(result.get('duration'),(int,float)) or not 0<=result['duration']<=MAX_AUDIO_SECONDS or result.get('provider')!=self.settings.stt_provider or result.get('device')!='cpu':
                    raise RuntimeError('Invalid local STT response')
                self.ready=bool(result.get('model_loaded'))
                return result
            except (asyncio.CancelledError,asyncio.TimeoutError,ValueError,RuntimeError,OSError):
                await self.close()
                raise

    async def close(self):
        proc,self.proc=self.proc,None
        self.ready=False
        if proc and proc.returncode is None:
            try: proc.kill()
            except ProcessLookupError: pass
            await proc.wait()
