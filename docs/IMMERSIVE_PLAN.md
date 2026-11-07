# Immersive Jarvis implementation

Approved direction: reference.mp4's sparse central core and map transitions, with
continuous local phrase listening, discreet controls and collapsible chat. Keep one
mounted R3F scene and audio bus through dashboard/fullscreen transitions. Retain
review dialogs and exact-code approvals. No duplicate agent runtime.

Checklist:
- Inspect reference video and startup MP3 (59.1 s video, 17.6 s audio).
- Add fullscreen layout, explicit entry/mute/exit, collapsible chat, audio-linked
  scene details, reduced-motion and bounded pixel budget.
- Reuse bounded VAD/STT listener in conversation mode; suppress capture during
  output/synthesis and resume after a short speaker-tail delay. Hide/lock releases
  immersive capture; retain separately authorized background wake behavior.
- Serve the supplied MP3 through an authenticated fixed route. Play once per page;
  offer a gesture if autoplay is blocked. Share the voice player and analyser.
- Add fixed-provider map lookup and driving routes to reviewed jarvis_online.
  Keep route geometry out of the LLM prompt; return expiring receipt IDs. Map
  candidates require disambiguation; city defaults are not GPS origins.
- Lazy-load a Leaflet map with visible attribution, manual zoom/pan, animated
  fly-to and route overlay. Internet consent applies to tiles and lookups.
- Run unit/build/browser checks and real provider/native-tool checks where
  available. Report hardware/speech limits separately. Update README and commit.
