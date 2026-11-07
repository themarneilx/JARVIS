# Interaction and model controls

The user requested permission popups, typed or spoken confirmations, an optional
“Hey Jarvis” listener, the installed Gemma model, and a browser model selector.
These extend the existing local architecture and its approval policy.

- [x] Keep chat streams alive during inference gaps; verify the fresh Zen failure.
- [x] Issue browser-owned review tickets for immutable action and memory proposals.
      Display one proposal at a time and require its short confirmation code for
      typed or spoken approval. Preserve all existing server validation.
- [x] Add the local VAD/transcription wake listener, off until explicitly enabled.
      Stop capture during foreground speech, recording, hidden tabs and locking.
- [x] List installed local Ollama models, prepare an explicitly requested separate
      64K alias when necessary, and select through Hermes’ supported request model
      controls. Retire conversations on switching; keep the global home intact.
- [x] Verify unit tests, production build, browser flows and real provider behavior;
      document measured limits and the distinction between fixtures and hardware.

Browser tests may use synthetic input to verify recording and UI behavior. They
do not prove physical microphone performance or speaker identity. Voice approval
is a convenience for a paired local browser, not speaker authentication.
