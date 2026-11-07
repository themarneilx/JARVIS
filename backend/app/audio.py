import asyncio
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
import time
import wave
from .stt import LocalSTT


def speech_text(text):
    text=re.sub(r'```[\s\S]*?```',' Code is available in the conversation. ',text)
    text=re.sub(r'!\[[^\]]*\]\([^)]*\)','',text)
    text=re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',text)
    text=re.sub(r'https?://\S+','',text)
    text=re.sub(r'(?m)^\s*(?:#{1,6}|[-*>]|\d+\.)\s+','',text)
    text=re.sub(r'[`*_~|]','',text)
    from .memory import redact
    return ' '.join(redact(text).split())[:3500]


def speech_phrases(text):
    text=speech_text(text)
    if not text: raise ValueError('No speakable text in this response')
    phrases=[]
    while text:
        limit=160 if not phrases else 220
        if len(text)<=limit:
            phrases.append(text)
            break
        window=text[:limit+1]
        ends=[]
        for match in re.finditer(r'[.!?]["\u201d\u2019]?\s+',window):
            end=match.start()+1
            prefix=window[:end]
            if end>=60 and not re.search(r'\b(?:Dr|Mr|Mrs|Ms|Prof|Sr|Jr|vs|e\.g|i\.e)\.$',prefix,re.I):
                ends.append(match.end()-1)
        cut=ends[-1] if ends else window.rfind(' ',60,limit+1)
        if cut<60: cut=limit
        phrases.append(text[:cut].strip())
        text=text[cut:].lstrip()
    return phrases


def validate_audio(data, mime):
    base=mime.split(';')[0]
    if not data or len(data)>12*1024*1024:
        raise ValueError('Recording is empty or exceeds 12 MiB')
    valid=(base=='audio/webm' and data.startswith(b'\x1aE\xdf\xa3')) or (base=='audio/ogg' and data.startswith(b'OggS')) or (base in ('audio/wav','audio/x-wav') and data.startswith(b'RIFF') and data[8:12]==b'WAVE') or (base in ('audio/mp4','audio/x-m4a') and data[4:8]==b'ftyp')
    if not valid: raise ValueError('Unsupported or invalid audio container')
    return {'audio/webm':'.webm','audio/ogg':'.ogg','audio/wav':'.wav','audio/x-wav':'.wav','audio/mp4':'.m4a','audio/x-m4a':'.m4a'}[base]


class JarvisTTS:
    def __init__(self,settings):
        self.settings=settings
        self.proc=None
        self.ready=False
        self.lock=asyncio.Lock()
        self.directory=settings.state_dir/'audio'
        self.directory.mkdir(mode=0o700,exist_ok=True)
        self.artifacts={}
        self.device_path=settings.state_dir/'speech-settings.json'
        self.device=self._load_device()

    def _load_device(self):
        try:
            descriptor=os.open(self.device_path,os.O_RDONLY|os.O_NOFOLLOW)
        except FileNotFoundError: return self.settings.tts_device
        except OSError as exc: raise ValueError('Speech settings cannot be read safely') from exc
        with os.fdopen(descriptor) as file:
            info=os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode&0o077 or info.st_size>1024:
                raise ValueError('Speech settings must be a private regular file')
            data=json.load(file)
        if not isinstance(data,dict) or set(data)!={'version','device'} or data['version']!=1 or data['device'] not in ('cpu','cuda'):
            raise ValueError('Invalid speech device settings')
        return data['device']

    def view(self):
        return {'device':self.device,'ready':self.ready and self.proc is not None and self.proc.returncode is None,'provider':'JarvisLuxTTS','speed':self.settings.tts_speed}

    async def select_device(self,device):
        if device not in ('cpu','cuda'): raise ValueError('Choose cpu or cuda for speech')
        async with self.lock:
            if self.device_path.is_symlink(): raise ValueError('Speech settings cannot be a symbolic link')
            if device!=self.device:
                await self.close()
            descriptor,path=tempfile.mkstemp(prefix='.speech-settings-',dir=self.device_path.parent)
            try:
                with os.fdopen(descriptor,'w') as file:
                    json.dump({'version':1,'device':device},file)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(path,self.device_path)
            finally:
                Path(path).unlink(missing_ok=True)
            self.device=device
            return self.view()

    def worker_error(self,result,preparing=False):
        errors={
            'cuda_unavailable':'CUDA is unavailable in your JarvisLuxTTS environment. Select CPU speech or check the NVIDIA/PyTorch installation.',
            'cuda_headroom':'GPU speech needs at least 2 GiB of free VRAM before loading. Select CPU speech or a smaller AI model.',
            'cuda_oom':'JarvisLuxTTS reached its GPU memory limit. Select CPU speech or a smaller AI model.',
        }
        return errors.get(result.get('error'),'JarvisLuxTTS '+('preparation' if preparing else 'synthesis')+' failed; verify its cached models and dependencies. No substitute voice was selected.')

    def cleanup(self):
        now=time.time()
        for path in self.directory.glob('*.wav'):
            if now-path.stat().st_mtime>300:
                path.unlink(missing_ok=True)
        self.artifacts={k:v for k,v in self.artifacts.items() if now-v['created']<300}

    async def start(self):
        if self.proc and self.proc.returncode is None: return
        if not (self.settings.tts_repo/'audio.py').is_file() or not Path(self.settings.tts_python).exists():
            raise ValueError('JarvisLuxTTS checkout or Python environment is unavailable. Configure JARVIS_TTS_REPO and JARVIS_TTS_PYTHON.')
        env=dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',DO_NOT_TRACK='1',OMP_NUM_THREADS='2',CUDA_VISIBLE_DEVICES='0' if self.device=='cuda' else '')
        cache=self.settings.state_dir/'speech-models/hub'
        if cache.is_dir(): env['HF_HUB_CACHE']=str(cache)
        if self.device=='cuda' and cache.is_dir():
            # Reuse an already-installed reference model without downloading or editing the speech environment.
            base=cache/'models--openai--whisper-base'
            existing=Path(os.getenv('HF_HUB_CACHE',str(Path(os.getenv('HF_HOME',str(Path.home()/'.cache/huggingface')))/'hub')))/base.name
            if not base.exists() and not base.is_symlink() and existing.is_dir():
                base.symlink_to(existing.resolve(),target_is_directory=True)
        self.proc=await asyncio.create_subprocess_exec(self.settings.tts_python,str(Path(__file__).with_name('tts_worker.py')),str(self.settings.tts_repo),str(self.directory),str(self.settings.tts_speed),self.device,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,env=env)
        self.ready=False

    async def prepare(self):
        async with self.lock:
            if self.ready and self.proc and self.proc.returncode is None:
                return self.view()
            try:
                await self.start()
                self.proc.stdin.write(b'{"op":"prepare"}\n')
                await self.proc.stdin.drain()
                result=json.loads(await asyncio.wait_for(self.proc.stdout.readline(),240))
                if not result.get('ok'): raise ValueError(self.worker_error(result,preparing=True))
                if result.get('device')!=self.device: raise ValueError('Speech worker did not use the selected device')
                self.ready=True
                return self.view()
            except (asyncio.CancelledError,asyncio.TimeoutError,ValueError,BrokenPipeError):
                await self.close()
                raise

    async def synthesize(self,text,phrase_index=None):
        if phrase_index is None:
            text=speech_text(text)
        else:
            phrases=speech_phrases(text)
            if phrase_index<0 or phrase_index>=len(phrases): raise ValueError('Invalid speech phrase index')
            text=phrases[phrase_index]
        if not text: raise ValueError('No speakable text in this response')
        async with self.lock:
            self.cleanup()
            await self.start()
            identifier=secrets.token_hex(24)
            try:
                self.proc.stdin.write((json.dumps({'text':text,'id':identifier})+'\n').encode())
                await self.proc.stdin.drain()
                line=await asyncio.wait_for(self.proc.stdout.readline(),240)
                result=json.loads(line)
                path=self.directory/f'{identifier}.wav'
                if not result.get('ok') or not path.exists():
                    raise ValueError(self.worker_error(result))
                if result.get('device')!=self.device: raise ValueError('Speech worker did not use the selected device')
                self.ready=True
                with wave.open(str(path)) as wav:
                    duration=wav.getnframes()/wav.getframerate()
                self.artifacts[identifier]={'created':time.time(),'path':path}
                return {'id':identifier,'url':f'/api/audio/{identifier}','duration':duration,'provider':'JarvisLuxTTS','speed':self.settings.tts_speed,'device':self.device}
            except (asyncio.CancelledError,asyncio.TimeoutError,ValueError,BrokenPipeError):
                await self.close()
                (self.directory/f'{identifier}.wav').unlink(missing_ok=True)
                raise

    async def close(self,cleanup=False):
        if self.proc and self.proc.returncode is None:
            self.proc.kill()
            await self.proc.wait()
        self.proc=None
        self.ready=False
        if cleanup:
            for path in self.directory.glob('*.wav'):
                path.unlink(missing_ok=True)
            self.artifacts.clear()
