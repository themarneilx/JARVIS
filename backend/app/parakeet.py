"""Bindings for NVIDIA NeMo-Speech.cpp's installed, size-tagged ASR C ABI."""
import ctypes as c
import os
from pathlib import Path


class Backend(c.Structure):
    _fields_=[('size',c.c_size_t),('gpu',c.c_int32)]


class Model(c.Structure):
    _fields_=[('size',c.c_size_t),('path',c.c_char_p),('name',c.c_char_p)]


class RecognizerConfig(c.Structure):
    # The ABI explicitly accepts this prefix and defaults omitted optional tails.
    _fields_=[('size',c.c_size_t),('backend',c.POINTER(Backend)),('model',c.POINTER(Model))]


class ParakeetRecognizer:
    def __init__(self,model,library):
        if not Path(model).is_file() or not Path(library).is_file():
            raise RuntimeError('Parakeet assets are missing. Run npm start -- --prepare-stt.')
        self.library=c.CDLL(str(library))
        signatures={
            'version':([],c.c_char_p),
            'last_error':([],c.c_char_p),
            'create':([c.POINTER(RecognizerConfig),c.POINTER(c.c_void_p)],c.c_int),
            'destroy':([c.c_void_p],None),
            'recognize_f32':([c.c_void_p,c.c_void_p,c.POINTER(c.c_float),c.c_size_t,c.c_int32,c.POINTER(c.c_void_p)],c.c_int),
            'result_transcript':([c.c_void_p,c.c_size_t],c.c_char_p),
            'result_destroy':([c.c_void_p],None),
        }
        for name,(arguments,result) in signatures.items():
            function=getattr(self.library,'nemo_speech_asr_'+name)
            function.argtypes=arguments
            function.restype=result
        version=self.library.nemo_speech_asr_version().decode('utf-8')
        if version.split()[-1].split('+',1)[0]!='0.3.0':
            raise RuntimeError('Parakeet requires the reviewed NeMo-Speech.cpp 0.3.0 runtime.')
        backend=Backend(c.sizeof(Backend),-1)
        definition=Model(c.sizeof(Model),os.fsencode(model),None)
        config=RecognizerConfig(c.sizeof(RecognizerConfig),c.pointer(backend),c.pointer(definition))
        self.handle=c.c_void_p()
        if self.library.nemo_speech_asr_create(c.byref(config),c.byref(self.handle)) or not self.handle:
            self.close()
            raise RuntimeError('Parakeet could not load the local model. Verify the pinned model/runtime with npm start -- --prepare-stt.')

    def transcribe(self,signal):
        if not self.handle: raise RuntimeError('Parakeet recognizer is closed')
        result=c.c_void_p()
        try:
            status=self.library.nemo_speech_asr_recognize_f32(self.handle,None,signal.ctypes.data_as(c.POINTER(c.c_float)),len(signal),16000,c.byref(result))
            if status or not result: raise RuntimeError('Parakeet could not recognize this audio')
            text=self.library.nemo_speech_asr_result_transcript(result,0)
            return text.decode('utf-8','replace').strip() if text else ''
        finally:
            if result: self.library.nemo_speech_asr_result_destroy(result)

    def close(self):
        if getattr(self,'handle',None):
            self.library.nemo_speech_asr_destroy(self.handle)
            self.handle=c.c_void_p()
