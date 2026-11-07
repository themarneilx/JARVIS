"""Private framed stdin → JSON stdout worker. Recordings never touch disk."""
import json
import os
import struct
import sys
from types import SimpleNamespace

from .parakeet import ParakeetRecognizer
from .stt import decode_audio,MAX_RECORDING_BYTES,RATE


def transcribe_signal(signal,settings,model,parakeet_factory=ParakeetRecognizer):
    import numpy as np
    result={'text':'','language':None,'duration':len(signal)/RATE,'provider':settings.stt_provider,'device':'cpu'}
    if not len(signal) or float(np.max(np.abs(signal)))<.0005:
        return {**result,'model_loaded':model is not None},model
    if settings.stt_provider=='parakeet':
        if model is None: model=parakeet_factory(settings.stt_model,settings.stt_library)
        result['text']=model.transcribe(signal)
        result['model']='nvidia/parakeet-tdt-0.6b-v3'
        result['compute_type']='Q8_0'
    elif settings.stt_provider=='faster-whisper':
        if model is None:
            from faster_whisper import WhisperModel
            model=WhisperModel(settings.stt_model,device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,local_files_only=True)
        segments,info=model.transcribe(signal,beam_size=1,vad_filter=True,condition_on_previous_text=False)
        result['text']=' '.join(segment.text.strip() for segment in segments)
        result['language']=info.language
        result['compute_type']='int8'
    else: raise ValueError('Unsupported local STT provider')
    return {**result,'model_loaded':True},model


def main():
    settings=SimpleNamespace(stt_provider=sys.argv[1],stt_model=sys.argv[2],stt_library=sys.argv[3])
    # Native libraries may print to fd 1; keep the result protocol on a separate descriptor.
    protocol=os.fdopen(os.dup(sys.stdout.fileno()),'w',buffering=1)
    os.dup2(sys.stderr.fileno(),sys.stdout.fileno())
    model=None
    try:
        while header:=sys.stdin.buffer.read(4):
            if len(header)!=4: break
            length=struct.unpack('!I',header)[0]
            if not 0<length<=MAX_RECORDING_BYTES: break
            raw=sys.stdin.buffer.read(length)
            if len(raw)!=length: break
            try:
                signal=decode_audio(raw)
            except ValueError:
                print(json.dumps({'error':'invalid_audio'}),file=protocol,flush=True)
                continue
            try:
                result,model=transcribe_signal(signal,settings,model)
                print(json.dumps(result),file=protocol,flush=True)
            except Exception:
                print(json.dumps({'error':'recognition_failed'}),file=protocol,flush=True)
    finally:
        if settings.stt_provider=='parakeet' and model is not None: model.close()


if __name__=='__main__': main()
