"""Exercise the selected local STT with real synthesized speech, without host playback."""
import asyncio
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import wave
import subprocess

import psutil

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.config import Settings
from app.audio import JarvisTTS
from app.stt import LocalSTT


async def main():
    with tempfile.TemporaryDirectory(prefix='jarvis-parakeet-check-') as temporary:
        state=Path(temporary)
        (state/'speech-models').symlink_to(ROOT/'.runtime/speech-models',target_is_directory=True)
        settings=Settings(state_dir=state,tts_device='cpu')
        tts,stt=JarvisTTS(settings),LocalSTT(settings)
        samples=[]
        try:
            for text in ['Hey Jarvis, give me a brief system status report.','Approve seven two four six.','Reject seven two four six.']:
                result=await tts.synthesize(text)
                samples.append((text,(tts.directory/f"{result['id']}.wav").read_bytes()))
            await tts.close(cleanup=True)
            for source,raw in samples:
                start=time.monotonic()
                result=await stt.transcribe(raw,'audio/wav')
                print(json.dumps({'source':source,'result':result,'seconds':round(time.monotonic()-start,3),'worker_rss_mib':round(psutil.Process(stt.proc.pid).memory_info().rss/2**20,1)}),flush=True)
                if '--compare' in sys.argv:
                    fresh=LocalSTT(settings)
                    legacy=LocalSTT(Settings(state_dir=state,stt_provider='faster-whisper',tts_device='cpu'))
                    try:
                        print(json.dumps({'comparison_source':source,'fresh_parakeet':await fresh.transcribe(raw,'audio/wav'),'explicit_whisper_comparison':await legacy.transcribe(raw,'audio/wav')}),flush=True)
                    finally:
                        await fresh.close()
                        await legacy.close()
            output=io.BytesIO()
            with wave.open(output,'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\0\0'*16000)
            silent=await stt.transcribe(output.getvalue(),'audio/wav')
            assert silent['text']==''
            if '--long' in sys.argv:
                with wave.open(io.BytesIO(samples[0][1])) as wav:
                    rate=wav.getframerate()
                    assert wav.getnchannels()==1 and wav.getsampwidth()==2
                    frames=wav.readframes(wav.getnframes())
                frames=(frames*(60*rate*2//len(frames)+1))[:60*rate*2]
                output=io.BytesIO()
                with wave.open(output,'wb') as wav:
                    wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(rate);wav.writeframes(frames)
                start=time.monotonic()
                long=await stt.transcribe(output.getvalue(),'audio/wav')
                print(json.dumps({'long_clip_seconds':long['duration'],'processing_seconds':round(time.monotonic()-start,3),'recognized_characters':len(long['text']),'worker_rss_mib':round(psutil.Process(stt.proc.pid).memory_info().rss/2**20,1)}),flush=True)
            try:
                rows=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,used_gpu_memory','--format=csv,noheader'],text=True,timeout=5).splitlines()
                allocation=next((row.split(',')[1].strip() for row in rows if row.split(',')[0].strip()==str(stt.proc.pid)),'0 MiB (process absent from GPU compute list)')
            except (OSError,subprocess.SubprocessError): allocation=None
            print(json.dumps({'stt_gpu_compute_allocation':allocation}),flush=True)
            print(json.dumps({'silence':silent,'mocked_stt':False,'physical_microphone_verified':False,'worker_pid':stt.proc.pid}),flush=True)
        finally:
            await tts.close(cleanup=True)
            await stt.close()


if __name__=='__main__': asyncio.run(main())
