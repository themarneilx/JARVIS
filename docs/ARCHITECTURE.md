# Runtime architecture

The authenticated model selector enumerates installed tags through a separate
server-side Ollama client. Selection is private application state, sent to Hermes
using its supported explicit `model` and `provider: custom` fields. Global Hermes
configuration and the API toolset are preserved. Preparation creates a separate
64K alias sharing local weights. Switching retires all application conversations;
native session model precedence cannot silently reuse an old selection. Model
metadata is explicitly distinguished from measured runtime compatibility.

Browser-owned review tickets bind a short spoken/typed code to the exact pending
desktop action or memory diff. Their snapshots, browser ownership, expiry and
one-use consumption are checked server-side. Cheap proposal polling reads review
metadata only; it never loads the model or native memory subprocess. The popup's
explicit commands are parsed on human input paths before ordinary chat; model
output cannot enter this confirmation parser.

An opt-in wake listener uses a private Web Audio analyser for VAD and bounded
MediaRecorder clips. CPU STT detects a leading “Hey Jarvis”, then submits the
remaining command to the normal application path. Capture is released during
transcription and foreground activity. Hidden tabs release wake capture unless
the separate backgroundWake browser preference was explicitly enabled. Page
freezing/closing and suspended Web Audio still stop it; browser throttling means
there is no always-on guarantee. Wake and manual capture reject
late permission/recorder callbacks after cancellation. This has transcription
latency and is not a dedicated wake-word neural engine.

Chat responses send SSE comment heartbeats every two seconds during quiet gaps.
One producer owns upstream contexts and a one-item queue bounds buffering; ready
events are forwarded immediately. The pending read survives heartbeat intervals; closing the browser stream
cancels and closes it. Comments carry no invented model activity or progress.

React/Vite communicates only with `/api` on the application origin. Production FastAPI serves the built frontend on 127.0.0.1:8787; Vite development runs on loopback port 3000 and proxies `/api`. Hermes remains the only reasoning/tool loop. The backend sends the latest user message with `X-Hermes-Session-Id`, and Hermes owns the transcript and tool results. A backend SQLite table holds only session IDs, birth memory epochs and retirement flags. Display history is retrieved from Hermes; it is never fed back into the prompt a second time.

Hermes native `register(ctx)` plugin tools retrieve backend telemetry, read bounded logs/process information, propose actions, read native memory, and propose memory changes. The plugin bearer credential cannot resolve approvals, synthesize speech, or authenticate a browser. Neither arbitrary shell nor general filesystem tools are exposed. Explicit `no_mcp` prevents Hermes auto-enabling globally configured MCP servers. Before chat, the backend checks both the dedicated profile and the authenticated `/v1/toolsets` surface. Unknown or broad configurations fail closed.

The installed Hermes 0.22.6 (commit f0d94882e89ab8d4098b5bb2f166adfb9ee0a0ab) supports authenticated Chat Completions, named tool-progress events, session continuation, runs and cancellation. Its discovery endpoint returns `{object:"list",data:[...]}`. A streaming completion's `chatcmpl-*` identifier is also its run identifier. Only `finish_reason=stop` counts as a completed response; failures and interrupted turns retire the local session. Progressive tool disclosure is disabled for this thirteen-tool profile; the model receives the reviewed function schemas directly. The telemetry overview summarizes services/applications instead of injecting their complete inventories; an explicit section retrieves detail.

## Internet information

The reviewed `jarvis_online` tool provides weather, FX, stocks, news,
time, saved city and general search. Search reuses the installed bundled Hermes
`DDGSWebSearchProvider` explicitly after a backend consent check, without enabling
the broad web toolset or paid autodetection. The remaining kinds use a bounded
backend information service: fixed HTTPS provider hosts, no redirects/proxies,
three concurrent requests, a nine-second wall limit and one MiB decoded-body cap.
Open-Meteo supplies weather/geocoding, Frankfurter daily FX, Yahoo an unofficial
last-trade endpoint, and Google News bounded RSS headlines. Sources/timestamps
remain visible. No full article/page extraction is claimed.

The authenticated browser alone edits private online settings; the plugin can
read defaults and perform lookups. A saved city and IANA timezone supply weather
and clock defaults without GPS. Updates invalidate the cache generation, recheck
permission after semaphore waits, and discard old in-flight responses. Caches
are bounded to 128 in-memory entries with type-specific TTLs. Time/saved-city
queries work offline. Recognized online prompts require relevant current-turn
receipts from the native `jarvis_online` tool; desktop receipts cannot substitute.
Displayed/history summaries derive from those receipts with bounded HTTPS links,
not from an invented forecast or exchange quote. Ordinary reasoning remains the
selected Hermes model's output.

`scripts/sync-plugin.py` backs up changed plugin files and refreshes only the
dedicated Hermes home before launching its official CLI. Preflight requires the
reviewed online/telemetry tools and still rejects unknown tools, global homes,
remote model endpoints and MCP. A running older gateway must be restarted.

The installed package manager records the current immutable dependency generation in its facts.json. Read-only discovery resolves that interpreter on each launch. We launch Hermes' official CLI module with the existing interpreter and `HERMES_DISABLE_LAZY_INSTALLS=1`, so the dedicated home does not trigger a duplicate dependency install. Global source, credentials and identity are preserved.

Ollama 0.30.0 ignores the native Hermes extra_body.options.num_ctx override on its OpenAI-compatible endpoint. The original model actually loaded 4096 context and truncated the user message after large tool results. With explicit user approval, a separate jarvis-qwen35-4b-64k:latest tag was created with PARAMETER num_ctx 64000, sharing the original weight layers. Both model context pins remain 64000, but preflight also checks the real model's explicit default via /api/show with a separate client that never receives the Hermes bearer key. A genuine two-tool completion verified /api/ps allocation at 64000. No Ollama service configuration was modified.

## Terminal commands and desktop policy

`DesktopAccess` owns private desktop.db command recipes and the browser's
ask-before-launch setting. Two reviewed native tools list recipes and request an
opaque command ID; command authoring/deletion/settings have browser-only routes.
The server parses browser-authored text once into direct arguments, pins executable
metadata, rechecks the home working directory and builds Kitty's fixed invocation.
`--session none` avoids a configured startup session swallowing the requested
program; `--hold` keeps the terminal available afterward. These options follow the
[official Kitty command interface](https://sw.kovidgoyal.net/kitty/invocation/).

Requests enter the same one-use action store. Default requests stay pending;
explicit browser preauthorization consumes only launch/terminal requests and logs
the authority source. Human review continues for all other kinds. Repeated native
requests for the same target in a web turn reuse a receipt, avoiding duplicate
automatic windows. Saved IDs are random per creation; removing/re-adding cannot
revive a pending approval. Queued requests retain the originating web-turn state
and recheck cancellation/closure inside both serialization gates. Internal
requests without a bound web turn can only propose. Hermes' supported pre_llm_call
hook binds the native session/turn and prompt hash; tool_execution middleware
forwards runtime IDs in headers without adding model arguments. The backend
matches the exact current browser prompt and rejects reused turn identities.
Stream/history and popup outcomes distinguish terminal
launch acceptance from command completion. Commands use normal account privileges;
home-relative cwd is not a process sandbox. The file inspection API remains bounded
and read-only.

## Native identity and memory

Explicit memory requests are buffered until the native tool turn completes.
The presenter matches proposal IDs and exact content/target/reason against the
current review queue, and checks current native entries before describing a save.
Failure/pending/approved/rejected states stay distinct on stream and history
reload. Validation errors return useful bounded messages without echoing inputs.
Repeated pending facts reuse the original review snapshot. The browser reports
the target native filename after successful bridge approval and refreshes Memory.

## Home files and installed applications

The reviewed profile now has thirteen tools. Native wrappers expose
home file list/search/read, installed desktop discovery and launch proposals.
Filesystem paths are home-relative and descriptor-anchored without following
symlinks; hidden/credential/runtime paths, hardlinks, special files and mount
crossings are refused. Models receive at most 8 KiB of file text; browser previews
are capped at 32 KiB. Plain-text/JSON credential redaction runs before results
leave the backend. Reads/scans run in bounded worker threads, not model polling.

Desktop IDs pin entry bytes and filesystem identity. ActionPolicy re-resolves
them before proposal and execution; the server supplies effects and only fixed
gio launch arguments. No arbitrary process arguments reach the launcher. The
existing browser code/expiry/snapshot approval flow is the default execution
gate. Child environments preserve desktop/session variables and strip agent
credentials. Local-account mutation after validation remains the OS trust boundary.

Home-file tool use marks the active web session private in a separate table of
session IDs only. Future online requests in that session are refused before
inference, and internal online endpoints also check the active marker. Start a
new conversation to resume online work. No file content is duplicated in this
table. Native Hermes remains the transcript and reasoning runtime.

The launchers set `HERMES_HOME` to `hermes/runtime`. This dedicated home contains the actual SOUL.md and Hermes memories. The project template by itself is not an active identity. `bash scripts/hermes.sh cli` uses the same home as the API. A plain globally installed `hermes` command may use another home and is not claimed to share this identity.

Launch validation refuses inherited global homes and symlinked identity/configuration/memory. The foreground supervisor starts or validates the local Hermes API, starts the backend, serves the frontend, opens the browser and prints the local pairing token in one terminal. It stops only its owned children on exit; reusing a verified existing gateway does not transfer ownership. The explicit stop command checks recorded process command lines and working directories before sending SIGTERM.

The native API advertises `memory_write_api:false`. An isolated subprocess bridge uses the installed `tools.memory_tool.load_on_disk_store` and `apply_memory_pending` functions used by Hermes' own approval implementation. This is a version-sensitive Python compatibility boundary, not an invented public REST endpoint. It must be verified against the installed source before upgrades. It uses native locks, size limits, threat checks, entry pinning and persistence, and never rewrites MEMORY.md itself.

The application's review database stores pending proposals and metadata (reasons, pins, deletion hashes and operation history), not a second injected memory store. Approved/rejected proposal bodies are erased. Deleted exact entries have durable normalized fingerprints that block automatic recreation; obsolete pending proposals are invalidated. Paraphrased suggestions still need explicit review. Memory edits advance a server-owned epoch: old sessions cannot relabel themselves with a new browser header. Start a fresh CLI session too, because existing Hermes prompts hold frozen snapshots. Native Hermes transcripts/backups are not automatically purged by deleting a memory; they are never mined by this app to reconstruct it.

Native auxiliary.background_review is explicitly disabled in this profile. Foreground plugin suggestions remain available and reviewable, while turning off application suggestions cannot be bypassed by Hermes' separate background self-improvement path. Native memory itself remains enabled and injected by Hermes.

## Audio

The browser requests microphone permission only on interaction, captures at most 60 seconds with MediaRecorder, and uploads the raw container with its MIME type. Preferred encoding is Opus in WebM, then Ogg/Opus, then MP4 when supported. The backend verifies signatures and the 12 MiB size limit, then sends a length-framed recording to an isolated resident CPU worker. PyAV decodes 16 kHz mono in RAM, with a 65-second decoded cap allowing container padding; silence is rejected before model loading. Recordings are not saved.

STT defaults to NVIDIA Parakeet TDT 0.6B v3, using the official Q8_0 GGUF with NVIDIA NeMo-Speech.cpp 0.3.0's size-tagged ASR C ABI. Only the backend/model startup prefix is bound; omitted optional fields keep native defaults. CPU backend -1 is explicit. Each native result is copied and freed; the recognizer remains resident until shutdown/failure/cancellation. Native stdout is separated from the JSON protocol. The subprocess receives a minimal environment without Hermes/browser credentials and has no network provider or additional listening port. Setup pins SHA256, size and source revisions; runtime only reads local assets. An explicitly configured faster-whisper CPU/int8 provider remains available without automatic substitution.

The API allows at most two pending transcription jobs and serializes native work. A request-disconnect watcher cancels and awaits its worker job; session logout cancels that browser's jobs without cancelling other browsers' recognition. Cancelled/failed workers are terminated before serialization is released. A 90-second processing timeout bounds stalled work. The subprocess boundary keeps native/model failures from taking down typed chat. Reported language is null when the native result does not expose detected-language metadata.

JarvisLuxTTS runs in one resident subprocess using the original StreamJarvisTTS class. CPU is the default; a browser-only CSRF-protected selector persists CPU/CUDA in private application state. Device switching stops the old worker under the same preparation/synthesis lock. CUDA validates availability, requires 2 GiB free VRAM before loading and caps the PyTorch allocator at 25% of total VRAM; context/library overhead is additional. Missing CUDA or insufficient memory fails explicitly. The adapter calls `lux_tts.generate_speech` with the original encoded reference and synthesis settings; it never calls speak(), which plays on the host.

An authenticated preparation request initializes the worker before the final reply. A plan normalizes the whole final text and splits it into bounded phrases. Synthesis receives the original text plus a validated phrase index so a second normalization cannot corrupt numeric prefixes. The browser plays one phrase and prefetches at most one next phrase. Actual analyser data remains attached to each playing media element. It never speaks unverified agent deltas. Outputs are 48 kHz PCM16 WAV files with random IDs, authenticated URLs, and a five-minute lifetime. A periodic cleanup removes expired files. Scoped cancellation tombstones reject late phrase requests. Stopping active synthesis kills the worker; future preparation reloads it. This trades interruption latency for resource control.

The user's selected voice environment remains unchanged. CPU reference transcription requires openai/whisper-tiny even though the GPU loader uses whisper-base. Setup downloads the former into a private project cache and links the existing cached LuxTTS assets for reading. Runtime is offline. Speech pace defaults to 0.73, down from upstream 0.8. Automatic speech defaults on. Browser preference schema v3 enables release-to-send once for older preferences, then preserves subsequent opt-outs. Pointer capture and focused Space/Enter share the hold/release lifecycle; blur, hidden tabs, cancellation and late permission grants discard capture. Approval speech goes through the exact confirmation parser before any ordinary chat submission.

Hermes supports command-type TTS providers, but its API server advertises `audio_api:false` and its standard API toolset omits text_to_speech. Therefore the application controls synthesis after a successful final reply. It does not rely on the model deciding to speak. No browser speech-synthesis fallback is used.

The Web Audio graph attaches an analyser to actual microphone or browser playback data. RMS amplitude drives the core, time-domain samples deform a 128-point ring, and FFT magnitudes drive 48 instanced radial bars. Buffers and objects are reused per frame without React state updates. Silence produces no invented speech pulse. Audio failures leave text input and telemetry usable.

## Graphics and monitoring

The lazy-loaded canvas contains procedural sphere shaders, instanced radial ticks, independent torus assemblies, orbital paths, particles, Drei lines and React Three Postprocessing bloom. The panels remain normal DOM components. Rendering is demand-driven by a capped timer (20/30/45 FPS limits), DPR is capped at 1/1.25/1.5, and hidden tabs stop requesting frames. Reduced motion renders a static core. Context loss/WebGL absence produces an explicit 2D fallback.

Telemetry is independently sampled and cached for four seconds; inference is never used to generate metrics. Monitoring is disabled by default, evaluates ordinary thresholds every ten seconds when enabled, requires sustained excursions, resets through hysteresis and deduplicates via cooldowns. Explicitly authorized routines store bounded telemetry reports only while monitoring and the app are running; no scheduled command execution or cloud scheduling exists.

## Verified system reports

Strict whole-message greetings, attention cues and name questions have bounded presentation replies after a successful Hermes completion. They still use native Hermes sessions; failed inference is never presented as a successful response. This prevents a small model's unsolicited diagnostics and identity drift from reaching speech. History uses the same projection. User-name answers read current guarded native memory only, accept explicit user-name statements, and ask when absent or conflicting. Deleted facts are never recovered from old transcripts. Compound prompts and ordinary reasoning remain model responses. The native transcript is retained unchanged, so it may contain a longer original model answer than the displayed greeting.

The supported Chat Completions system-message field adds a short application policy on top of native Hermes identity and memory. It does not replace SOUL.md. Live-diagnostic text is buffered until successful, relevant current-turn native tool results are available; no-tool, failed or unrelated claims are rejected and the session retired. For recognized live diagnostics, the backend obtains verified_summary objects with explicit source and coverage metadata from Hermes’ authenticated native tool transcript, verifies that they cover the requested measurements, and renders the bounded factual summaries. The same derivation is used on history reload, without a duplicate transcript store. This prevents the small model’s invented capacities or thermal judgments from becoming a system report. Other free-form reasoning still needs human judgment.

The foreground supervisor records Linux process start time and exact invocation, validates the dedicated HERMES_HOME and workspace, and sends explicit stop signals through a pidfd to prevent PID-reuse mistakes. Development backend startup does not require a production bundle; the launcher waits for Vite readiness before opening the browser.

## Immersive mode and map receipts

App owns layout, transcript, player and listener state. Fullscreen is applied to
the document root so native permission dialogs remain visible. CSS repositions
the existing core/chat; it does not mount a second canvas or create another audio
context per view. The bounded wake VAD supports a conversation mode without a
wake-prefix requirement; it attaches the shared visual analyser to the live stream.
Speaker/generation suspension and a 900 ms tail prevent self-transcription. Each
mode retains cancellation generations, late-permission cleanup and hidden-page
release. Startup MP3 uses the same exclusive player and cancellation path as TTS.

The saved immersiveMicMode selects always-listening conversation or wake-only
VAD. A bare wake call arms one follow-up command; its five-second monotonic deadline
starts when command capture begins. Sustained VAD speech beginning before the
deadline lets the bounded phrase finish. An empty transcript disarms the window.
Hiding, mode changes and microphone mute disarm it. Mode switches advance the capture
generation even when both old/new modes currently allow unprefixed speech.
Neither mode changes desktop wake consent or any backend authorization.

ListeningFrame renders only after an accepted wake call, with a brief fade on
exit. It fits the viewport edges with small 12px/8px corners. A thin colored rim
and broad radial/linear gradients diffuse color inward without a Gaussian blur.
Opacity is the animated property; reduced motion disables it and
hidden tabs render no frame. No additional canvas or neural model is used.

Immersive chat uses an explicit viewport-derived height, a bounded flex message
log and a nonshrinking composer. ChatPanel scrolls only its own log, follows new
text only while near the bottom, and observes resizes when a hidden drawer opens.
It does not scroll the document. Wide-screen chat reduces the existing core's
available canvas width; the existing camera fitting responds without remounting.

Map lookup extends jarvis_online's existing schema, not the toolset. Fixed-host
Nominatim geocoding is globally serialized at at most one request per 1.1 seconds
with a bounded cache. OSRM returns driving geometry. Only a short source summary
and opaque expiring map receipt enter the native transcript; geometry stays in a
32-entry in-memory backend cache. Browser-only selection resolves ambiguous
candidates and explicitly confirms a saved city-centre origin. Successful native
current-turn map receipts generate an SSE map event independently of prompt intent
heuristics. Lazy MapLibre consumes authenticated receipt data, loads OpenFreeMap
vector data only with internet permission, and preserves the latest receipt in App.
Leaflet/OSM remains the explicit 2D and WebGL-failure fallback. A dedicated map
container has explicit full dimensions, independent of MapLibre's lazy CSS.
The map is a geographic overlay; the Jarvis core remains genuine R3F geometry.

MapLibre uses two local bundled workers, capped pixel ratio and a 1.6-million-pixel
budget. It renders on demand; destination camera motion lasts 6.5 seconds with
smooth interpolation of zoom, pitch and bearing. Pending lookups have a bounded
five-second camera adjustment, not a fabricated destination. Page hiding stops
camera animation; becoming visible reapplies the last verified view. Reduced
motion removes the flight. Building heights come from vector properties.

News/stocks add opaque information receipts in a bounded 32-entry, 30-minute
in-memory store. Only three compact news items and quote metadata enter the model
prompt; up to 12 headlines and 120 actual chart samples remain in the browser
receipt. Native tool provenance emits an information SSE event. No second agent,
article extractor or model-driven chart generator is introduced.

Wake recognition accepts either leading Jarvis or Hey Jarvis. A callback after a
valid, uncancelled STT result triggers the temporary edge indicator. The browser
processing cue uses a separate decoded 700-millisecond local WAV buffer and gain,
never the microphone/playback analyser. AudioBus's beforePlayback notification
disconnects that cue synchronously before the voice player starts. Effect cleanup
handles cancellation, toggling, hiding and lock. Browser-local boot and processing
sound preferences are independent of the voice-output preference.
The WAV is extracted from the user's supplied MP3 (0:01.0–0:01.7) with five-ms
edge fades, stored beneath
the private state directory and served at one fixed authenticated audio route.

Standalone mute/unmute commands are browser audio controls handled before normal
chat or confirmation parsing. Bare mute controls Jarvis speech; mic/microphone
qualifiers control browser capture. They do not reach Hermes or system tools.
The persisted microphoneMuted preference gates manual, approval and wake/immersive
capture. Muting releases tracks and aborts transcription; late results and pending
permission callbacks are fenced. Transcription and synthesis have separate abort
controllers, so microphone mute does not cancel playback. Speech checks current
preferences before synthesis, including when a response began before voice mute.
