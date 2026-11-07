# Jarvis Shortcuts Implementation Plan

> **For agentic workers:** Use the shared contract below to implement independent
> frontend, native Hermes and delivery tasks in parallel; integrate and verify
> each with the backend store/API before claiming completion.

**Goal:** Build reviewable, persistent local shortcuts for alarms, spoken battery
warnings and morning briefings using the selected JarvisLuxTTS voice.

**Architecture:** Extend the local monitoring/scheduling subsystem with a guarded
SQLite shortcut store and a bounded delivery worker. Hermes remains the only
reasoning loop and proposes shortcuts through the reviewed plugin. Scheduled
checks, phrasing and weather retrieval use ordinary code, without periodic LLM
inference. No system timer/service is enabled; the backend and laptop must be awake.

**Tech stack:** Existing FastAPI, SQLite, zoneinfo, React/TypeScript, JarvisTTS,
Open-Meteo information service, fixed PipeWire playback executable.

**Spec:** The user-requested alarm, low-power and morning-weather behavior is
specified in the scope and shared API contract below.

## Scope and authorization

- Triggers: manual, once, daily on selected weekdays, battery at/below threshold.
- Actions in order: optional chime, custom short announcement, optional live saved-city weather.
- Only these actions are supported; no arbitrary commands, scripts, URLs or tool chains.
- UI creation/editing requires an explicit authorization checkbox. Native proposals
  use the existing exact-code permission popup and cannot approve/enable themselves.
- Templates are inactive until created/authorized. Do not activate a 7AM alarm or
  battery routine merely because the user gave those as feature examples.
- Desktop playback is explicitly requested by the user. Default delivery `auto`
  prefers an available paired browser, otherwise uses local desktop speakers.
  `browser` and `desktop` remain selectable. Do not change OS input/output volume.
- Voice mute is respected; a requested chime and visible event can still notify.
- One in-flight event claim, bounded history, cooldown/hysteresis and persisted
  occurrence keys prevent duplicate scheduled runs. Disable/delete invalidates queued runs.
- No waking a suspended machine, public webhook, cloud inference, new startup unit,
  global Hermes home change or external speech environment modification.

## Shared API contract

`ShortcutSpec` is a strict flat JSON object:
`{name, trigger: manual|once|daily|battery, time: HH:mm|"", date: YYYY-MM-DD|"",
timezone: IANA|"", weekdays: number[0..6], threshold: int1..50,
message: string<=500, weather: boolean, chime: boolean,
delivery: auto|browser|desktop}`. Message placeholders are limited to `{time}`,
`{date}`, `{location}`, `{battery_percent}`. The server resolves an empty timezone
from current settings and generates canonical reviewed schedule descriptions.

`ShortcutView`: `{id, revision, spec, enabled, next_run, last_run, last_error, summary}`.
`EventView`: `{id, shortcut_id, revision, name, status, due, created, delivery,
text, sources, error}`; times are UNIX seconds. Statuses: pending, preparing,
playing, delivered, cancelled, missed, failed, muted.

All browser mutations retain existing cookie/Origin/CSRF guards.

- GET `/api/shortcuts` -> `{shortcuts, events, capabilities:{desktop_audio_available,
  timezone, location_label, weather_available}, pending_count}`.
- POST `/api/shortcuts` `{spec, authorized:true}` -> ShortcutView.
- PUT `/api/shortcuts/{id}` `{spec, authorized:true, revision}` -> ShortcutView.
- POST `/api/shortcuts/{id}/enabled` `{enabled, revision}` -> ShortcutView.
- DELETE `/api/shortcuts/{id}?revision=N` -> `{ok:true}`.
- POST `/api/shortcuts/{id}/run` `{}` -> EventView (human Run now).
- GET `/api/shortcuts/events` -> `{events}`.
- POST `/api/shortcuts/client` `{available, voice_enabled, busy}` -> `{desktop_playing}`;
  browser presence expires in 15 seconds. Keep a heartbeat while the paired app is open.
- POST `/api/shortcuts/events/{id}/claim` `{}` -> `{claim_id,event}` (one browser owner).
- POST `/api/shortcuts/events/{id}/audio` `{claim_id,voice:boolean}` ->
  `{url,duration,text}`. URL uses the existing authenticated opaque audio route.
- POST `/api/shortcuts/events/{id}/finish` `{claim_id,status:delivered|failed|muted,error?}`.
- POST `/api/shortcuts/events/{id}/stop` `{}` cancels generation/playback and the event.

Native tool `jarvis_shortcuts`: operation list/propose, with the same flattened
spec fields for propose. GET/POST internal shortcuts routes can list/propose only.
The tool returns `{source:"jarvis_shortcuts/v1",status:"pending",id,summary,spec}`.
Its receipt must match a live proposal before chat claims preparation; no receipt
means no claimed alarm. Add exactly this reviewed tool to preflight, never a broad
terminal/MCP/cron toolset. Review tickets use source `shortcut`, target schedule,
and effect containing announcement/delivery/weather details.

## Tasks

- [ ] Shortcut store: strict validation, timezone handling, deduplicated proposals,
  optimistic edits, scheduler occurrence keys, missed-alarm grace, battery latch,
  claims, durable event history, cancellation and bounded retention.
- [ ] Runner: render placeholders, actual saved-city weather with explicit failure,
  serialize selected JarvisLuxTTS/chime audio, fixed PipeWire playback, auto routing,
  stop and cleanup. Reuse the existing TTS worker/artifact registry.
- [ ] API/approval: integrate scheduler lifecycle, browser routes and native proposal
  boundary. Existing model authorization remains separate from browser approvals.
- [ ] Frontend: Shortcuts navigation, templates/builder, exact review, enable/edit/
  delete/run controls, run history and event announcement banner/queue. Play through
  the existing voice player/analyser so browser output drives the 3D core.
- [ ] Hermes: native tool, verified feedback/history, explicit timezone/current-time
  context for alarm requests, plugin/schema fixtures and dedicated profile sync.
- [ ] Verification: unit/security fixtures, browser lifecycle, real native proposal,
  selected Jarvis voice and local playback where available, documentation and commits.

## Review focus

- A restarted backend must not replay an already consumed occurrence or a stale alarm.
- Missing/charging/unknown battery readings must not fabricate a low-power event.
- Multiple tabs and browser/desktop delivery must not play the same event twice.
- Editing/disabling/deleting a shortcut must invalidate in-flight work before output.
- Speech/weather failure must leave the alarm visible and accurately reported.
- Local timezone and DST boundaries must never silently schedule at host UTC.
- Physical audio and mocked contracts must be reported separately.
