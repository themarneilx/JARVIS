"""Resident CPU synthesis worker using the original JarvisLuxTTS voice pipeline."""
import contextlib
import json
from pathlib import Path
import sys


def main():
    repo,output=map(Path,sys.argv[1:3])
    speed=float(sys.argv[3])
    device=sys.argv[4] if len(sys.argv)>4 else 'cpu'
    sys.path.insert(0,str(repo))
    engine=None
    for line in sys.stdin:
        try:
            payload=json.loads(line)
            import re
            operation=payload.get('op','synthesize')
            if operation not in ('prepare','synthesize'): raise ValueError('Invalid operation')
            if operation=='synthesize' and not re.fullmatch('[a-f0-9]{48}',payload['id']): raise ValueError('Invalid artifact id')
            with contextlib.redirect_stdout(sys.stderr):
                import soundfile as sf
                if engine is None:
                    if device=='cuda':
                        import torch
                        if not torch.cuda.is_available():
                            print(json.dumps({'ok':False,'error':'cuda_unavailable'}),file=sys.__stdout__,flush=True)
                            continue
                        if torch.cuda.mem_get_info()[0]<2*1024**3:
                            print(json.dumps({'ok':False,'error':'cuda_headroom'}),file=sys.__stdout__,flush=True)
                            continue
                        torch.cuda.set_per_process_memory_fraction(.25)
                    from audio import StreamJarvisTTS
                    engine=StreamJarvisTTS(device=device,prompt_audio=str(repo/'sample.mp3'),speed=speed)
                if operation=='synthesize':
                    # speak() plays on the host. Reuse its actual synthesis path, without host playback.
                    wav=engine.lux_tts.generate_speech(payload['text'],engine.encoded_prompt,num_steps=engine.num_steps,t_shift=engine.t_shift,speed=engine.speed,return_smooth=engine.return_smooth)
                    sf.write(str(output/f"{payload['id']}.wav"),wav.cpu().numpy().squeeze(),48000,subtype='PCM_16')
            print(json.dumps({'ok':True,'device':engine.device}),flush=True)
        except Exception as exc:
            import traceback
            traceback.print_exc(file=sys.stderr)
            error='cuda_oom' if device=='cuda' and 'out of memory' in str(exc).lower() else 'synthesis_failed'
            print(json.dumps({'ok':False,'error':error}),flush=True)


if __name__=='__main__': main()
