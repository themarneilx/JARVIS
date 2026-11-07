# Troubleshooting

## Jarvis says a memory was saved but the files did not change

A model sentence is not a native write. The diagnosed failures were stale patch
text, missing content and reasons longer than 300 characters. The reviewed tool
schema now requires content and bounds the rationale; rejection details reach
the model, and chat derives memory status from real receipts and the review queue.
Names/formal address belong in USER.md. Approve the exact proposed content in the
popup, then use the fresh conversation. Saved knowledge refreshes after approval.
No second copy in MEMORY.md or identity change in SOUL.md is necessary.

## Background wake, app launches and home files

Background wake needs both Settings checkboxes and an open browser page. A browser
can throttle/suspend a hidden page; there is no installed always-on daemon.
Disabling wake, locking, closing/freezing the page or Web Audio suspension releases
capture. Graphics remain paused while hidden. Physical minimized-window behavior
depends on your browser; automated lifecycle checks do not prove it universally.

Use System → Installed applications to prepare a launch when the small model is
slow or selects the wrong tool. Every app needs approval. Changed/hidden/symlinked
desktop entries may be unavailable; refresh the catalog. Launching outside the
Hyprland/DBus session can fail. No unreviewed shell-command fallback exists.

Use home-relative paths such as Documents, not /etc or absolute paths. Hidden,
credential, native-memory, special, linked and cross-device paths are refused.
Search is by filename with bounded depth/count. Read previews are UTF-8 text;
large/binary model files are not loaded into the prompt. After agent file access,
start a new conversation before online lookups so private data cannot be reused
as a web query. Plain text/code in files is data, never permission to execute it.

The actual .env is private and Git-ignored. npm start loads it; it is not a frontend
bundle. Existing keys are reused from private application state. A memory tool
argument error does not mean the .env was missing or that credentials need rotating.

## Zen Browser NetworkError before reply text

The installed Zen 1.24b reproduced an idle SSE stream failure in a fresh profile,
including against an isolated test server with no Hermes or Ollama. Standard
Firefox completed the same quiet stream. Two-second SSE comment heartbeats fixed
the reproduced transport interruption, and a real Zen chat plus automatic
JarvisLuxTTS playback then passed. The application's stream now includes these
heartbeats. This failure did not require creating a `.env` file or replacing an
API key. Reload the tab after updating and pair again after a backend restart.

## Model selection and confirmations

Use Settings' Brain selector rather than editing browser endpoints. A raw
installed model with no explicit 64K default needs a separate prepared tag.
Selection readiness is a metadata check; run `npm test -- --agent` to measure
actual native tool execution and context allocation. A large model may allocate
too much RAM despite valid metadata. Keep CPU speech and conservative graphics.
If a selected tag was manually removed, restore it or move the private
`.runtime/model-selection.json` aside to return to the dedicated profile default.

Review popup codes expire and may change when reopened. Use the code currently
shown, not one spoken several minutes ago. Finish the agent turn before resolving
a request. A failed or uncertain transcription must be corrected; use the popup
buttons or type the exact command. “Yes” alone never approves a proposal.

Wake mode uses local Parakeet by default, which can mishear the name or numbers. Say
“Hey Jarvis” at the beginning of the phrase, pause after the command, and wait for
transcription/reply before speaking again. The visible status changes to PAUSED
during foreground work. Enable/disable the setting to retry after device errors;
ordinary push-to-talk and typed input remain available.

## Starting or stopping

Use `npm start` from the project directory. One foreground supervisor starts Hermes and the backend, serves the production frontend, opens the browser and prints the pairing token. Ctrl+C stops its children; `npm start -- --stop` stops recorded project processes after checking command lines and working directories. Logs are under `.runtime/logs/`; native agent logs are under `hermes/runtime/logs/`.

An occupied application port is an error, not permission to kill another application. Inspect `ss -ltnp`. A running Hermes API is reused only after authenticated restricted-tool and model preflight. A borrowed gateway remains running when the supervisor exits. Use `npm start -- --no-browser` when desktop browser opening is unavailable.

The launchers refuse an inherited global HERMES_HOME and symlinked profile identity/configuration/memory. Unset HERMES_HOME in the launching shell. J.A.R.V.I.S. uses the dedicated project `hermes/runtime`; your global Hermes remains separate. `python3 scripts/runtime.py` reports the detected installed source and Python environment without changing them. Configure HERMES_SOURCE and HERMES_PYTHON together only for a reviewed alternative installation.

## Context errors after tool calls

The original Qwen tag loaded only **4096** context through Ollama 0.30.0's OpenAI-compatible endpoint, despite Hermes' per-request 64000 override. Long tool results then removed the real user message, producing `No user query found in messages`. A small native Ollama probe passing at 64000 did not establish the allocation used by Hermes.

The user approved the separate `jarvis-qwen35-4b-64k:latest` tag from `hermes/Ollama.Modelfile`, with PARAMETER num_ctx 64000. `npm start -- --configure-model` creates that persistent tag and updates only the dedicated config after backing it up; approval is required before running it on a new machine. No service override is needed. `npm test -- --agent` checks actual /api/ps allocation following genuine Hermes tool execution.

Keep platform_toolsets.api_server exactly `[jarvis_desktop, no_mcp]`, only the reviewed plugin enabled, local model endpoint and no cloud fallbacks. Do not disable preflight or enable terminal tools to fix a configuration error. Progressive tool disclosure is disabled for this small seven-tool profile so the local model can call diagnostic functions directly.

## Voice or automatic playback

The voice checkout defaults to `../JarvisLuxTTS`; the worker uses that checkout's `.venv/bin/python`, not the backend Python. The external checkout and environment are not rewritten. `npm test -- --tts-probe` checks original CPU initialization, and `npm test -- --speech` checks a real backend WAV when the reviewed QA browser is available.

An earlier diagnostic reported a misleading GenerationMixin import error because the helper `scripts/profile.py` shadowed Python's standard profile module. It was renamed to `scripts/prepare-profile.py` and a regression test now covers standard-profiler imports. Do not reinstall Transformers solely because of that historical error.

The CPU loader needs **openai/whisper-tiny** to transcribe its reference voice; its GPU path uses whisper-base. Having the latter cached does not satisfy the CPU path. `npm start -- --prepare-voice` downloads the missing CPU reference weights to the private project cache and reuses existing LuxTTS weights. Runtime is offline and never substitutes a different voice.

Automatic speech is enabled by default and migrates the previous manual-playback setting once. In Settings, check Enable voice output and Speak replies automatically. Later explicit opt-outs are preserved. The default speaking speed is 0.73; set JARVIS_TTS_SPEED between 0.4 and 1.2 in `.env` and restart to change it. Lower is slower. A browser may require an initial user interaction to allow audio; pairing and submitting a prompt normally provide it.

Stop speaking interrupts playback and active synthesis. A cancelled synthesis kills its worker; the next request reloads the voice. First initialization is consequently slower than resident synthesis. Locking any paired browser stops active app speech/chat for privacy, so avoid running multiple QA flows concurrently.

For lower speech latency, choose Settings → Voice output → Speech processing device → NVIDIA GPU. The choice is saved locally; no restart is needed for subsequent device switches. The first GPU load can take about 22 seconds on this machine. Preparation starts after pairing with voice enabled and during a new agent turn. Long replies play in phrases and prefetch one next phrase. Speech still waits for the agent's final verified reply, and CPU/model contention can increase delays.

GPU speech requires CUDA-enabled PyTorch and cached whisper-base in the voice environment. Existing cached weights are linked for reading; if absent, run `npm start -- --prepare-voice-gpu` explicitly. Low free VRAM, missing CUDA or allocator limits produce a visible voice error. Select CPU to leave more memory for the brain. Do not change Ollama's service configuration to work around speech errors. `npm test -- --tts-latency --device cuda` measures the real adapter with disposable audio; the CPU variant uses `--device cpu`.

## Microphone and STT

`npm start -- --prepare-stt` installs project-local NumPy/PyAV and verifies the official NVIDIA Parakeet v3 Q8_0 model plus NeMo-Speech.cpp 0.3.0 CPU runtime. It does not install NeMo or modify the JarvisLuxTTS environment. Runtime stays offline. Keep `JARVIS_STT_PROVIDER=parakeet`; an old Whisper directory in `JARVIS_STT_MODEL` must be removed or replaced with the Parakeet GGUF path shown in `.env.example`. `npm test -- --stt` tests real synthesis→recognition with temporary artifacts.

Parakeet's native C ABI version string includes the product name (`nemo-speech-asr 0.3.0`); the adapter validates its semantic version and the setup pins the exact release hash. Missing/incompatible libraries or weights produce a speech error while text chat remains usable. Re-run setup to verify cached asset hashes. Unexpected pre-existing runtime directories are not overwritten automatically; inspect them before moving aside or replacing them.

English wake/status and approval-number samples worked locally. A short rejection-number sample repeated digits, including with a fresh recognizer; an explicit comparison with Whisper recognized that audio correctly. Do not remove repeated digits automatically or relax confirmation matching. Correct the transcript or use the popup buttons. Parakeet lists 25 European languages, including English; Tagalog is not listed. Physical microphone quality and room noise require desktop testing.

Use the loopback browser URL, click the microphone and allow permission. Stop the recording to transcribe; transcripts remain editable by default. Denied permission or no detected speech leaves typed input available. Device labels may remain hidden until permission is granted. Output selection needs browser setSinkId support. Recording is limited to 60 seconds and never starts continuously in the background.

The synthetic-stream integration test exercises real MediaRecorder, real local STT, Hermes and the selected voice. It does not verify a physical microphone, speakers, room noise, or subjective voice quality; test these at the desktop.

## Resources and response quality

Use Low Power or reduced motion, close unnecessary browser tabs, keep speech on CPU, and request short summaries. Default status reports target three short sentences. Recognized live replies require relevant current-turn native tool results; unrelated or merely started tools cannot authorize measurements. Detailed system inventories are retrieved only when requested. Short output saves generation time; it does not shrink the fixed model/context allocation.

A measured 64000-context run used a 6.24 GB model footprint, including 3.77 GB VRAM, with 40%/60% CPU/GPU placement. Full two-tool replies previously took 30.5–45.2 seconds under different CPU loads. Whole-host swap usage was substantial during concurrent tests and cannot be attributed entirely to J.A.R.V.I.S. Do not promise frame rates or latency from these samples. The 4B model can misinterpret metrics; compare its summary with the live telemetry cards when accuracy matters.

## Desktop data and permissions

Launch from the active Hyprland session so HYPRLAND_INSTANCE_SIGNATURE, WAYLAND_DISPLAY, XDG_RUNTIME_DIR and the user bus are inherited. Review the optional environment import example in `systemd/hyprland.conf.example`; setup never modifies live configuration. Unavailable metrics are not zero readings or diagnoses of a broken driver.

User-service mutation names must be explicitly configured in JARVIS_APPROVED_USER_SERVICES. Every proposal requires its own expiring approval. Root/system service changes, arbitrary commands, configuration editing and process termination remain unavailable. Monitoring and telemetry routines are disabled until explicitly enabled/created.

## Browser QA and Git

Playwright is used because no Browser plugin is available. Some restricted environments need a temporary reviewed headless Chrome listener on **127.0.0.1:9223**: `npm test -- --browser --cdp --agent`. Voice and synthetic conversation tests also use this listener. Stop it after QA; it is not part of production startup. Software/headless WebGL is not a physical RTX performance benchmark.

The original root .git is read-only in this workspace. Milestone commits use `.runtime/project.git`: `bash scripts/git.sh status` and `bash scripts/git.sh log --oneline`. Tokens, private memories, transcripts, audio, weights and runtime logs remain ignored.
## Weather, currency, location and web search

In Settings → Location & internet, enable lookups, search for the city/town and
select Use this city. Save a valid IANA timezone such as Asia/Manila. These are
private application defaults; network interfaces and open applications cannot
establish your location or weather. A fresh checkout has no saved city.

If chat reports an outdated plugin, restart the project with `npm start -- --stop`
then `npm start`. The launcher updates only the dedicated reviewed plugin and
preserves a backup. Its toolset remains jarvis_desktop/no_mcp. Native general
search requires the optional `ddgs` package in the installed Hermes interpreter;
no package or paid provider is selected automatically. Rate limiting, missing
tickers and provider outages are reported as failures. Retry one clear question
in a new conversation if a small model selects the wrong tool. Date/time labels
distinguish forecast estimates, reference FX and last trades from live readings.

Run `.venv/bin/python scripts/information-check.py` for actual provider checks
and `.venv/bin/python scripts/online-agent-check.py` for fresh-session native
Hermes tool checks. Both need the running local services and enabled settings.
Private detailed reports are saved under .runtime, never committed.
