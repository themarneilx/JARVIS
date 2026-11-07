# Reduce speech startup latency

The existing CPU adapter measured 13.489 s cold / 3.052 s warm for a
73-character reply and 6.776 s warm for 245 characters. These are local samples,
not guarantees. The original voice uses three synthesis steps and speed 0.73.

Implementation:

1. Add an authenticated, idempotent preparation request when a paired browser
   has voice enabled. Load the original CPU model and encode its reference once.
   Keep synthesis serialized with preparation, cancellation and shutdown.
2. Normalize the complete final reply before splitting it into bounded spoken
   phrases. Preserve the existing full-WAV API for diagnostics and compatibility.
3. Play the first phrase as soon as its WAV is ready and prepare at most one next
   phrase while it plays. Retain real Web Audio analysis, device/volume controls,
   scoped cancellation and sequential playback. Never speak unverified deltas.
4. Test cancellation before and during playback, bounded prefetch, normalization,
   authentication and failed warm-up recovery. Measure real CPU latency again
   with private temporary artifacts and run an isolated browser speech check.
5. User-requested addition: measure the original CUDA path with Ollama resident,
   then expose CPU/CUDA in Settings with private persistence, a test sample and
   explicit device errors. Require 2 GiB free VRAM at GPU load and cap the
   PyTorch allocator at 25% of total VRAM.

The external voice checkout, its environment, voice pace, model steps and Ollama
service stay untouched. CPU is the initial default; GPU speech is explicitly
selected. Preparation retains model RAM/VRAM just as successful synthesis does;
stopping active synthesis still kills its worker. Future speech prepares it again.
