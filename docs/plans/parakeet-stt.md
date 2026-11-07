# Parakeet speech-to-text implementation

Goal: use `nvidia/parakeet-tdt-0.6b-v3` for microphone, wake phrases and spoken
confirmations, while preserving local-only speech and typed interaction.

The selected path is NVIDIA's official Q8_0 GGUF (revision
541d1f99c6b0c3cd0b11a95167540bb8edefd82b) with the stable C ABI from the official
NeMo-Speech.cpp 0.3.0 CPU release. Full NeMo or Transformers would add a second
large PyTorch dependency stack to this Python 3.14 project. The native CPU runtime
keeps STT independent of the already-selected GPU TTS and Ollama allocation.

- [x] Pin and verify model/runtime SHA256 downloads in project-only storage;
      safely unpack the CPU bundle without installing shell scripts or packages.
- [x] Bind the public ASR C ABI, keep one recognizer resident, and free native
      results/recognizer correctly. Validate decoded 16 kHz mono audio in RAM.
- [x] Make Parakeet the explicit default. Keep faster-whisper available only
      through explicit configuration, with no automatic model substitution.
- [x] Serialize inference through cancellation and shutdown; reject invalid,
      oversized and silent input without persisting microphone audio.
- [x] Update Settings connection information, wake help, setup and README.
- [x] Run contract/security tests, real local model samples, browser microphone
      transport with synthetic speech, wake/confirmation checks where feasible,
      and CPU/RAM/VRAM measurements with the selected brain/TTS. Separate these
      results from physical microphone and real-room accuracy checks.

Only project artifacts/dependencies change. External speech environments, global
Hermes, Ollama service configuration, desktop settings and startup units remain
outside scope. The model lists 25 European languages including English; Tagalog
is not among its documented languages.
