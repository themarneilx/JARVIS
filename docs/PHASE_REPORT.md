# Implementation and verification report

Updated 2026-11-04, Asia/Manila. Real provider tests and simulated device inputs are distinguished below. Physical microphone/speaker validation and a physical RTX browser benchmark remain outstanding.

## Standalone GGUF installer and downloaded models

Added scripts/gguf-installer/{install-gguf.sh,install_gguf.py,README.md,INSTALLED_MODELS.md}
and backend/tests/test_gguf_installer.py. The utility uses Python's standard
library, hashes and streams local files into Ollama, refuses existing names
including case variants, supports a preview, and creates separate 64K/persona
tags directly from local blobs. It does not alter the native home, global
configuration, permissions, service settings or active model selection.

Imported the Qwen3.5 2B Q4_K_M, Q6_K and Q8_0 GGUFs and Qwen3 4B 2507 Instruct
Q4_K_M GGUF from Downloads. All four J.A.R.V.I.S. aliases passed the running
backend's /api/models metadata checks: advertised tools, 262144 architecture
context limit and 64000 configured default. Selected Gemma was preserved. New
model inference latency, tool reliability and RAM/VRAM allocation were not tested.

Initial Q4 alias creation exposed Ollama 0.30.0's canonical tag capitalization:
named-base lookup could attempt a registry manifest pull. The installer now
creates both tags from the already uploaded GGUF digest and reports actual
server names. Case-insensitive overwrite and local-blob alias regressions passed;
the two partial imports were recovered without changing downloaded files.

Verification: **103 Python tests, 36 Vitest tests and the production build passed**,
including 21 installer tests for path handling, invalid/split files, collisions,
endpoint validation, dry-run, report protection and partial failures. Real imports
and backend inventory checks establish installation, not runtime compatibility.
The requested deployment copy into `../ollama stuff/` was blocked by this
session's read-only filesystem mount. The tested bundle remains available under
scripts/gguf-installer pending write access to the sibling folder.

## Browser transport, brain selection and voice controls

The user requested Gemma, a frontend brain selector, approval popups, typed/voice
confirmation and “Hey Jarvis” listening. Backend changes are in models.py,
reviews.py, streaming.py and the API/Hermes integration. Frontend changes include
ModelPanel, PermissionDialog, wakeWord/useWakeWord, confirmation parsing, voice
capture lifecycle and App integration. README, architecture, security and
troubleshooting document the runtime locations and controls.

The installed Gemma HF Q4_K_M advertises tools and a 131072 context limit. Its
original tag has no explicit 64K default, so the requested switch prepared a
separate alias sharing local weights, selected privately by the application:
`jarvis-gemma-4-e4b-uncensored-hauhaucs-aggr-fca8d39fe6de-64k:latest`.
Original Qwen/Gemma tags, global Hermes home and Ollama service settings remain
unchanged. Native Hermes receives the explicit selected model and custom provider
through its supported API; it keeps the seven reviewed tools and native memory.

A genuine Hermes telemetry + processes turn completed in **26.50 seconds** with
the selected Gemma alias. Ollama reported **64000** allocated context,
**6,737,625,086 bytes** loaded footprint, **2,844,199,485 bytes** VRAM and
**58%/42% CPU/GPU** placement. NVIDIA's whole-GPU sample was **3432 MiB / 6141 MiB**
at **48°C**. Whole-host RAM available was **8,069,681,152 bytes** and swap used
**5,602,750,464 bytes**; these host-wide values include unrelated applications.
This is one measured workload, not a latency or memory guarantee.
A final `npm test -- --hardware` run through the selected native Hermes route
completed both tools in **12.37 seconds**, again confirming the same 64000 context
and loaded model/VRAM allocation. Host RAM available was **5,574,950,912 bytes**
and swap used **2,016,145,408 bytes** in that later sample.

Fresh Zen 1.24b reproduced the reported pre-text NetworkError independently of
Hermes against a minimal idle SSE server. Standard Firefox passed the same quiet
stream. Two-second comment heartbeats let Zen complete the 20-second transport
test; real Zen chat and automatic original JarvisLuxTTS playback then passed.
Headless Zen fell back from WebGL, so this does not establish Zen GPU rendering
performance. Separate Chrome QA rendered the procedural core and verified native
chat history, telemetry, reduced motion, fallback and mobile layout.

Browser interaction checks passed model selection/64K preparation and typed
rejection. A real JarvisLuxTTS → MediaRecorder → local tiny.en transcription test
rejected a specific proposal by voice, then recognized “Hey Jarvis, are you there?”
and received a native Gemma reply with automatic original voice playback. All
desktop proposals in that successful QA flow were rejected. The input was generated speech injected as a
synthetic microphone, not a physical microphone or speaker-identity test.
The later interaction run also verified automatic spoken permission requests,
manual rejection during capture releasing its microphone track, and capture
shutdown after disabling wake listening. One earlier voice-rejection run timed
out before transcript instrumentation; the instrumented rerun passed. Recognition
is not assumed reliable for every utterance or numeric code. The popup now shows
the recognized command for correction, and the strict parser accepts digit words
and ordinary ASR comma/hyphen separators without accepting extra commands.
A later shared-session QA volume request was approved through a paired browser
and executed at 35%. That interrupted the test's expected rejection flow. The
interaction harness now uses a temporary private backend and review database on a
random loopback port so QA requests do not appear in the ordinary app session.
The final isolated run passed all interaction assertions. Real local STT returned
“Reject 7956.” and “Hey, Jarvis. Are you there?”; the specific proposal was
rejected, the native Gemma reply played automatically, and capture ended after
disabling wake mode. Its private backend, token, audio and review database were
removed after the check.

The automated suite passed **82 Python tests and 36 Vitest tests**, covering
ticket ownership/expiry/snapshot integrity, one-use execution with a fixture OS
executor, plugin rejection, local model policies, wake capture/cancellation and
stream cleanup. Review found cancellation regressions around short-lived iterator
tasks and unopened response bodies; both were reproduced in failing tests and
fixed with stable cancellation events and response-owned idempotent cleanup.
The last browser pass also exposed a wait that required both data and cancellation
to complete, delaying each event by a heartbeat interval. The reader now waits for
the first available signal and keeps the upstream iterator in one producer task;
task-context and immediate-delivery regressions passed after reproducing both
failures. A one-item queue bounds buffering.
No remaining blocker was found in the final targeted security review.

Wake mode remains off until explicitly enabled. Physical microphone accuracy,
untrusted nearby audio and laptop graphical performance require a desktop check.
Actual disruptive operations, global configuration, remote access and persistent
startup still require their own authorization.

| Phase | Completed features / modified files | Tests and actual hardware evidence | Limitations / approvals |
|---|---|---|---|
| A — audit | scripts/doctor.mjs, benchmark.ts; architecture and troubleshooting | Arch/Hyprland, PipeWire/WirePlumber, RTX 4050 Laptop 6141 MiB, 16,441,266,176 B RAM, 8,222,928,896 B swap; Ollama 0.30.0; real Q4_K_M model identified | Unavailable starter was not falsely claimed as migrated. Initial sandbox failures were not treated as broken host drivers. |
| B — core | backend/app/{runtime,hermes}.py; native jarvis_desktop plugin; runtime/profile/context launch helpers | Installed Hermes 0.22.6 at f0d94882e89ab8d4098b5bb2f166adfb9ee0a0ab discovered with its managed dependency generation. Authenticated API preflight, actual native tool execution, and real 64000-context two-tool completion passed | User approved jarvis-qwen35-4b-64k, sharing existing layers. Original tag and Ollama service preserved. No broad toolsets, MCP or cloud fallback. |
| C — browser | frontend/src/**; CPU/GPU System Overview and System cards; backend/app/telemetry.py | Chrome/Playwright rendered real WebGL; chat, native history after refresh, telemetry, 390px mobile layout, reduced motion and fallback passed. CPU package reading 53°C from coretemp / Package id 0 was displayed beside GPU temperature | Software/headless graphics do not measure physical RTX frame rate. CPU sensor selection refuses unrelated ACPI/drive readings. |
| D — identity/memory | hermes/SOUL.md, README.md; actual dedicated native files; memory bridge/UI and preparation helper | Installed native memory functions passed approved write, fresh-process retrieval, edit, deletion, duplicate and deletion-resurrection checks in a disposable profile. Actual active SOUL matches the J.A.R.V.I.S. template | USER.md/MEMORY.md are valid empty native files. Two initial preferences/system-fact proposals await browser review. Fixture writes were not inserted into active user memory; global identity was preserved. |
| E — voice | backend/app/{audio,tts_worker}.py; project voice/STT setup; useVoice/audioBus; SpeechWaveform | Original StreamJarvisTTS CPU initialization and authenticated 48 kHz PCM16 WAV succeeded. Browser automatic speech, analyser response, stop/replay passed. MediaRecorder WebM/Opus recording of real generated speech transcribed exactly through CPU/int8 faster-whisper, then reached Hermes and automatically spoke the verified status reply at speed 0.73 | Synthetic microphone stream proves the software pipeline, not physical microphone permission/device/noise quality. Physical speaker output was not audited. The user's external voice checkout/.venv were not modified. |
| F — administration | backend/app/permissions.py; System/approval UI; restricted native proposals | Tests cover immutable scoped one-use proposals, expiry, rejected actions, structured argv, allowlists and inability of plugin credentials to approve. Live services/windows/processes inspected | No disruptive action was run against the host. User-service mutation allowlist remains empty; arbitrary root/system/config/process mutations are unavailable. |
| G — monitoring | backend/app/monitoring.py and System/Settings controls | Tests cover sustained thresholds, hysteresis, deduplication and cooldowns; routines require explicit creation consent | Monitoring and routines remain disabled/uncreated. Numeric checks do not use repeated inference. |
| H — startup/docs | scripts/run.py, process_control.py, start/dev/common helpers; README; systemd example | Single terminal starts gateway/backend, serves frontend, opens browser and prints the pairing token. Real startup/stop passed. Process stop now verifies start time, full argv, dedicated home and workspace, signalling through a pidfd; stale/global-profile invocations are rejected in tests | Optional service/Hyprland examples remain uninstalled. Existing verified gateway reuse does not transfer ownership. No public binding or startup enablement. |
| I — verification | backend/tests/**; frontend/tests; real agent/memory/browser/conversation scripts | 45 Python tests, seven Vitest tests and the production build passed; genuine native/provider artifacts are private under .runtime. The full recorded-speech → STT → Hermes tool → verified short report → original TTS → browser analyser path passed | Mock fixtures are not hardware proof. Small-model free-form reasoning can still be inaccurate. Only verified tool summaries are used for general status reports; no-tool live claims are rejected. |

## Context and model evidence

The original installed tag is hf.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive:Q4_K_M. GGUF type15 and the approved alias metadata confirm Q4_K_M; the model has about 4.2B parameters. The original blob is 2,707,513,696 bytes plus a 675,568,768-byte vision projector.

The initial native Ollama probe allocated 64000 successfully, but actual Hermes /v1 requests reset to 4096 because Ollama 0.30.0 ignores options.num_ctx on that endpoint. Tool results then truncated the user prompt and produced a misleading Jinja “No user query found” error. This was reproduced and corrected with the explicitly approved separate Modelfile tag, not by weakening Hermes' context checks or modifying its internals/service. Backend preflight now requires the actual model default, using an Ollama client without the Hermes bearer key.

A genuine Hermes two-tool completion then verified /api/ps context_length 64000, a 6,240,138,687-byte loaded footprint and 3,773,258,792 bytes VRAM. Ollama reported 40%/60% CPU/GPU placement. NVIDIA sampled 3745 MiB used of 6141 MiB. Whole-host swap reached 6,954,606,592 bytes during concurrent CPU speech testing; it cannot be attributed entirely to this project.

Measured full two-tool turns took 30.47 s and 45.20 s under different concurrent loads. A later short system-report tool round trip took 20.2 s while speech/WebGL work was active. These are samples, not latency guarantees. Status output is buffered for evidence validation; ordinary chat can stream. Frontend resource samples showed roughly78 MiB backend RSS before speech dependencies were loaded and about443 MiB after real STT work; TTS resides in its own CPU worker. GPU speech models were not loaded concurrently.

## Voice corrections and final behavior

The first diagnostic's GenerationMixin failure was misleading: scripts/profile.py shadowed Python's standard profile module through PyTorch/cProfile. Renaming it to prepare-profile.py fixed the import, with a regression test. The actual CPU loader then required openai/whisper-tiny, whereas only whisper-base (used by its GPU path) was cached. Required reference weights were downloaded into a private project cache, reusing the original LuxTTS assets; no external environment was repaired or replaced.

A real cold backend WAV request succeeded in 14.58 s. Resident requests avoid model reinitialization. The user first requested a slower pace 0.68, then a slight increase; the final default is 0.73. Automatic playback is enabled through a versioned preference migration and respects subsequent opt-outs. Browser tests measured nonzero real RMS and FFT values driving the procedural core, waveform and instanced bars; no timing-only speech animation was used.

An earlier recorded fixture was transcribed exactly as “Jarvis, good evening. Give me a brief system status report.” The spoken report contained verified CPU/RAM use, GPU temperature and 6.00 GiB capacity, battery and disk readings in three concise sentences. Earlier free-form 4B responses invented or misinterpreted readings, so status rendering now derives from Hermes' current native tool transcript. This does not claim that every other model-generated explanation is correct.

## Remaining checks and permissions

- Test physical microphone capture, selected output device and subjective voice quality at the desktop. Review local STT accuracy against normal speech and room noise; tiny.en is a resource-conscious English model.
- Review the two initial Memory proposals; accepted changes use the native guarded bridge and require a fresh chat context. Do not equate those pending proposals with saved memories.
- Measure physical GPU frame rate and longer real workloads before increasing graphics/context or adding simultaneous GPU speech.
- Actual service mutations, persistent startup, live Hyprland edits, global identity replacement and remote access need their own authorization. None was performed.

The original root .git is read-only. Milestone commits use .runtime/project.git via bash scripts/git.sh. Private tokens, memories, candidates, transcripts, model weights, generated audio and detailed QA artifacts remain ignored and must not be committed.

A warmed short two-tool Hermes turn completed in **8.64 seconds** after the compact-tool and concise-response changes, again verifying 64000 allocated context and both native telemetry/process tools. That host sample showed about 8.0 GB RAM available and 1.07 GB swap in use. This is a warmed sample; earlier concurrent-load measurements remain relevant.

A later strict evidence-validation run completed in **18.54 seconds**, with both native tools and the same 64000 allocation. It showed about 10.7 GB RAM available and 1.06 GB swap in use. Live output is now derived from successful, relevant native tool results with explicit source and coverage metadata; unrelated/running-only tools cannot authorize a measurement.

A final tiny.en sample retained the full status-report command but transcribed the name as “JAVAS”; transcripts remain editable. This is a recorded accuracy limitation, not a claim of perfect recognition. Native runtime files and pending candidates remain private.

## CPU/CUDA voice selection and latency — 4 November 2026

Added an authenticated Settings selector for CPU or NVIDIA CUDA, with private
atomic persistence, readiness, Test voice and Stop voice. CPU remains the initial
default. Device changes stop current speech and serialize with preparation.
The original external checkout/environment, reference sample, three synthesis
steps and speed 0.73 are preserved. Runtime remains offline. CUDA requires 2 GiB
free VRAM before load and limits the PyTorch allocator to 25% of the GPU, with
additional context/library overhead.

Voice preparation now starts when a paired browser enables voice and during an
agent turn. Final verified text is normalized once before bounded phrase
selection; the browser plays sequentially and prefetches one next phrase.
Cancelled request IDs reject late arrivals. Code, credential normalization,
decimal/negative measurements, device validation and cancellation have regression
coverage. No unverified model deltas are spoken.

Measured on the RTX 4050 6 GB with the user's Qwen 2B Q4 64K tag resident:

| Measurement | CPU | CUDA |
| --- | --- | --- |
| 73-character sample, warm | 3.00 s | 0.38–1.00 s |
| 245-character sample, warm | 6.43 s | 0.67–1.27 s |
| First 156-character phrase, warm | 4.09 s | 0.37 s |
| Preparation samples | 9.13 s | 7.16–21.56 s |
| Resident worker RAM sample | about 2.63 GiB | about 2.56 GiB |

The direct CUDA probe recorded 1036 MiB peak allocated / 1350 MiB peak reserved
by PyTorch. Whole GPU use was 4185 / 6141 MiB, with 1669 MiB free. These values
apply to the measured workload; other brains and desktop applications can change
headroom and latency. Preparation still costs time on a cold start.

Verification: 110 Python tests, 40 Vitest tests, production build and shell/JS
syntax checks passed. Real original CPU and CUDA synthesis passed with disposable
artifacts. The isolated Playwright run used real Hermes/Ollama, the selected Qwen
brain and original JarvisLuxTTS. Automatic CUDA audio started 888 ms after text
became ready. CPU→CUDA selection survived refresh; phrase prefetch, maximum one
playing element, actual analyser RMS 0.158 / FFT peak 252, replay/stop, no late
playback and switching back to CPU passed with no page errors. The longer test
sample came from Settings' explicit Test voice control, separately from native
chat. QA state/audio/workers were isolated from the user's app and cleaned up.

Modified areas: backend audio adapter/worker/config/API, frontend voice queue,
Settings controls and hook, voice preparation/diagnostic scripts, tests and
README/architecture/security/troubleshooting documentation. Detailed private QA
artifacts remain ignored. Physical speakers, subjective voice quality and
performance with every installed brain remain unverified. No global Hermes,
Ollama service, desktop configuration or startup unit was changed.

## Parakeet, hold-to-talk and conversational identity — 5 November 2026

Parakeet TDT 0.6B v3 is the selected local STT. Setup pins NVIDIA's Q8_0 GGUF
revision/hash and the official NeMo-Speech.cpp 0.3.0 CPU bundle. The resident,
isolated C-ABI worker decodes browser audio in RAM, rejects silence/oversize
input and is cancelled on disconnect, locking and timeout. The existing external
JarvisLuxTTS environment was preserved. The explicit Whisper alternative remains
available without automatic substitution.

Both microphone controls now record while held and transcribe on release.
Normal speech submits immediately by default; the v3 preference retains later
opt-outs for editing. Approval speech still requires the exact displayed code.
Late permission grants, blur, hidden tabs and hand rejection discard recording.
A held-through-60-second cap ends the gesture without cancelling the resulting
transcription. Bare wake phrases produce only the attention cue, with no model
request or fabricated chat turn. The native SOUL template and dedicated active
identity now use Jarvis in conversation. Global SOUL was untouched; the former
dedicated file was backed up. Brief greetings/name answers are constrained after
a successful Hermes turn and on history reload. Compound requests remain model
turns; confirmed user names come only from current guarded native memory.

Real original TTS samples through Parakeet measured 0.61–0.71 s initially for a
3.4-second clip, 0.27–0.34 s for short warm clips and about 750–774 MiB worker RSS.
A 60-second repeated synthetic sample took 8.23 s and about 1170 MiB RSS. The STT
process was absent from NVIDIA's compute-process list. One short rejection-code
clip produced repeated digits even in a fresh Parakeet recognizer; Whisper read
that same clip correctly. This is an accuracy limitation, not an approval parser
exception. No physical microphone, room-noise or speaker-quality claim is made.

Isolated real browser checks passed release-to-send, delayed permission cleanup,
blur cancellation, confirmation hold/release, hand rejection and malformed
confirmation retention. A Playwright-advanced timer verified completion while
still held, using real MediaRecorder and Parakeet rather than a mocked transcript.
Native Hermes greeting/name replies and history refresh also passed.
The final browser speech run also passed real MediaRecorder → Parakeet → Hermes
→ original automatic JarvisLuxTTS, both manually and through wake listening;
bare “Hey Jarvis” generated zero model requests and only its attention cue.

Changed areas: backend STT/decoder/worker/config/API, frontend microphone controls,
voice hook, preferences/wake flow, SOUL template, setup/QA scripts and their tests.
Native memory was not edited to silently repair identity; guarded review remains
the only write path. No external speech environment or persistent startup changed.

## Sourced internet information and location defaults — 5 November 2026

The reviewed native plugin now exposes eight tools, adding `jarvis_online` while
retaining only jarvis_desktop/no_mcp. Search explicitly reuses the installed
Hermes DDGS provider. Structured backend lookups supply Open-Meteo weather/city
search, Frankfurter daily FX, Yahoo last-trade information and Google News RSS
headlines. Local time and configured-city queries need no external request.
The authenticated Settings panel edits private city/timezone/outbound permission;
the header uses the saved timezone. The user's supplied defaults remain private.
Internet is disabled in a fresh checkout. Inference and speech remain local.

Recognized online questions require relevant successful native online receipts;
desktop network/disk readings cannot become weather or currency answers. Source
links and report dates survive history reload. Unknown tools remain refused.
Settings changes invalidate cache generations, recheck queued consent and discard
old in-flight data. Backend provider requests have fixed HTTPS destinations,
bounded response sizes/concurrency/time and no redirects or credential reuse.
Only the dedicated plugin is updated at startup, preserving a backup.

Real provider checks passed weather, FX, stock trades, news and time. Real Hermes
checks passed the user's location/weather/rate questions, search, news, stocks,
time and a two-call weather-plus-FX turn. Early individual stock/compound attempts
failed and were rejected; a fresh complete run passed. These results demonstrate
working calls, not perfect small-model tool selection. General search exposes
snippets and news exposes headlines; full-page extraction is not implemented.
Yahoo's endpoint is unofficial, quotes can be delayed, and reference FX is daily.
A later small-model run chose USD/USD for an unspecified dollar-rate question.
Same-currency lookups are now refused and the application policy specifies the
USD/PHP default and reciprocal. Three consecutive real Hermes reruns of that
question then returned the correct dated USD/PHP pair.

Browser QA passed real city search, saved timezone after refresh, disabled lookup
refusal, a native sourced FX reply and restored links/history. It used a private
backend state and an executor that blocks all desktop mutations. The broader
browser check passed real WebGL rendering, deliberate WebGL-failure fallback,
CPU-temperature display, reduced motion, mobile layout and microphone denial/lock
cleanup, with no page errors. Headless software rendering does not measure RTX
frame rate. Browser-plugin tools were unavailable; reviewed temporary loopback
Chrome/CDP with Playwright was used and is not part of normal startup.

The selected brain at the later hardware check was the user's Qwen 2B Q6_K 64K
tag. Ollama reported 64,000 allocated context, 100% GPU placement and 2,869,019,278
bytes of model VRAM. Whole GPU use in that sample was 2914/6141 MiB, RAM available
about 6.7 GiB of 15.3 GiB, with about 2.0 GiB swap used across the host. A genuine
telemetry-plus-process turn completed in 5.69 s. Its first attempt skipped tools
and failed closed; after clearer per-turn tool instructions the rerun passed.
This is a measured sample, not a latency or reliability guarantee. PipeWire,
WirePlumber and Hyprland were detected. Backend RSS in browser QA was about
82 MiB before speech loading.

Automated verification: 135 Python tests, 47 frontend tests, production build,
diff whitespace and Python/JS/shell syntax checks passed. Real provider/browser/
hardware results above are separate from contract fixtures. Changed areas:
information service/API, Hermes evidence/policy and reviewed plugin, location
Settings/header/source links, launch synchronization, diagnostics/tests and docs.
No new system privilege, global profile, public route, remote inference or startup
unit was enabled. Physical audio quality and accuracy still need desktop use.

## Verified memory writes, background wake and home/app access — 5 November 2026

The reported memory failure was reproduced from real native transcripts. The
model attempted an invalid exact-text patch, an add without content, and reasons
over 300 characters. The plugin hid HTTP validation errors; the model then claimed
success. The native bridge itself passed real isolated save/read/edit/delete
checks. Tool schemas now require bounded content/reasons and report validation
messages without input values. Chat/history derive status from actual proposal
receipts, immutable pending snapshots, native saved entries and review outcomes.
No proposal is treated as a save. Pending duplicates reuse the existing review;
deleted/obsolete entries are never reconstructed. Name parsing distinguishes user
facts from assistant identity. Early chunked/typographic saved claims are held
until proof is available. Memory panel refresh and target-file confirmations now
follow successful approval, with success notices distinct from errors.

A real selected-model request created a live name preference proposal without
changing native files. Its wording omitted one requested addressing form, so the
implementation's test candidate was withdrawn and an exact complete preference
prepared for human review. This is pending, not automatically saved. The separate
global Hermes home/SOUL was preserved. Browser QA approved a disposable preference
only in its own native profile and verified the actual USER.md, fresh subprocess
retrieval, immediate Saved knowledge refresh and persistence after page reload.

Background wake now has a separate explicit opt-in, off for existing profiles.
With both checkboxes enabled it may listen while another tab/app is focused and
the browser page remains open. Manual capture, replies, locking, page freeze/
close and suspended Web Audio still release/pause capture. Graphics remain paused
when hidden. Real MediaRecorder/Parakeet recognition passed a simulated hidden-page
lifecycle test with synthetic original JarvisLuxTTS audio; bare wake used zero
model requests. Real OS minimization/browser throttling, physical microphones and
closed-browser operation are not claimed. No always-on service was installed.

The native reviewed plugin now has eleven tools, including home files, installed
application discovery and launch proposals. Home reads/listing/name searches are
bounded, descriptor-anchored and read-only; outside-home/absolute paths, symlinks,
hidden/credential/runtime paths, special files, hardlinks and cross-device paths
are refused. JSON/plain-text credential redaction covers ordinary quoted config
fields and headers. File results are untrusted data. Browser previews have a
32 KiB cap; agent reads use 8 KiB. Web file-tool use durably marks the conversation
private and refuses future outbound lookups before inference; internal endpoints
check too. A fresh session is needed for online work.

Installed app catalogs use opaque IDs pinned to entry bytes and filesystem
identity. Launch effects are generated server-side; ApprovalStore revalidates the
entry at execution and runs fixed gio launch arguments only after human approval.
Agent credentials are removed from child environments. No arbitrary model argv,
root/shell launcher or command-bearing terminal entry is exposed. Existing
same-user OS trust applies after final validation; this is not an OS sandbox for
an account owner deliberately replacing installed applications.

Real catalog discovery found eligible installed entries. Browser QA exercised
actual home-file previews, rejected an actual catalog launch proposal without
execution, refused outside-home reads and checked mobile overflow. A genuine
Hermes home-list turn took 8.97 s; a real catalog-plus-launch-proposal turn took
40.63 s and was rejected by its QA driver. No live GUI application was launched.
Approval execution was tested with a captured executor, including stale-entry
rejection and credential-free child environment. These are separate from hardware
launch compatibility claims.

The actual .env now has 24 populated local settings, reuses existing credentials,
has mode 600 and is Git-ignored. Shell loading, paths and API-key consistency were
verified without printing secrets. Location/timezone/model/device state remains
in its existing private settings; browser wake consent is not forced by .env.

Verification: 182 backend tests, 71 frontend tests, production build, diff/shell/
JS/Python syntax checks passed. New cases cover missing/failed/forged/stale memory
receipts, Unicode/stream ordering, quoted non-write prompts, pending deduplication,
JSON credential redaction, home traversal/races, app arguments/approvals and
private-context outbound refusal. Native hardware diagnostics first skipped tools
and failed closed, then a fresh genuine two-tool run passed in 2.98 s. Ollama
reported 64,000 context and 2,869,019,278 model VRAM bytes, 100% GPU placement for
the selected Qwen 2B Q6_K tag; whole GPU use was 2912/6141 MiB in that sample.
The small model remains variable, especially on multi-tool prompts; no latency
or perfect-selection guarantee is made. Hyprland/PipeWire/WirePlumber were found.

Modified areas: guarded memory/proposal presentation and schemas; approval
feedback; background wake listener/preferences; read-only home/app catalog
modules, permissions/API/native tools; System panels; private environment/template;
QA scripts/tests and documentation. No global identity, Ollama service, Hyprland
configuration, persistent startup, public route or external speech environment
was changed. Ordinary file editing, hidden files, root access and unattended app
execution remain unavailable.

## Kitty commands and desktop preauthorization — 5 November 2026

The previous app-only launcher could not run fastfetch inside a terminal. Added
browser-authored exact command recipes and two reviewed native Hermes tools:
jarvis_terminal_commands and jarvis_run_terminal. Kitty receives fixed arguments,
a validated home-relative working directory and a sanitized environment. Installed
fastfetch/btop/htop/nvtop are seeded when available. Other commands can be saved,
run and removed in Settings; models can select IDs but cannot supply process
arguments. Command identities pin executable metadata and are newly randomized
after deletion, preventing old approvals from reviving.

Settings → Desktop & terminal permissions now controls repeated approval for
installed apps and saved commands. It defaults to approval and persists privately
on this computer. The user's current preauthorization choice was preserved. The
backend still reviews services, memory and other desktop operations. Execution
records distinguish browser review from desktop_setting authority. Existing
pending requests never execute merely because the setting changes.

Hermes' supported pre_llm_call hook and tool_execution middleware bind native
session/turn IDs to the exact active browser prompt without model arguments or a
Hermes fork. Hash-only replay records reject reused turns. Queued requests retain
that origin and check cancellation/closure inside both gates. Unbound/stale/CLI
requests remain proposals and cannot borrow another browser turn's permission.
Repeated native requests reuse a receipt within a turn. Stream, history, settings
and popup wording distinguish launch acceptance from command completion.

Modified areas: backend command catalog, permission store/API and native-turn
binding; Hermes tool schemas and response verification; Settings/System/popup
feedback; unit, native and browser diagnostics; README, architecture and security.

Verification: npm test passed 205 Python and 74 frontend tests; npm run build
passed. Regression cases include scoped policy/CSRF, exact argv, revoked and
expired approvals, remove/re-add, stale executables, missing Kitty, cancelled
queued requests, unrelated/native-old turns and trusted context reset. The real
isolated Chrome settings check passed persistence, popup rejection, save/remove,
root-wrapper refusal, failed-launch reporting and mobile layout without executing
desktop changes. Browser plugin tools were unavailable; Playwright used a temporary
owned loopback Chrome/CDP profile.

Real native Hermes tests prepared the original fastfetch request in 19.78 s and
23.22 s with review enabled. After the user enabled preauthorization, an explicitly
launch-enabled diagnostic verified the trusted native binding and an executed
fastfetch launch receipt in 13.33 s. Separate fixed-command checks observed a new
Hyprland Kitty window and no launcher stderr. These prove launch behavior, not
the terminal command's completion or physical voice recognition. No TTS/STT
compatibility is inferred from this work.

General browser QA passed real WebGL, fallback, telemetry, history, reduced motion,
mobile layout and simulated microphone failure/release. One fresh run failed
closed because Qwen returned only CPU/GPU tool coverage without the requested
battery result; the fresh-session retry passed. This small-model variability
remains visible rather than weakening evidence checks. Current Qwen 2B Q6_K
preflight advertised exactly 13 reviewed tools and 64,000 context; Ollama reported
100% GPU placement and 2.9 GB model size. A whole-GPU sample was 4084/6141 MiB,
including other desktop/speech/browser use; backend RSS was about 90 MiB in QA.
The earlier genuine two-tool hardware diagnostic passed in 10.66 s on the then
selected Q8_0 tag. Selection was not changed by these checks.

Saved commands run as the normal account, not inside a filesystem/network sandbox.
The starting directory is home-scoped; file tools retain their separate read-only
boundary. Shell operators/wrappers, privilege escalation and model-authored argv
remain unavailable. No global SOUL, Hyprland/Ollama settings, persistent startup,
public endpoint or external speech environment was changed. Further exact command
authoring and permission choices are available in the browser; no Codex approval
request is outstanding.

## Immersive command centre — 2026-11-06

Implemented the approved reference-video direction: fullscreen R3F core, hidden
dashboards, discreet focusable microphone/stop/map/exit controls, collapsible
conversation, and a procedural node/link sphere. The existing waveform, frequency
bars, particles and core use the shared real microphone/playback analyser. One
canvas remains mounted across views; hidden app panels and browser tabs stop
requesting frames. A viewport pixel budget supplements existing preset FPS/DPR
limits. Reduced motion and WebGL fallback remain available.

Immersive entry starts local hands-free phrase capture on user interaction. Speech
pauses submit to the existing local STT and Hermes flow, with 60-second/12-MiB
bounds. Bare Hey Jarvis still acknowledges the user. Capture stops during output,
generation and transcription, resumes after a 900 ms speaker tail, and releases
on mute/exit/hide/lock. This is half-duplex, not acoustic echo-proof barge-in or a
background desktop wake daemon. Existing exact-code approval handling is retained.

The supplied 17.628 s welcome_back_jarvis.mp3 plays through the same authenticated,
exclusive player and visualizer once per page opening, with explicit retry/skip
when autoplay is blocked and a saved disable setting. The 59.115 s reference.mp4
was inspected at six timeline positions; neither reference video nor supplied
music is committed as application code. No external speech environment changed.

Maps use the existing reviewed jarvis_online tool (still thirteen tools total).
Nominatim resolves public places; OSRM supplies driving route geometry/distance/
estimated duration. Ambiguous matches and saved-city origins require selection.
Geometry stays outside the model prompt in 30-minute bounded receipts. A verified
native tool receipt opens the map through SSE; closing/reopening retains the
selected route. Lazy Leaflet renders real OSM tiles, attribution, markers, fly-to,
manual pan/zoom and a road polyline. It is a 2D geographic map, not 3D terrain or
turn-by-turn navigation. Internet consent and private-conversation guards apply.

Modified areas: App layout/listener coordination; useVoice and wake listener;
R3F scene and particles plus NeuralShell; MapPanel and map backend; reviewed
plugin online schema and Hermes receipt presentation; information provider
allowlist; authenticated startup route/CSP; preferences/settings/CSS; regression
tests, browser test audio isolation, README and architecture/security docs.

Verification on this checkout:
- npm test: 209 backend tests and 77 frontend tests pass. Fixtures test map consent,
  ambiguity, expiry, cache, coordinate/path validation and current-turn provenance;
  wake tests cover prefix-free phrases, wake-only acknowledgement and late cancelled
  approval transcripts. These fixtures do not prove physical microphone quality.
- npm run build and Git whitespace checks pass. Map code/CSS are separate lazy
  chunks; the core remains a separate lazy chunk.
- Owned temporary Chrome/CDP at 127.0.0.1:9223, browser plugin unavailable. At
  1512×982 and 390×844, the immersive flow preserved the exact canvas node and chat
  draft, released synthetic capture on mute, loaded actual OSM tiles, and restored
  the confirmed route after closing/reopening. No page errors or immersive mobile
  overflow. Reference mismatch: retained original sphere/rings and used a planar
  map rather than copying video artwork or introducing another WebGL map renderer.
- Actual startup MP3 playback produced 265 non-silent analyser samples out of 335
  sampled calls during the final immersive flow. No simulated speech pulse was used.
- Actual JarvisLuxTTS CUDA synthesis, automatic playback, stop and replay passed in
  immersive mode. Generated clip 6.613 s at pace 0.73; observed RMS 0.109 and FFT
  magnitude 209 on first playback. Physical speakers were not verified.
- Actual Hermes → selected local model → jarvis_online map → SSE receipt →
  authenticated map retrieval passed in 12.10 s. Actual Nominatim returned Mactan–
  Cebu International Airport, and OSRM returned a 9,636.5 m / 951.5 s route from
  the saved Mandaue city centre (20 geometry points). No live-traffic claim.
- Broader browser regression initially found dashboard mobile header overflow;
  changed the phone header to two rows. Agent telemetry, history restoration,
  WebGL fallback, reduced motion, denied-mic text usability and capture release
  on lock passed in that run. Final rerun is recorded below.
- Measured backend RSS in the browser check: 84,815,872 bytes. A later whole-GPU
  sample was 4082/6141 MiB, 0% utilization and 47°C. These include other desktop
  processes; headless SwiftShader testing does not measure physical RTX frame rate.

Remaining limits: Firefox/native fullscreen permission behavior and physical
microphone/noisy-room echo rejection need user-device testing. Public map services
are best-effort and route time excludes traffic; missing providers show errors.
Mic capture pauses during speech, so Stop must precede an interruption. Source
files and user media stay local; no global Hermes identity, Ollama service,
Hyprland configuration, persistent startup or public route was changed. No new
approval request is outstanding.

Final broader browser rerun: PASS, including real Hermes telemetry, restored
history, one WebGL canvas, simulated WebGL fallback, reduced motion, mobile
layout without overflow, denied-mic text usability and capture release on lock.
No application console errors; the pre-pairing auth-session 401 is expected.

## 2026-11-06 — Cinematic maps, information views and sound controls

Completed: MapLibre 3D vector map with bounded render resolution, real building
heights, 6.5-second camera flights with gentle pitch/bearing changes, pending-lookup
indicator, hidden-page interruption/resume and Leaflet fallback. Fixed the blank
map: lazy MapLibre CSS made the host position relative with zero height; explicit
container dimensions now preserve the full viewport. News/markets displays
verified headline details and timestamped stock samples behind expiring receipts.
Leading Jarvis and Hey Jarvis phrases trigger the edge indicator. Long chat stays
inside its panel; Settings flows in independent columns and fits mobile widths.

Boot sound has its own persisted toggle. Processing sound now uses the user's
supplied data-readout MP3 segment 0:01.0–0:01.7, with five-ms edge fades. The final
WAV is exactly 0.700000 seconds, 44.1 kHz stereo, and stays in private runtime
assets. The procedural cue was replaced at the user's request. It loops through
Web Audio, follows volume and stops synchronously before speech playback, as well
as on cancellation, disable, hidden page and lock. A fixed authenticated route
serves the clip; no speech environment or AI model changes were made.

Changed files: backend Hermes intent/receipt handling, information store, API and
regression tests; frontend App, voice/wake/processing hooks, map and information
panels, GeographicMap, Settings, audio bus/preferences/types, styles and tests;
MapLibre dependency/lockfile; two reproducible browser QA scripts; README,
architecture/security documentation and this report.

Verification:
- npm test: 213 Python tests and 82 frontend tests passed. npm run build passed.
- Broader browser check passed with actual Hermes telemetry, restored history,
  reduced motion, simulated WebGL failure, denied mic/text usability and capture
  release on lock. Headless Chrome/SwiftShader is not physical RTX performance.
- Live 3D map rendered at 1512×982; camera pitch progressed from 44.72° to 49.17°,
  paused at 49.17° during simulated hiding, then reached 55° on return. Actual
  vector requests succeeded. Live news returned 12 cards; stock chart had 106
  timestamped samples in that run. No desktop/mobile overflow or page errors.
- Wake-edge check used a synthetic microphone and a mocked local transcript;
  this proves UI lifecycle, not physical wake recognition. Boot toggle persisted.
- Processing browser check uses the actual extracted local audio, with chat/TTS
  fixtures to verify idle silence, toggle/cancel stop and stop-before-play ordering.
  No physical speaker listening test is claimed.
- Actual native Hermes map call with an explicit map instruction produced a
  verified airport receipt in 4.46 seconds; a natural Cebu news request produced
  an information receipt in 5.81 seconds. These are observed runs, not guarantees.

Known limitation: the selected 2B Qwen model sometimes chooses the wrong tool
kind or argument. “locate cebu” selected generic search; an NVDA stock request
omitted symbol and then put it in query. Both were rejected without inventing
results. Explicit map instructions and manual map/news/stock controls work;
the broad toolset and provenance checks were not weakened. News details remain
headlines/source links, not full article extraction. No new hardware allocation
or physical GPU frame-rate benchmark was performed in this change. No privileged,
global configuration or persistent startup changes require approval.

## 2026-11-06 — Independent Jarvis voice and microphone mute

Added exact local mute/unmute phrases before the AI/approval paths. Bare mute
stops Jarvis voice and disables subsequent speech. Mute mic/microphone releases
all application capture and leaves speech/system audio running. A saved browser
microphone mute gates push-to-talk, approval capture, wake and immersive mode;
on-screen and typed unmute restore it. These commands never invoke system-volume
tools or authorize a pending operation. Existing half-duplex behavior remains:
speech capture pauses during playback; typed commands or push-to-talk interrupt it.

Split transcription cancellation from speech cancellation, fenced late microphone
results and checked current voice preferences before late response synthesis.
Changed App, voice hook, chat/settings panels, preferences/types, local command
parser/tests, the browser audio-controls check and these docs. The prior loop
tuning is now 0:01.0–0:01.7, exactly 0.700000 seconds with five-ms edge fades.

Verification: npm test passed 213 backend and 105 frontend tests; production build
passed. Dedicated browser fixtures passed spoken local mute with edit-before-send,
capture release, microphone mute preserving playback, voice mute stopping playback,
persisted mute, on-screen/immersive unmute, and delayed responses honoring mute.
Zero system-mutation requests and no page errors were observed. These fixtures do
not prove physical microphone recognition or speakers. Broader browser regression
also passed real Hermes telemetry/history, fallback/reduced motion, mobile layout,
denied-mic text usability and capture release on lock. Backend RSS sample was
87,506,944 bytes; CPU package temperature was 64°C during that check. No new model
allocation or physical GPU FPS measurements were performed. No approval needed.

## 2026-11-06 — Immersive listening choice, wake lighting and bounded chat

Completed: a saved Always listening/Wake phrase switch in immersive controls and
Settings. Wake mode accepts Jarvis/Hey Jarvis plus a command, or a bare wake call
followed by one command within a fixed 15-second listening window. An absolute
monotonic deadline prevents silence/STT cycles extending it; hiding the tab,
switching modes or muting the microphone disarms the window. Existing local mute
phrases, half-duplex speech suspension and approval rules remain in effect.

The rounded, blurred cyan/blue/violet edge indicator appears only after a wake
call. There is no standby frame. It fades out after activity, supports reduced
motion and unmounts while hidden. The last visual adjustment blurs the composed
masked layer, removing the sharp border seen in the user's screenshot. The same
mounted R3F core and audio analyser continue to provide microphone/playback motion.

Fixed immersive long-chat layout with an explicit viewport-derived drawer height,
nonshrinking composer and independently scrolling messages. The former auto-height
parent/percentage-height child could expand with content; scrollIntoView could
also move ancestors and fight history reading. Chat now scrolls only its own log,
pauses following when scrolled up and follows again on a newly submitted prompt.
Wide screens reserve the right chat column and center the core in remaining space;
phones retain an overlay above the two-row control bar.

Modified: App, ListeningFrame, ChatPanel, Settings, preferences/types/styles and
preference regression tests; immersive-modes browser check; the general browser
harness; README, architecture/security docs and this report. No new dependency.

Validation:
- npm test: 213 Python and 106 frontend tests pass. Production build and whitespace
  checks pass.
- Owned temporary Chrome/CDP, headless SwiftShader: immersive fixture checks pass
  for ignored unprefixed speech, both wake phrases, wake-then-command, timeout
  through a noise transcription, armed-to-always switching, persistence, mute,
  hidden-page disarming and reduced motion. No page errors.
- At 1512×982, a 90-paragraph conversation stayed inside a 390×772 drawer with a
  502-pixel message viewport and visible input; manual scrolling worked without
  moving the document. At 390×844, chat/input stayed above the controls without
  horizontal overflow. Rounded frame radius was 44 pixels on desktop. Screenshots
  were inspected for the soft edge wash and separated core/chat columns.
- VAD, transcripts and chat in the targeted flow are explicit fixtures; these do
  not prove physical microphone accuracy, actual STT latency or physical RTX FPS.
  No new neural model, VRAM allocation or hardware compatibility claim is made.

The general browser harness initially failed because six pending permission
dialogs exceeded its old five-dialog dismissal loop. It now uses Review later
handling during actions; no proposal is approved/rejected by the check.
The full rerun also caught a dashboard flex item retaining its old canvas width
after a phone resize; explicit width/max-width bounds now keep it in the viewport.
Final npm test -- --browser --cdp exited successfully: real Hermes telemetry,
history restoration, one canvas, simulated WebGL fallback, reduced motion,
denied-mic text usability, capture release on lock and zero mobile overflow all
passed. No application console errors. Backend RSS sample: 97,509,376 bytes;
CPU package temperature: 64°C. These readings are samples rather than performance
guarantees.

Limits: wake detection still uses bounded local speech clips rather than a
dedicated instant wake engine. Fullscreen/browser microphone behavior and visual
color perception need the user's actual desktop. The video is a visual reference,
not an artwork copy; the original procedural Jarvis geometry is retained. No
system configuration or persistent startup change requires approval.

## 2026-11-06 — Short idle wake window and edge-fit lighting

Wake-follow-up mode now returns to wake-only monitoring after five seconds without
speech. Sustained VAD activity starting within the window preserves the current
bounded phrase rather than cutting off longer commands at five seconds. Empty
transcriptions disarm the window without sending a prompt. Existing hide, mute,
mode-change and late-result cancellation guards remain in effect.

The indicator now fits the full viewport, with 12px desktop and 8px phone corners.
Richer cyan, violet, pink and teal use a thin defined rim plus broad radial/linear
color diffusion. Gaussian blur was removed; opacity remains the only animated
property. It still appears only after a wake call and fades away on timeout.

Changed App, wake service/hook callbacks, Settings copy, indicator CSS, wake tests,
immersive browser QA and current README/architecture documentation. No dependency
or backend authorization change.

Checks: npm test passed 213 backend and 108 frontend tests; production build and
whitespace checks passed. Targeted headless browser QA measured 5,457ms from armed
listening to full disappearance (including the 600ms fade), preserved a 6.5-second
spoken fixture, rejected an empty follow-up and confirmed exact viewport bounds,
12px corners and no blur filter. Desktop/phone chat and controls remained usable;
mute, mode persistence, hidden-page release and reduced motion passed. Screenshots
were inspected for the broader color wash. Full browser regression also exited 0
with actual Hermes telemetry/history, one core canvas, no mobile overflow or
application console errors. VAD/STT/chat in the targeted test are explicit fixtures;
physical wake accuracy, speakers and RTX frame rate were not measured. No system
configuration, speech environment or persistent startup change needs approval.

## 2026-11-10 — Local Shortcuts and LAN access review

Added authorized local alarms, battery warnings, manual announcements and daily
weather briefings. The Shortcuts page reviews a strict schedule/action summary
before saving, records bounded event history, and supports edits, disable, delete,
run-now and stop. Hermes may list or propose a shortcut through its reviewed
plugin; only the existing human approval flow enables that proposal. A one-second
local scheduler does not invoke the model. Battery telemetry is sampled only while
a battery routine exists, with sustained thresholds, re-arm hysteresis and event
deduplication. Local speaker output is implemented through fixed `pw-play`
arguments and the existing JarvisLuxTTS provider; the host must stay awake.

Validation: `npm test` passed 304 backend and 116 frontend tests. `npm run build`
passed. `npm test -- --browser` passed against the running local application,
including genuine Hermes telemetry/history and responsive/mobile checks. A focused
real-browser flow created a manual routine, recorded its muted run, and deleted it.
`npm test -- --speech` produced a valid RIFF artifact through JarvisLuxTTS (103,468
bytes, 1.077 seconds of audio; synthesis returned in approximately 0.665 seconds in
this run). That checks synthesis, not speaker playback.

Not exercised: a real scheduled alarm, a live low-battery transition, a weather
announcement, microphone/STT capture, or desktop speakers. No claim of physical
audio delivery or suspend wake is made. The browser QA used headless Chrome and
software WebGL; it does not measure RTX performance.

A fresh review identified two edge cases and both were fixed: active browser audio
now receives an authenticated server cancellation event immediately after a
shortcut change/stop, and terminal one-time alarm outcomes leave no misleading
enabled-but-unscheduled entry. Regression tests were watched fail before fixes;
the final backend and frontend suites pass. The 15-second browser-presence expiry
is used when a paired tab closes without logging out.

LAN note: the application remains loopback-only. `scripts/start.sh`, TrustedHost,
and configured Origin validation require a separate HTTPS LAN design. The current
browser cookie is not Secure because loopback HTTP is the only supported transport.
Changing only Uvicorn's bind host would be incomplete and unsafe. No interface,
firewall, router, TLS trust store, or service configuration was modified.
