# J.A.R.V.I.S. native Hermes profile

The launchers use this project's `hermes/runtime` as HERMES_HOME. The installed global Hermes source and Python environment are reused; the global identity, memories and provider settings are separate.

```text
hermes/
├── SOUL.md                    version-controlled J.A.R.V.I.S. identity template
├── config.example.yaml        reviewed local runtime configuration
├── plugins/jarvis_desktop/    native diagnostics and proposal tools
└── runtime/                   private, ignored by Git
    ├── SOUL.md                actual loaded identity
    ├── config.yaml            local Qwen, plugin and memory settings
    ├── .env                   private API/plugin credentials
    ├── memories/
    │   ├── USER.md            approved stable preferences
    │   └── MEMORY.md          approved useful operating knowledge
    ├── plugins/               installed native desktop tools and skill
    ├── sessions/              native conversation history
    └── state.db               native Hermes session store, when created
```

The native filename is **SOUL.md**, not sould.md. There is no invented memories.md database. USER.md and MEMORY.md hold curated entries; Hermes manages their format, locking, size limits and prompt snapshots. Empty memory files are valid: identity still comes from SOUL.md.

J.A.R.V.I.S. has a composed, precise manner, restrained dry wit, concise default replies, live-tool requirements and strict approval boundaries. The application controls the original JarvisLuxTTS voice, slower pace and automatic playback; personality text never pretends an audio action happened.

Run `npm start -- --prepare-memory` to create empty native files without replacing entries. Review proposed preferences in the browser Memory panel before they are saved. Native mutations use Hermes' guarded memory bridge. Re-running preparation does not restore deleted candidates. Private candidates, entries, transcripts and credentials must never be committed.

Use `bash scripts/hermes.sh cli` for the same J.A.R.V.I.S. identity and approved memory in a CLI session. After memory edits, start a fresh conversation because existing Hermes sessions retain a frozen prompt snapshot. Longer procedures belong in native skills, such as `plugins/jarvis_desktop/skills/system-report/SKILL.md`.
