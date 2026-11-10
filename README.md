# J.A.R.V.I.S. — personal AI command center

A local browser assistant for Arch Linux and Hyprland. Hermes Agent runs the reasoning and tools; Ollama serves Qwen; JarvisLuxTTS supplies the voice. The React interface contains a procedural Three.js core that follows actual microphone and playback audio.

**Working integrations:** authenticated Hermes 0.22.6, Qwen at an allocated 64,000-token context, Linux telemetry, native Hermes memory, original JarvisLuxTTS CPU/CUDA synthesis, automatic browser speech, and audio-reactive WebGL. NVIDIA Parakeet v3 runs locally on CPU for speech-to-text. Detailed test evidence and remaining hardware checks are in [docs/PHASE_REPORT.md](docs/PHASE_REPORT.md).

## Run everything from one terminal

This machine's dependencies, dedicated profile and approved 64K model tag are prepared. From the project directory:

```sh
cd '/home/marneilx/new project marneilx/JARVIS'
npm start
```

The launcher starts the dedicated Hermes gateway and Python backend, serves the built frontend, opens **http://127.0.0.1:8787**, and prints the **local pairing token in that same terminal**. Paste it into the browser pairing screen once. No separate agent terminal or token command is required. Keep the launcher running; **Ctrl+C stops the processes it started**. Logs are private files under `.runtime/logs/`.

If you prefer to open the browser yourself:

```sh
npm start -- --no-browser
```

To stop recorded project processes from a later terminal:

```sh
npm start -- --stop
```

The stop command verifies process identity and workspace before signalling it. It does not stop your separate global Hermes installation, Ollama service, or other desktop services. If a verified project gateway is already running, startup can reuse it; a borrowed gateway remains running when the launcher exits. An occupied application port produces an explicit error.

## Everyday use

- Type an instruction and press **Enter**. Use **Shift+Enter** for another line.
- Completed replies **speak automatically**. Settings can disable voice or automatic speech; stop and replay remain available.
- Voice pace defaults to `0.73`, slightly slower than the original `0.8`. Set `JARVIS_TTS_SPEED` in `.env` for another pace; restart the launcher to apply it.
- Choose **Settings → Voice output → Speech processing device → CPU / NVIDIA GPU**. The device choice is saved on this machine and shared by paired browsers. Switching stops speech and prepares the selected device when voice is enabled. Use **Test voice** and **Stop voice** to check it. The original voice and pace are preserved.
- With voice enabled, the model prepares after pairing and while Hermes works. Long final replies play in bounded phrases, with one next phrase generated during playback. Only completed, verified replies are spoken.
- Hold the microphone button, or focus it and hold **Space/Enter**, then release to transcribe and send. Permission is requested only on interaction. Disable automatic submission in Settings to edit first.
- A system report normally uses **two or three short sentences**, with requested readings and verified warnings. Ask for a detailed report when needed.
- System shows measured resources, services and Hyprland applications. Memory reviews proposed preferences and supports editing, deletion and pinning. Settings contains graphics, device, voice and optional monitoring controls.
- **Shortcuts** lets you create an alarm, a battery warning, or a daily weather briefing. Choose a template or set the trigger, time, timezone, message, chime, weather and delivery; review the exact summary and select the authorization checkbox before saving. Nothing is scheduled from an example or chat suggestion alone. An alarm can run once or on selected weekdays. Battery shortcuts use measured battery state while discharging, require the threshold to stay crossed for ten seconds, and re-arm only after charging or recovering five percentage points above the threshold.
- Shortcuts use the selected JarvisLuxTTS voice. **Auto delivery** uses an available paired browser and otherwise speaks through the desktop's PipeWire speakers; desktop delivery also works with the browser closed. The Jarvis backend must still be running, the computer must be awake, and PipeWire output must be available. These are software alarms, not firmware alarms: they do not wake a suspended or powered-off laptop. A seven o'clock briefing can read the saved city's current weather only when the saved location and internet-lookup permission are available. Review outcomes and failures in **Shortcuts → Run history**; disable or delete a shortcut to cancel its queued runs.
- CPU and GPU temperatures appear side by side in System Overview and System. CPU readings use a recognized CPU package/core sensor; unrelated ACPI or drive temperatures are not substituted.

The core's waveform and frequency bars use real Web Audio analyser samples. Core brightness and size also follow measured amplitude. Silence does not generate invented speech pulses. Reduced motion, capped graphics presets, hidden-tab pausing and a 2D WebGL fallback are supported.

## Immersive Jarvis, maps and welcome audio

Click **Enter immersive mode** in the top bar. This opens the fullscreen core and
starts hands-free local listening after browser microphone permission. If native
fullscreen is unavailable, the same layout fills the page. The main dashboards
are hidden. The faint bottom controls become clearer on hover/focus:

- **Always listening / Wake phrase** switches the immersive microphone mode and
  saves your choice in this browser. Always listening sends each complete phrase.
  Wake phrase accepts “Jarvis, …” or “Hey Jarvis, …”; saying only the name opens a
  five-second window to start your next command. Silence returns to wake-only
  mode; speech started in time can finish within the normal recording limit.
  Empty/noise transcripts return to wake-only mode without submitting a command.
  After the command, timeout, or hiding the page, it waits for another wake call.
  This choice is also in **Settings → Immersive microphone mode**.
- **Mic on / Muted** releases/enables capture in either mode. Wake mode still uses
  the microphone and local STT to detect your call; unrelated speech is not sent
  to the agent. The existing exact local mute commands remain available. Recordings
  are bounded and held in memory only; always-listening clips allow up to 60 seconds.
- Rounded cyan/blue/violet edge lighting appears **only after a wake call**, then
  fades out. It stays hidden while waiting and does not continuously frame the
  screen. Reduced motion removes the pulse; background tabs stop the effect.
- Capture pauses during generation, transcription and audio playback, then resumes
  after a 900 ms speaker-tail delay. This is half-duplex conversation: use **Stop**
  to interrupt playback, then speak. It does not transcribe over Jarvis's own voice.
- **Chat / Hide chat** expands or minimizes the existing conversation and composer;
  drafts, history, ongoing replies and playback are preserved. **Exit** or **Esc**
  returns to the dashboard. Exiting ends immersive capture and restores your
  separately configured Hey Jarvis preference. Hidden tabs release immersive
  capture; this mode is not a desktop background microphone service.
- Expanded chat has a fixed viewport height, scrolls messages inside the panel and
  keeps the input above the controls. Scrolling back pauses automatic following;
  a newly submitted prompt returns to the latest reply. Wide screens reserve a
  separate column for chat and recenter the existing core in the remaining space.
- **Permissions** opens pending reviews. The normal popup and exact spoken/typed
  review codes remain enforced; hands-free listening grants no new permissions.

The same R3F canvas, waveform, FFT bars and audio bus remain mounted across view
changes. A new procedural node-and-link sphere adds depth; particles, rings and
core respond to real microphone/playback samples. Graphics retain preset FPS/DPR
limits, a roughly 1.8-million-pixel render budget, reduced-motion and WebGL fallback.
Hidden application panels and background tabs pause the scene.

With **Settings → Location & internet → Enable internet information lookups** on,
ask **“Show Mactan Cebu International Airport Philippines on the map.”** Hermes's
reviewed `jarvis_online` tool returns verified place data and opens the map. Or
click **Map** and search manually. Drag to pan, use the zoom buttons/wheel, and
choose **Back to core** to dismiss it. The small live core remains visible on the
map in immersive mode. Confirmed selections/routes survive closing and reopening
until their 30-minute receipt expires or the backend restarts.

The default map is now a tilted, dark-cyan MapLibre WebGL scene with real roads,
place labels and building heights where supplied. A verified destination starts
a roughly 6.5-second camera flight with a gentle tilt and rotation. While a native
lookup is pending, a scanning indicator accompanies a slow camera adjustment;
it does not imply a location has been found. Dragging interrupts the flight.
Reduced motion uses an immediate view change; hiding the tab stops animation and
returning resumes the destination approach. **Switch to 2D map** provides the
lighter Leaflet view; WebGL initialization failure selects it automatically.

Ask **“Give me directions from Mandaue City, Philippines to Mactan Cebu
International Airport, Philippines.”** Multiple matches require a selection. If
no starting point is supplied, you must confirm the saved city centre or enter a
more useful starting place. A saved city is not GPS tracking. OSRM provides the
road route, distance and estimated driving time, **without live traffic or
turn-by-turn navigation**. Routes and locations are not invented when a provider
fails. Place searches/coordinates go to Nominatim and OSRM; visible map tiles load
from OpenFreeMap in 3D or OpenStreetMap in 2D. These are public, best-effort services, not hosted inference.
No API key is needed. Attribution stays visible; there is no bulk tile download,
autocomplete geocoding or periodic location search. See the
[OSM tile policy](https://operations.osmfoundation.org/policies/tiles/),
[Nominatim policy](https://operations.osmfoundation.org/policies/nominatim/) and
[OSRM interface](https://project-osrm.org/docs/v5.24.0/api/).

`welcome_back_jarvis.mp3` in the project root is served through an authenticated
fixed audio endpoint and plays once after pairing on each page opening/reload.
It shares the voice player and analyser, so it animates the core and cannot overlap
with a new assistant response. When the browser blocks autoplay, click **Play
welcome sound** or **Skip**. Use **Settings → Voice output → Enable boot-up sound**
to turn it off. This saved choice is independent of spoken replies. The supplied media remains a local file, not a bundled dependency;
copy your own file to that exact project-root filename on another installation.
`reference.mp4` was inspected for the visual direction and is not played by the UI.

**Enable processing sound** in the same Settings panel controls the 0:01.0–0:01.7
segment of your `5 data readout sound effect .mp3`, looped locally without the quiet opening. It plays during thinking,
tool execution and speech preparation, then stops before reply playback. It also
stops on cancellation, errors, page hiding and session lock. It follows playback
volume and the selected output where Web Audio supports device selection; other
browsers use their default output. It never drives the speech analyser or loads
another AI model. Browser autoplay rules can require a click first. The original
file is unchanged; the extracted WAV stays outside Git in `.runtime/assets`.
To recreate it on another installation, from the project folder run:

```sh
mkdir -p .runtime/assets
ffmpeg -i '5 data readout sound effect .mp3' -af 'atrim=start=1:end=1.7,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.005,afade=t=out:st=0.695:d=0.005' -c:a pcm_s16le .runtime/assets/processing-readout.wav
```

If `JARVIS_STATE_DIR` is customized, use its `assets` directory instead. The
authenticated backend serves this fixed clip; it is decoded once per open page
and looped with Web Audio without MP3 encoder padding between repeats. Missing
audio stays silent; no synthesized replacement is selected. Five-millisecond
edge fades soften the loop join without inserting a pause.

Jarvis has local voice/microphone commands. Type them, hold the microphone to
say them, or use the enabled wake listener. These exact audio commands also work
without saying Jarvis first while that listener is active:

| Command | Effect inside Jarvis |
| --- | --- |
| `mute` / `mute voice` | Stop current speech and disable spoken replies. |
| `unmute` / `unmute voice` | Enable spoken replies again. |
| `mute mic` / `mute microphone` | Release all Jarvis microphone capture, including wake and immersive listening. |
| `unmute mic` / `unmute microphone` | Allow capture again; previously enabled listening modes can resume. |

These commands run locally without an AI turn or system-volume operation.
Microphone mute leaves reply playback running; voice mute leaves microphone
permission and the selected input/output devices unchanged. Both choices persist
in this browser. Use **Unmute Jarvis microphone**, Settings → **Mute Jarvis
microphone**, or typed `unmute microphone` to restore a muted microphone: it cannot
hear an unmute command while off. Spoken commands use the existing half-duplex
listener; capture pauses during reply playback. Hold the mic to interrupt speech
and give a command, or type it while speech is playing. Boot/processing sound
toggles remain independent of voice mute.

Both **“Hey Jarvis”** and a leading **“Jarvis”** wake phrase trigger the optional
listener and briefly illuminate the screen edges. Detection occurs after local
phrase transcription, not instant neural wake-word detection. A wake phrase alone
gets a short acknowledgement. Enable listening in Settings; it is off by default.

Use **News & markets** to search public news headlines or a stock ticker, or ask
Jarvis for news or a stock quote. Successful native tool receipts open the same
view. News cards show the publisher, date and source link; selecting a card shows
headline details, **not the full article text**. Open the source to read the article.
Stock charts use timestamped samples from the provider's current chart response;
missing samples show an unavailable state. Quotes can be delayed and are not a
trading service. The saved internet-lookup permission controls both views.

The conversation scrolls inside its own panel so long replies cannot push the
core downward. Settings uses independently flowing columns on wide screens and
one column on smaller screens.

After updating source, rebuild with `npm run build`, then restart using
`npm start -- --stop` followed by `npm start`. Refresh the browser to load changes.

## Memory, background listening and home access

Say “Remember that I prefer …”. Jarvis prepares a compact native memory change
and the permission popup shows the exact content. **Approve once** writes it;
only then does the UI say it was saved and refresh Saved knowledge. Names and
addressing preferences belong in `USER.md`; technical knowledge belongs in
`MEMORY.md`. A pending/rejected proposal is never a confirmed save. Invalid tool
arguments are reported, repeated pending facts reuse the original review, and
old conversations cannot reconstruct deleted knowledge. The separate `SOUL.md`
keeps the assistant's identity as Jarvis. Start a new conversation after a save.

In Settings → Microphone & devices, enable **Hey Jarvis** and optionally **Keep
listening when this browser is in the background**. The second setting is an
explicit microphone opt-in; existing profiles leave it off. It can keep capture
active while another app/tab is focused, but browsers may throttle or suspend
hidden pages. Keep the page open. Locking, disabling wake, page closing/freezing,
manual capture and assistant speech still stop or pause it. This is not an
always-running desktop wake daemon. Graphics still pause in hidden tabs.

System → **Installed applications** searches actual desktop entries. Jarvis can
request launches by name through Hermes. Approval is required by default; the
**Settings → Desktop & terminal permissions** checkbox controls whether installed
apps and exact saved terminal commands can launch without repeated confirmation.
The backend uses fixed `gio launch` arguments, revalidates desktop fingerprints
and strips agent credentials from child environments.

For Kitty, say **“Open Kitty and run fastfetch.”** The installed fastfetch, btop,
htop and nvtop commands are offered on a new installation when available.
Approve the popup, or uncheck **Ask before opening apps or running saved terminal
commands** to preauthorize these launches. Existing pending requests still need
approval. Memory edits, services and other desktop actions keep their approvals.

Add other commands in the same Settings panel: give an exact command a name,
optionally set a home-relative working folder, then click **Save terminal
command**. For example, save `git status --short` as “Project status” with your
project folder, then ask Jarvis to run “Project status.” **Run in Kitty** also
works without inference. Commands run directly, with quoted arguments; shell
operators, variables, shell wrappers and privilege escalation are refused. Jarvis
selects saved IDs and cannot invent arguments or edit this permission setting.
Kitty stays open after the command exits. A successful launch receipt means Kitty
accepted the request, not that the command finished successfully.

These exact, browser-authored commands run as your normal account; they are not
an OS sandbox and can read/write files according to that account's permissions.
Only save commands you trust. The working folder stays inside home; the separate
home-file tools retain their stricter read-only boundary. Saved commands and the
approval choice persist privately in `.runtime/desktop.db`, not `.env`. Removing
a command revokes its old proposals even if an identical command is saved later.

System → **Home files** browses folders, searches filenames and previews UTF-8
text. Paths are relative to your account home, for example `Documents`. Hermes
has the same bounded read-only tools. File editing/deletion, absolute/outside-home
paths, symlinks, hidden/credential files, special files, hardlinks and cross-device
paths are unavailable. Scans and previews have limits; narrow a folder when
results are truncated. Common credential forms are redacted; do not assume every
secret copied into an ordinary document can be detected.

Web conversations that use home-file tools are marked private on the server.
The agent cannot perform internet lookups in that conversation afterward; start
a fresh conversation for online work. This prevents file text/names from becoming
outbound search queries. The file tools grant no root or filesystem write access.

This checkout now has a private, populated `.env` with local ports/endpoints,
speech paths, resource defaults and reused credentials. `npm start` loads it.
Permissions are `600` and Git ignores it. Location/timezone, selected brain and
saved speech-device choice stay in private application settings; browser wake
consent stays in browser preferences. Installed Hermes paths are discovered on
each launch. `npm start` still prints the pairing token from `.runtime/login.token`
in its own terminal. Never put server credentials in frontend `VITE_*` settings.

## How the components work

```text
Browser: React + TypeScript + Vite + R3F/Drei/Postprocessing
  ├─ text / recorded microphone → authenticated FastAPI backend
  ├─ live telemetry / reviewed actions / memory panels
  └─ browser WAV playback → Web Audio analyser → 3D core

Backend → authenticated Hermes API → local Ollama / Qwen
        → resident local Parakeet v3 CPU transcription
        → original JarvisLuxTTS CPU/CUDA worker → short-lived WAV

Hermes → reviewed native jarvis_desktop plugin → backend Linux diagnostics
       → native SOUL.md and USER.md / MEMORY.md
```

Hermes owns conversation history and tool execution. The backend sends only the next user turn and the native session ID; it does not feed duplicate transcripts back into the model. The browser never receives the Hermes bearer token or calls Ollama directly.

The launchers discover your installed Hermes source and its current committed Python environment. They reuse it without reinstalling dependencies or changing global identity. Hermes' lazy dependency synchronization is disabled for this shared interpreter. **J.A.R.V.I.S. uses `hermes/runtime/SOUL.md`**, because its `HERMES_HOME` is the dedicated project directory. The version-controlled template is [hermes/SOUL.md](hermes/SOUL.md). A plain global `hermes` command uses your separate global profile; use `bash scripts/hermes.sh cli` for the J.A.R.V.I.S. CLI identity and memory.

The web runtime exposes only the reviewed desktop plugin and `no_mcp`. It can inspect the machine and propose changes. A proposal cannot approve itself: the backend requires an exact, expiring, one-use browser approval. User-service mutations require an explicit service allowlist. Root shell, arbitrary commands and public access are unavailable.

Native memory stays in Hermes' USER.md and MEMORY.md. The application stores review metadata rather than a duplicate memory corpus. Changes retire obsolete chat contexts. Deleting memory does not erase old native transcripts or disk backups; those are never used by this app to recreate deleted knowledge.

The actual native files are `hermes/runtime/SOUL.md`, `hermes/runtime/memories/USER.md`, and `hermes/runtime/memories/MEMORY.md`. Its conversational name is **Jarvis**. Review suggested changes in **Memory**; proposals become saved memories only after approval. `npm start -- --prepare-memory` can prepare empty files and queue private candidates idempotently. It never silently saves them or restores deleted candidates. See [the native profile guide](hermes/README.md).

Hold the microphone button while speaking, then release it to transcribe and send. A focused microphone button also supports holding Space or Enter. Releasing before permission arrives discards the capture; leaving the tab or losing focus cancels it. **Settings → Submit recognized speech automatically** can be disabled to edit the transcript before sending. Both the main microphone and approval popup use this gesture. Approval speech must still match the displayed command and code exactly.

## Internet information and location defaults

Open **Settings → Location & internet** to enable outbound information lookups,
search for a city/town, select **Use this city**, and choose an IANA timezone such
as `Asia/Manila`. The header clock uses this timezone. City/timezone are saved
privately on this computer in `.runtime/online-settings.json`, shared with the
dedicated Hermes plugin. New checkouts start with internet disabled and no city;
your existing approved defaults are preserved. No GPS tracking is used.

Ask Jarvis “What's my location?”, “What's the weather like today?”, “What's the
current USD/PHP exchange rate?”, “What is the NVDA stock price?”, “Find news
headlines about the Philippines”, or “Search the web for …”. These calls still
run through Hermes and the selected local brain. The reviewed plugin wraps the
installed Hermes **DDGS** provider explicitly, so paid-provider autodetection is
not used. It requires `ddgs` in the existing Hermes environment; missing support
returns an error rather than installing packages or changing providers.

Weather comes from [Open-Meteo](https://open-meteo.com/en/docs), a dated model
estimate for the configured city. Currency conversions use
[Frankfurter](https://frankfurter.dev/) daily reference rates; they are not
intraday bank/cash quotes. Stocks use Yahoo Finance's unofficial read endpoint
and report the last regular-market trade timestamp; availability/delays vary.
News is bounded Google News RSS headlines, with publisher links and publication
dates. General search returns source-linked snippets, not full-page research.
Neither headlines nor snippets prove that the article/page has been read.

Queries or city coordinates go to these public information providers. Inference,
speech, identity and memory stay local. Lookups run on request with bounded
in-memory caching; they do not trigger continuous model inference. Disabling
lookups blocks new provider requests. Settings changes invalidate old results,
including queued/in-flight weather responses. Local time and saved-city queries
remain available offline. Missing/unrelated tool results cannot become a weather
or currency answer; start a fresh conversation and retry if the brain chooses
the wrong tool. Safe source links are visible in chat and survive refresh.

## First-time installation on another checkout

Prerequisites: Linux, Git, Node.js 22+, npm, uv, Python 3.14, Ollama, and the NVIDIA driver. `hyprctl`, `wpctl`, `systemctl` and `journalctl` enable desktop readings. Start from a shell inside your active Hyprland session.

```sh
bash scripts/setup.sh
python3 scripts/runtime.py
```

The second command reports the installed Hermes source/interpreter/version. If Hermes is absent, review and run `bash scripts/install-hermes.sh` to install the pinned official source into this project. No remote shell installer or sudo is used. Existing managed and conventional Hermes environments are supported; explicit `HERMES_SOURCE` and `HERMES_PYTHON` overrides must be supplied together.

Discover your real model tag, then prepare a fresh dedicated profile:

```sh
ollama list
python3 scripts/prepare-profile.py --model 'YOUR_INSTALLED_QWEN_TAG'
```

The helper refuses to overwrite an existing nonempty profile. It replaces the old `scripts/profile.py` name, which collided with Python's standard profiler module.

**Context setup requires explicit approval:** Ollama 0.30.0 ignores per-request `options.num_ctx` on `/v1/chat/completions`. A Hermes context pin alone does not allocate the requested window. The approved setup on this machine uses [hermes/Ollama.Modelfile](hermes/Ollama.Modelfile):

```text
FROM hf.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive:Q4_K_M
PARAMETER num_ctx 64000
```

After reviewing the exact source tag and approving a separate persistent alias:

```sh
npm start -- --configure-model
```

This creates `jarvis-qwen35-4b-64k:latest` using existing layers, backs up and updates only the dedicated Hermes config, and leaves the original model tag intact. It does not modify Ollama's systemd configuration. Do not run it with an unrelated Modelfile or before the base model is installed. Startup/chat preflight requires an explicit local model default of at least 64,000 tokens; the real agent check verifies the loaded allocation too. See [Ollama's context documentation](https://docs.ollama.com/api/openai-compatibility#setting-the-local-context-size).

For speech, the default original checkout is the sibling `../JarvisLuxTTS`, with its own `.venv`. CPU synthesis needs cached LuxTTS/ONNX assets and **openai/whisper-tiny** for the voice reference, even when whisper-base is already installed for its GPU path.

```sh
npm start -- --prepare-voice
npm start -- --prepare-stt
npm run build
npm start
```

Voice preparation reuses cached LuxTTS weights and downloads only the missing reference model into `.runtime/speech-models/hub`. It leaves the external voice repository and environment unchanged. STT preparation installs NumPy/PyAV in the project `.venv`, verifies NVIDIA's official NeMo-Speech.cpp 0.3.0 CPU package and downloads the official 714 MB Q8_0 Parakeet v3 GGUF. Both downloads are pinned by version/revision, size and SHA256. No remote installation script, system package, NeMo/PyTorch stack or global PATH change is needed. These setup commands download model files; runtime transcription and synthesis are local and offline.

Speech recognition uses [NVIDIA Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3), by NVIDIA, licensed CC BY 4.0. The model supports 25 European languages including English; Tagalog is not listed. Input containers are decoded to bounded 16 kHz mono audio in memory. A single isolated CPU recognizer is reused for microphone input, wake phrases and spoken confirmations. Browser disconnects and session locking cancel active recognition; recordings are never saved. STT uses CPU so the 6 GB GPU remains available for the brain and selected TTS device.

Local synthetic speech tests measured about **0.7 s** for the first 3.4-second clip and **0.27–0.34 s** for short warm clips, with **757–774 MiB** worker RAM. These are sample timings, not accuracy or latency guarantees. One spoken rejection-number sample produced repeated digits, including with a fresh recognizer; the same clip was correct with the older Whisper provider. Transcripts remain editable, and malformed confirmation codes are rejected. Use popup buttons when recognition is uncertain.

The default is `JARVIS_STT_PROVIDER=parakeet`. If an older `.env` sets a Whisper directory in `JARVIS_STT_MODEL`, remove that override or point it to `.runtime/models/parakeet-tdt-0.6b-v3/parakeet-tdt-0.6b-v3.q8_0.gguf`. The existing Whisper assets are preserved. To explicitly select that already-installed alternative, set `JARVIS_STT_PROVIDER=faster-whisper` and its corresponding model directory, then restart. The application never falls back to another STT model automatically.

CUDA speech requires a CUDA-capable PyTorch installation in the existing voice environment and its cached `openai/whisper-base` reference model. The adapter reuses that cache when present. If it is missing, explicitly prepare it with `npm start -- --prepare-voice-gpu`, then choose NVIDIA GPU in Settings. This setup command downloads weights into the project cache; ordinary speech never downloads anything.

CPU is the initial default; `JARVIS_TTS_DEVICE=cpu` or `cuda` sets the initial device before a browser choice is saved. Settings takes precedence afterwards. GPU loading requires at least 2 GiB free VRAM and limits the PyTorch allocator to 25% of the GPU; CUDA context/library overhead also uses memory. If another AI model fills VRAM, choose CPU. A GPU error leaves text available and does not select another voice.

On this RTX 4050, with the 64K Qwen 2B Q4 model resident, the original GPU path synthesized a 73-character sample in **1.00 s** and a 245-character sample in **1.27 s**, versus **3.00 s / 6.43 s** on warm CPU. Total GPU use during that test was **4185 / 6141 MiB**, leaving **1669 MiB** free. GPU cold initialization took **21.56 s**; CPU preparation took **9.13 s**. Preparation moves this work earlier; it does not make a cold model instantaneous. These are samples under that workload, not guarantees for other brains.

## Configuration and development

Copy `.env.example` to `.env` only when changing defaults. It is a trusted local shell environment file; do not paste untrusted code into it. API secrets and generated audio remain ignored by Git. The dedicated profile must not be redirected to a global home or symlinked identity/memory.

### Changing the brain

For downloaded GGUF files, use the standalone
[GGUF installer](scripts/gguf-installer/README.md). The bundle can be copied to
`../ollama stuff/`; it accepts a file or directory and creates separate J.A.R.V.I.S.
64K tags. The [four installed download variants](scripts/gguf-installer/INSTALLED_MODELS.md)
are available after **Refresh models**; importing them does not switch the brain.

Open **Settings → Brain · local model**. Select an installed Ollama model, then
choose **Use this model**. If its default context is too small, **Prepare 64K tag
and use model** explicitly creates a separate local alias sharing its existing
weights. The original tag and Ollama service settings are preserved. The selector
does not download models or offer hosted providers. Models without advertised
tool support or a 64,000-token context limit are refused.

Switching starts a new conversation and retires existing application sessions.
The selection persists privately in `.runtime/model-selection.json`; Hermes still
owns reasoning, tools, SOUL.md and native memory. The browser never calls Ollama.
This is an application selection through Hermes' supported `model`/`provider`
request fields; a separate CLI invocation keeps its profile's configured default.
Metadata checks do not prove hardware performance.

The requested installed Gemma Q4_K_M is now selected through its separate 64K tag.
A real two-tool Hermes run verified the allocated context and CPU/GPU placement;
see [measured results](docs/PHASE_REPORT.md). You can select the existing prepared
Qwen tag again from the same menu.

### Permission popups and spoken confirmation

Pending desktop operations and native memory changes open a popup showing the
exact target, effect or memory diff, rationale, expiry and a short code. Use
**Approve once**, **Reject**, or **Review later**. The header's **Review permissions**
button reopens deferred requests.

Installed apps and saved terminal commands can instead use the explicit desktop
preauthorization setting above. The agent cannot enable it. All other action and
memory proposals continue through this popup.

For keyboard confirmation, enter `approve 4281` or `reject 4281`, using the code
currently displayed. For speech, hold **Hold to speak confirmation**, say the same command, then release
(digits may be spoken individually). A valid
confirmation is handled directly by the authenticated application, never by the
language model. With automatic voice enabled, Jarvis reads each displayed request
once when the current reply has finished. **Read request aloud** repeats it and
**Stop voice** interrupts it. A general “yes” does not
approve anything. Review codes expire after at most two minutes and belong to
one proposal and one paired browser. Existing backend allowlists and one-use
approval checks still apply. Memory changes require a fresh conversation.

### “Hey Jarvis” mode

Enable **Settings → Microphone & devices → Enable “Hey Jarvis” listening** and
allow microphone access. Say **“Hey Jarvis, are you there?”**, or follow the name
with an instruction. The command goes through Hermes and replies use the normal
automatic JarvisLuxTTS pipeline. “Hey Jarvis” alone plays “At your service, sir.” without an inference request or a fabricated conversation turn.
To confirm a visible request hands-free, say **“Hey Jarvis, approve 4281”** with
its current code.

This mode is off by default. While enabled, a visible indicator shows listening,
transcription or pause. Voice activity detection drops silence; bounded speech
clips are transcribed by the selected local CPU Parakeet service and discarded.
Capture stops during transcription, assistant replies, manual recording, locking
and hidden tabs. Turning the setting off releases the microphone. It is phrase
transcription rather than a dedicated instant wake detector: recognition can be
delayed or inaccurate, and speech during transcription is not heard. Voice
confirmation recognizes words; it does not authenticate a speaker. Keep this mode
off around untrusted audio. No cloud speech recognition is used.

```sh
npm run dev
```

Development uses the same single supervisor with Vite on **127.0.0.1:3000**, proxying `/api` to the backend. Production serves both on **127.0.0.1:8787**. Hermes defaults to **8642**, Ollama to **11434**. Application/frontend ports are configurable; match Hermes' configured port to `HERMES_API_URL` when changing it. No service is made public. Optional systemd and Hyprland examples are provided but are not installed or enabled automatically.

After changing the backend port, restart the dedicated gateway too, so its plugin inherits the matching JARVIS_BACKEND_URL. The supervisor's stop command verifies process generation, full invocation, working directory and dedicated home before signalling through a Linux pidfd.

## Verification and practical limits

```sh
npm test
npm run build
npm test -- --agent
npm test -- --memory
npm test -- --hardware
npm test -- --stt
npm test -- --tts-latency --device cpu
npm test -- --tts-latency --device cuda
npm test -- --browser --agent
```

With the reviewed temporary loopback QA browser running, `npm test -- --interactions --speech-latency` uses a private backend to check CPU/GPU switching, persistence, real automatic GPU speech, bounded prefetch, Web Audio analysis, replay and stop. It preserves the main application's speech device and proposals. This does not verify physical speakers or subjective voice quality.

`npm test -- --interactions --parakeet` uses real MediaRecorder with synthetic JarvisLuxTTS speech, Parakeet transcription, editable text, Hermes replies, automatic TTS and wake phrases in an isolated QA backend. `npm test -- --stt --compare` explicitly compares the same synthetic clips with the installed Whisper provider for diagnosis; this does not change the app's provider. Neither test verifies a physical microphone or real-room accuracy.

`npm test -- --interactions --voice-controls` verifies hold/release submission,
late-permission/blur cancellation, held-through-limit completion and approval
recording with real Parakeet. Its 60-second timer is advanced by Playwright;
recorded audio and transcription remain real. `--interactions --greetings` checks
brief greetings/name answers through Hermes and after refresh.
`--interactions --information` checks private QA timezone persistence, real city
search, disabling lookups and a source-linked native Hermes FX answer. QA desktop
mutations are blocked by an isolated executor. These commands require the
reviewed temporary CDP browser described below.

`npm test -- --interactions --terminal` verifies default review, rejection,
browser-only preauthorization persistence, real backend policy, saved command
creation/removal and failed-launch reporting with desktop execution blocked.
`bash -c 'source scripts/common.sh; .venv/bin/python scripts/terminal-agent-check.py'`
checks the original fastfetch prompt through real Hermes tools, then rejects only
its own pending proposals. It never changes policy. With preauthorized launches
enabled, it refuses to run unless you explicitly append `--allow-launch`; that
mode can open Kitty and run the saved fastfetch command.

For direct provider/agent diagnostics, run:

```sh
.venv/bin/python scripts/information-check.py
.venv/bin/python scripts/online-agent-check.py
```

The first uses real information providers. The second exercises native Hermes
calls, including a combined weather/FX turn. Detailed results stay in `.runtime`.

Additional reviewed QA commands:

```sh
npm test -- --interactions --memory-ui
npm test -- --interactions --home-access
npm test -- --interactions --background-wake
.venv/bin/python scripts/access-agent-check.py
```

The first three need the temporary loopback QA Chrome/CDP listener. Memory UI
uses an isolated native profile, home/app UI uses real discovery with mutations
disabled, and background wake uses synthetic microphone speech plus simulated
page visibility. The agent check uses the real running application/Hermes, reads
home metadata, verifies outbound refusal and rejects its own launch proposals
without launching an app. It does not prove an approved GUI launch or physical
microphone/minimized-window behavior.

`--agent` performs a genuine two-tool request through the application and checks actual 64K allocation. `--memory` exercises the installed native memory functions in a disposable profile. Browser QA uses Playwright; provider mocks are not evidence of hardware compatibility.

For reviewed QA with a temporary loopback Chrome/CDP listener on 9223:

```sh
npm test -- --browser --cdp --agent
npm test -- --voice-browser
npm test -- --conversation
node scripts/views-browser-check.mjs
node scripts/processing-browser-check.mjs
node scripts/audio-controls-browser-check.mjs
node scripts/immersive-modes-browser-check.mjs
```

The conversation test records real synthesized speech through a synthetic microphone stream and exercises STT → editable transcript → Hermes → automatic JarvisLuxTTS playback. It does not prove a physical microphone or speakers work. Stop the temporary QA browser afterwards; CDP is not part of normal startup.

The views check uses live map/news/stock providers and a simulated wake transcript
to verify rendering and layout. The processing check plays the actual local loop
clip but uses chat/TTS fixtures to check cancellation and silence before playback;
it does not validate a speech model or physical speakers.
The audio-controls check uses simulated capture/transcripts and speech to verify
independent voice/mic mute, delayed-reply handling, persistence and capture release.
The immersive-modes check uses simulated VAD/STT/chat to verify both modes, the
wake timeout, conditional edge lighting and a scrollable 90-paragraph conversation
at desktop and phone sizes. It does not establish physical wake-word accuracy.

Measured 64K model footprint: about **6.24 GB**, including **3.77 GB VRAM**, with **40%/60% CPU/GPU** placement on the RTX 4050 6 GB. Earlier full two-tool turns took 30.5 seconds, increasing to 45.2 seconds during concurrent CPU speech work. These are measurements, not latency guarantees. Short replies reduce generated tokens; they do not remove the model/context allocation. Headless WebGL tests do not establish physical GPU frame rates. Treat live telemetry cards as the authoritative readings: a small model can still misstate or overinterpret tool output.

See [architecture](docs/ARCHITECTURE.md), [security](docs/SECURITY.md), [troubleshooting](docs/TROUBLESHOOTING.md), and [phase evidence](docs/PHASE_REPORT.md). Local milestone commits use `bash scripts/git.sh` because this workspace's original `.git` mount is read-only. No unavailable starter project is claimed to have been migrated.

Additional checks with the reviewed temporary Chrome listener running:

```bash
npm test -- --interactions          # model selector and typed popup rejection
npm test -- --interactions --voice  # real TTS/STT, spoken rejection and wake phrase
npm test -- --firefox-chat --zen --motion --skip-wire --voice-on-only
```

The interaction check uses a temporary backend, private pairing token and review
database on a random loopback port; its proposals never appear in the ordinary
application session. It uses the already installed Gemma model and can create its
separate alias if needed; run it only when that change is wanted. It rejects its
desktop proposals without execution. Voice input is synthetic;
the providers and browser recording/playback are real. The Zen check requires an
installed Zen binary and geckodriver and uses its own temporary browser profile.
