# Security boundaries

Spoken/typed approval uses a four-digit review code plus the normal authenticated
browser cookie, Origin and CSRF checks. The code is not an authentication secret:
it disambiguates a visible immutable proposal. Tickets belong to one browser,
expire within 120 seconds, are consumed once, and are unavailable to the plugin.
The server rechecks the proposal snapshot before calling existing guarded action
or native-memory resolution. A model cannot resolve its own proposal. Bare “yes”,
quoted instructions and extra trailing commands do not match confirmation syntax.
Voice recognition is not speaker authentication; nearby or replayed audio can
contain a valid spoken command. Enable wake mode only when that is acceptable.

Wake listening requires an explicit browser setting and microphone permission;
it stops on hidden tabs by default. A separate explicit browser preference allows
background capture while the page remains open; existing profiles do not opt in.
Locking, disabling, page closing/freezing, suspended Web Audio and foreground
speech still stop capture. Browsers may throttle hidden pages. Short phrase
recordings are held in memory for local STT and are not saved as memories or
recordings. There is no remote speech service. The browser's ordinary microphone
permission and local account trust remain part of the security boundary.

STT uses a fixed local provider and an isolated, serial CPU worker. The Parakeet
model and official NVIDIA runtime bundle are pinned by source/version, byte size
and SHA256. Safe tar extraction rejects traversal and external symlinks; setup
does not execute installer scripts or alter a global environment. The worker
receives no Hermes/browser authentication secrets, holds recording bytes only
in RAM, and exposes no listening socket. Browser disconnect and owner-scoped
logout cancel native work; a timeout and two-job limit bound stalled/queued
requests. Recognition is fallible, particularly on short spoken numbers; extra
or malformed digits never become an approval.

Model selection is a browser-only CSRF-protected action, unavailable to Hermes
plugins. Only exact installed local tags with advertised context/tool support can
be selected. Preparation creates a deterministic separate tag through structured
Ollama API JSON; it cannot execute a shell, download weights or change service
configuration. Switching/preparing is refused while an agent turn is active.

Only loopback endpoints are supported. There is no public proxy, cloud AI fallback, remote browser access, analytics exporter, or persistent startup enabled by setup.

Internet information is an explicit read capability, independent of local model
inference. New profiles disable it until browser consent. Browser Origin/session/
CSRF checks protect city, timezone and permission updates; plugin credentials
cannot edit them. Provider requests never carry Hermes/browser bearer material.
Weather, FX, stocks, geocoding and news use fixed HTTPS destinations, no redirects
or environment proxy, bounded time/body/concurrency and structured arguments.
Queued requests recheck consent, settings changes fence old responses, and no
arbitrary webpage URL is fetched. Native Hermes DDGS handles its own disposable
search process; searches already started can finish when consent is turned off.
The app never selects a paid search provider automatically. Public information
providers receive the requested search text or city coordinates; no microphone
audio or curated memory corpus is sent to them.

Search snippets and headlines are untrusted text, not instructions or proof that
full pages were read. Online answers require relevant native-tool receipts, and
source links open HTTPS pages with noopener/noreferrer; images/raw HTML remain
suppressed. Stock data is an unofficial last-trade feed and FX is daily reference
data, not execution/trading functionality. Provider failures fail explicitly.

Pair a browser using a randomly generated private local token. The backend sets an HttpOnly, SameSite=Strict session cookie (12-hour lifetime, revoked on app restart or logout). This HTTP cookie is intentionally not Secure because the supported transport is loopback HTTP. Remote use needs a separate encrypted/authenticated design and is outside this deployment.

State-changing browser requests require an exact allowed Origin, a valid session and its CSRF token. Host checks reject DNS rebinding. Request sizes, audio signatures/duration, structured arguments and exact service allowlists are independently validated. External Markdown images and raw HTML are suppressed. Backend errors do not return upstream authentication material. Browser bundles contain no Hermes bearer or plugin credential.

The plugin credential can only access `/api/internal` diagnostics/request endpoints.
Browser credentials cannot be replaced with that bearer. The model cannot resolve
a proposal or change permission settings. A human-facing proposal displays the
kind, exact target and expected effect. The database pins those immutable values.
Approval is one use, expires in 120 seconds and revalidates current policy before
executing fixed argument arrays. A consumed approval stays consumed if execution
crashes. No arbitrary shell, shell=True, sudo, root execution or model-generated
process arguments are permitted. The explicit desktop preauthorization below is
the sole exception to per-operation approval.

Service operations support only explicitly allowlisted systemd **user** units.
Read-only system service inspection is supported. A service name in chat does
not add it to the allowlist. Application launch proposals now use reviewed
installed desktop entries, opaque fingerprinted IDs and fixed `gio launch`
arguments. Effects are generated server-side. Changed entries invalidate the
proposal, and execution follows the browser-owned desktop permission setting. Root/shell wrappers,
command-bearing terminal entries and model-supplied argument arrays are rejected.
Children receive only desktop/session environment variables, never agent/browser
credentials. Entry replacement after final validation remains within the existing
trusted local-account boundary. System/root mutations, arbitrary config changes
and process termination remain unavailable.

Desktop preauthorization is disabled initially. A paired browser with a valid
Origin and CSRF token can disable repeated approval for installed apps and exact
saved terminal commands; the plugin cannot update this setting or save commands.
The backend persists it in private desktop.db. Only launch/terminal kinds consult
it; services, memory and other desktop actions still need review. Existing pending
actions never auto-execute when it changes. Settings updates serialize with
preauthorized launches; already-started children are not terminated by revocation.

Terminal tools accept only opaque saved IDs. Exact commands are authored through
the authenticated browser and parsed without a shell. Execution pins the program
identity, arguments and home-relative working folder, then uses fixed Kitty
options. The default desktop session environment excludes all agent credentials.
Shell/privilege wrappers, shell operators, variables and set-ID binaries are
rejected; ordinary command programs must be installed under /usr/bin. Each saved
recipe has a fresh random identity, so removing/re-adding cannot revive an old
approval. Duplicate model requests for the same target in one web turn reuse the
same receipt. Queued requests retain their originating conversation and recheck
cancellation/closure after queue waits and inside the execution lock. Unbound
internal requests can propose but cannot use preauthorized execution; browser
buttons and bound web turns can. Hermes' supported pre_llm_call hook registers the
native session/turn with a hash of the current prompt. The tool_execution middleware
forwards those trusted runtime IDs in HTTP headers, outside model arguments. The
backend binds them once to the exact active browser prompt and retains replay
fingerprints for 24 hours. An unrelated CLI or stale run cannot inherit permission
merely because another chat is active. Missing or mismatched context stays pending.
Preauthorized execution is recorded as desktop_setting; manual
approval is recorded as review. A successful detached launch does not prove the
child command's exit status or output.

Browser-authored command recipes are trusted local-account capabilities, not an
OS filesystem/network sandbox: a saved program can read/write with that account's
permissions even when it starts inside home. The agent cannot supply new file
arguments or code. Do not save dangerous commands, credentials or private upload
workflows. This capability does not expand the separate home-file tools below.

Home-file tools anchor directory descriptors inside the account home and open
each component with O_NOFOLLOW. They expose only bounded read/list/name-search
operations, reject hidden/credential/native-memory paths, hardlinks, special files
and cross-device traversal, and redact common credential forms. File names/text
are untrusted data. Native memory uses its guarded bridge instead. App metadata
is inspected only in fixed installed-desktop roots; it grants no general outside-
home file access to the model. Web sessions that use home-file tools receive a
durable private-context marker; internal online lookups are refused for that
session, including future turns. A new server-owned session is needed for online
work. Direct browser information lookups remain explicitly user-controlled. This
web-conversation guard is not an OS sandbox for a separately run trusted CLI.

Memory write replies are buffered and verified against native tool receipts,
current exact proposal snapshots and current curated entries. Generic model
claims cannot establish that a preference was saved. Approval outcomes contain
IDs/status only after proposal bodies are erased; deleted memories are never
reconstituted from transcripts. Pending duplicates reuse the original immutable
review. HTTP validation details expose messages, not input values or credentials.

The dedicated Hermes profile must explicitly select only jarvis_desktop and no_mcp, have no cloud fallback providers, use the configured local Ollama endpoint and load only the reviewed plugin. The backend checks this profile in addition to API discovery because current Hermes discovery omits default MCP servers. Changes to that profile outside this application require restarting/reviewing the runtime; the preflight is defense in depth, not an OS sandbox against the local account owner deliberately replacing a running Hermes process.

Launcher validation rejects global HERMES_HOME redirects and symlinked profile identity/configuration/memory. The supervisor prints the local pairing token in the foreground launch unless --no-token is supplied; the optional systemd example suppresses it and browser opening. Process shutdown checks a recorded PID's exact runtime module and workspace. Preflight requires an explicitly configured local 64K model default and refuses remote-model metadata. The Ollama metadata client is separate from the authenticated Hermes client, preventing upstream bearer reuse.

Runtime files live below private `.runtime/` and `hermes/runtime/` directories and are ignored by Git. Never commit pairing tokens, native memories, transcripts, recordings or generated speech. Raw audio uploads are not stored. TTS artifacts expire after five minutes. Native memory deletion removes current knowledge and prevents automatic exact reconstruction, but does not constitute forensic erasure of Hermes' own transcripts, backups, filesystem snapshots or disk blocks.

Speech device selection and preparation require browser authentication, Origin and CSRF validation; plugin credentials cannot access them. Only the fixed CPU/CUDA enum is accepted. Device state is a private regular file written atomically. CUDA is explicitly selected, checked before loading and constrained by an allocator limit; its libraries/context add overhead outside that limit. Runtime speech stays offline and reuses cached model assets without editing the external speech environment. Cancelled speech IDs are remembered briefly so a late prefetched request cannot restart playback work after Stop.

Local model output and tool output remain untrusted. Logs are bounded and common credential forms are redacted; redaction cannot detect every possible secret encoding. Do not ask the agent to copy credentials into ordinary memory. Pinned memories cannot be automatically edited; all application memory writes still require review. Native Hermes write approval remains enabled as an additional gate.

Locking stops browser recording, STT requests, synthesis/playback and active chat before revoking the browser session. Shortcuts are limited to local alarm, battery and announcement routines. Every browser-created routine requires an explicit authorization checkbox; native Hermes proposals remain pending until a human approves their exact review. The scheduler uses only measured local telemetry and the existing consent-checked weather provider. It cannot execute commands or system changes. It does not wake a suspended computer, install a timer/service, or enable persistent startup. Battery notifications use sustained threshold checks, hysteresis and occurrence deduplication; unknown or charging readings do not trigger them. Browser and desktop audio share a one-use event claim, and the desktop player uses fixed local audio paths/arguments. Desktop playback still requires the backend, awake host, and local audio service to be running.

## Immersive listening and maps

Entering immersive mode is a user gesture enabling local phrase capture; mute,
exit, page hiding, locking and browser lifecycle suspension release it. It does
not enable the separate persisted background-wake preference. Playback/generation
pause capture; this is half-duplex, not speaker identification. Existing exact-code
approval parsing and backend authorization are unchanged. The startup MP3 route
requires browser authentication and serves one fixed, nonsymlink local filename.

Map searches/routes require existing online consent and the same private-session
guard as other native online lookups. Provider hosts and route-coordinate syntax
are fixed server-side; redirects, environment proxies and oversized responses are
refused. No model-supplied URL or executable HTML enters Leaflet. Labels use DOM
textContent. Browser receipt selection cannot submit arbitrary coordinates; it
chooses indices from a bounded, unexpired result. Consent/config generations
invalidate old results. Browser tiles load only while the permission-checked map
is open, using the specific CSP img-src allowance for tile.openstreetmap.org and
an origin-only referrer. Tiles already requested may finish after revocation;
the panel rechecks permission every four seconds and unmounts the tile layer.
Map providers receive places/coordinates/IP, never agent credentials or raw audio.

The 3D map additionally permits only https://tiles.openfreemap.org in CSP
connect-src; its request transformer rejects other remote origins. Workers are
bundled locally. No remote JavaScript, arbitrary style URL, satellite provider or
map API credential is introduced. Vector tiles and fonts disclose the requested
viewport and IP to that public provider. Revocation removes either renderer.

News/stock presentation receipts use the same browser authentication and internet
consent/generation checks as other online results. Provider strings are rendered
as text; article links are HTTPS with noopener/noreferrer. No article iframe,
HTML injection or full-page extraction is performed. The processing clip loads
only from its authenticated same-origin route, which rejects symlinks and files
over two MiB. It grants no microphone or operation permission; the user-supplied
MP3 and extracted WAV are not committed or sent to any external service.

Immersive wake mode still captures bounded local phrases to recognize Jarvis/Hey
Jarvis. It gates agent submissions, not physical microphone access. A bare wake
call allows one follow-up within a fixed listening window; hiding the page closes
that window and fences late results. Global Jarvis microphone mute overrides both
immersive modes. Mode selection never changes approval parsing, system sound,
background-wake consent or the reviewed Hermes toolset.
