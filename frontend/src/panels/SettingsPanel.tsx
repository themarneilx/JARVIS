import { useEffect, useState } from "react";
import { post } from "../services/api";
import type { MonitorView, Preferences, Status } from "../services/types";
import { ModelPanel } from "./ModelPanel";
import { SpeechDeviceControls } from "./SpeechDeviceControls";
import { LocationSettings } from './LocationSettings';
import { DesktopSettings } from './DesktopSettings';
export function SettingsPanel({
  preferences,
  change,
  status,
  monitor,
  refresh,
  fail,
  modelBusy,
  modelChanged,
  stopSpeech,
  speechBusy,
  testSpeech,
}: {
  preferences: Preferences;
  change: (p: Partial<Preferences>) => void;
  status: Status | null;
  monitor: MonitorView | null;
  refresh: () => void;
  fail: (s: string) => void;
  modelBusy: boolean;
  modelChanged: () => void;
  stopSpeech: () => Promise<void>;
  speechBusy: boolean;
  testSpeech: () => void;
}) {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]),
    [minutes, setMinutes] = useState(60),
    [name, setName] = useState("System status report"),
    [consent, setConsent] = useState(false);
  async function enumerate() {
    try {
      setDevices(await navigator.mediaDevices.enumerateDevices());
    } catch {
      fail("Audio device enumeration is unavailable.");
    }
  }
  useEffect(() => {
    if ("mediaDevices" in navigator) void enumerate();
  }, []);
  async function run(work: () => Promise<unknown>) {
    try {
      await work();
      refresh();
    } catch (e) {
      fail(String(e));
    }
  }
  return (
    <div className="detail-page">
      <div className="page-heading">
        <div className="small-label">PERSONAL CONFIGURATION</div>
        <h1>Settings</h1>
        <p>
          Voice, graphics, and explicitly authorized monitoring. Preferences
          stay in this browser; the AI brain and speech device are shared locally.
        </p>
      </div>
      <div className="detail-grid settings-grid">
        <ModelPanel changed={modelChanged} fail={fail} busy={modelBusy} />
        <LocationSettings changed={refresh} />
        <DesktopSettings changed={refresh} />
        <section className="panel">
          <div className="panel-title">
            <h2>Rendering</h2>
          </div>
          <label>
            Resource preset
            <select
              value={preferences.quality}
              onChange={(e) =>
                change({ quality: e.target.value as Preferences["quality"] })
              }
            >
              <option value="low">Low Power · 20 FPS limit / no bloom</option>
              <option value="balanced">Balanced · 30 FPS limit / bloom</option>
              <option value="performance">Performance · 45 FPS limit</option>
            </select>
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={preferences.reducedMotion}
              onChange={(e) => change({ reducedMotion: e.target.checked })}
            />
            Reduce motion
          </label>
          <p className="muted">
            Resolution is capped at 1.5 device pixels. Background tabs stop
            requesting frames. Actual frame rates depend on available resources.
          </p>
        </section>
        <section className="panel">
          <div className="panel-title">
            <h2>Voice output</h2>
            <span>JARVISLUXTTS</span>
          </div>
          <label className="check-label">
            <input
              type="checkbox"
              checked={preferences.voice}
              onChange={(e) => change({ voice: e.target.checked })}
            />
            Enable voice output
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={preferences.autoSpeak}
              disabled={!preferences.voice}
              onChange={(e) => change({ autoSpeak: e.target.checked })}
            />
            Speak replies automatically
          </label>
          <label className="check-label">
            <input type="checkbox" checked={preferences.startupSound}
              onChange={e => change({ startupSound: e.target.checked })} />
            Enable boot-up sound
          </label>
          <p className="muted">Play welcome_back_jarvis.mp3 once when this browser opens Jarvis. This choice is saved separately from spoken replies.</p>
          <label className="check-label">
            <input type="checkbox" checked={preferences.processingSound}
              onChange={e => change({ processingSound: e.target.checked })} />
            Enable processing sound
          </label>
          <p className="muted">Loop the 0:01.0–0:01.7 data-readout clip while Jarvis thinks, uses tools or prepares speech. Stops before playback; follows playback volume.</p>
          <label>
            Playback volume · {Math.round(preferences.volume * 100)}%
            <input
              aria-label="Playback volume"
              type="range"
              min="0"
              max="1"
              step="0.01"
              value={preferences.volume}
              onChange={(e) => change({ volume: Number(e.target.value) })}
            />
          </label>
          <SpeechDeviceControls enabled={preferences.voice} busy={speechBusy} stop={stopSpeech} changed={refresh} testVoice={testSpeech} />
          <p className="muted">Voice errors leave text available; no substitute voice is selected.</p>
        </section>
        <section className="panel">
          <div className="panel-title">
            <h2>Microphone & devices</h2>
          </div>
          <label className="check-label">
            <input type="checkbox" checked={preferences.microphoneMuted}
              onChange={e => change({ microphoneMuted: e.target.checked })} />
            Mute Jarvis microphone
          </label>
          <p className="muted">“Mute” disables Jarvis voice. “Mute mic” or “mute microphone” stops all Jarvis capture. These controls leave system input/output volume unchanged. Unmute the microphone here, on screen, or by typing “unmute microphone”.</p>
          <label>
            Immersive microphone mode
            <select value={preferences.immersiveMicMode} onChange={e => change({ immersiveMicMode: e.target.value as 'always' | 'wake' })}>
              <option value="always">Always listening</option>
              <option value="wake">Wake phrase · Jarvis / Hey Jarvis</option>
            </select>
          </label>
          <p className="muted">Always listening sends each phrase in immersive mode. Wake phrase waits for your call; say the name and command together, or start speaking within five seconds after calling. Silence returns to wake-only mode. Both modes pause during replies and obey microphone mute.</p>
          <label className="check-label">
            <input
              type="checkbox"
              checked={preferences.wakeWord}
              disabled={preferences.microphoneMuted}
              onChange={(e) => change({
                wakeWord: e.target.checked,
                ...(e.target.checked ? {} : { backgroundWake: false }),
              })}
            />
            Enable “Hey Jarvis” / “Jarvis” listening
          </label>
          <p className="muted">
            Requires browser microphone permission. Speech phrases are recorded
            briefly in memory and transcribed locally on CPU; recordings are not
            saved. Say “Hey Jarvis”, “Jarvis”, or “Jarvis, check my GPU.” Capture pauses
            during replies, manual recording and transcription. Locking or
            turning wake listening off releases the microphone.
          </p>
          <label className="check-label">
            <input
              type="checkbox"
              checked={preferences.wakeWord && preferences.backgroundWake}
              disabled={!preferences.wakeWord || preferences.microphoneMuted}
              aria-describedby="background-wake-help"
              onChange={(e) => change({ backgroundWake: e.target.checked })}
            />
            Keep listening when this browser is in the background
          </label>
          <p className="muted" id="background-wake-help">
            Keeps the microphone active in a hidden tab or minimized window while
            this page stays open. Browsers may throttle or suspend it, so wake
            detection is not guaranteed. Closing the page stops listening.
            Nearby or replayed voices can activate Jarvis; wake detection does
            not identify the speaker.
          </p>
          <p className="muted" role="status">
            {preferences.wakeWord
              ? preferences.backgroundWake
                ? "Wake mode: background listening allowed while this page is open."
                : "Wake mode: visible tab only."
              : "Wake mode: off."}
          </p>
          <label>
            Input device
            <select
              value={preferences.mic}
              onChange={(e) => change({ mic: e.target.value })}
            >
              <option value="">System default microphone</option>
              {devices
                .filter((d) => d.kind === "audioinput" && d.deviceId)
                .map((d, i) => (
                  <option value={d.deviceId} key={d.deviceId}>
                    {d.label || `Microphone ${i + 1}`}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Output device
            <select
              value={preferences.output}
              disabled={!("setSinkId" in HTMLMediaElement.prototype)}
              onChange={(e) => change({ output: e.target.value })}
            >
              <option value="">System default output</option>
              {devices
                .filter((d) => d.kind === "audiooutput" && d.deviceId)
                .map((d, i) => (
                  <option value={d.deviceId} key={d.deviceId}>
                    {d.label || `Output ${i + 1}`}
                  </option>
                ))}
            </select>
          </label>
          <button onClick={() => void enumerate()}>Refresh device list</button>
          <label className="check-label">
            <input
              type="checkbox"
              checked={preferences.autoSubmit}
              onChange={(e) => change({ autoSubmit: e.target.checked })}
            />
            Submit recognized speech automatically
          </label>
          <p className="muted">
            Hold the microphone button, Space or Enter to speak; release to
            transcribe and send. Turn automatic submission off to edit first.
            Recording stops after 60 seconds.
          </p>
        </section>
        <section className="panel">
          <div className="panel-title">
            <h2>Connections</h2>
          </div>
          <dl className="connection-list">
            <dt>Hermes Agent</dt>
            <dd>
              {status?.agent.connected
                ? "Connected · restricted tools"
                : "Not ready"}
            </dd>
            <dt>Identity</dt>
            <dd>
              {status?.identity.matches_template
                ? "J.A.R.V.I.S. loaded"
                : "Profile setup required"}
            </dd>
            <dt>Transcription</dt>
            <dd>{status?.audio.stt_provider === "parakeet" ? "NVIDIA Parakeet v3 · CPU / Q8" : status?.audio.stt_provider === "faster-whisper" ? "faster-whisper · CPU / int8" : "Checking local speech provider…"}</dd>
            <dt>Speech engine</dt>
            <dd>
              {status?.audio.tts_checkout
                ? `${status.audio.device === "cuda" ? "GPU" : "CPU"} · ${status.audio.tts_ready ? "Voice ready" : "Voice not loaded"}`
                : "Checkout unavailable"}
            </dd>
          </dl>
        </section>
        <section className="panel">
          <div className="panel-title">
            <h2>Proactive health alerts</h2>
          </div>
          <label className="check-label">
            <input
              type="checkbox"
              checked={monitor?.settings.enabled ?? false}
              disabled={!monitor}
              onChange={(e) =>
                void run(() =>
                  post("/monitoring", {
                    ...monitor!.settings,
                    enabled: e.target.checked,
                  }),
                )
              }
            />
            Authorize local background health checks
          </label>
          <p className="muted">
            Checks every 10 seconds while the app runs, with sustained
            thresholds, hysteresis, and cooldowns. No LLM inference.
          </p>
          {monitor
            ? (
                [
                  "gpu_temperature",
                  "cpu_percent",
                  "ram_percent",
                  "disk_percent",
                  "battery_percent",
                ] as const
              ).map((key) => (
                <label className="threshold-field" key={key}>
                  {key.replaceAll("_", " ")}
                  <input
                    type="number"
                    defaultValue={monitor.settings[key]}
                    onBlur={(e) => {
                      const value = Number(e.target.value);
                      if (value !== monitor.settings[key])
                        void run(() =>
                          post("/monitoring", {
                            ...monitor.settings,
                            [key]: value,
                          }),
                        );
                    }}
                  />
                </label>
              ))
            : null}
        </section>
        <section className="panel">
          <div className="panel-title">
            <h2>Scheduled telemetry reports</h2>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (consent)
                void run(async () => {
                  await post("/routines", { name, interval: minutes * 60 });
                  setConsent(false);
                });
            }}
          >
            <label>
              Routine name
              <input
                value={name}
                required
                maxLength={80}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              Repeat interval (minutes)
              <input
                type="number"
                min="5"
                max="10080"
                value={minutes}
                onChange={(e) => setMinutes(Number(e.target.value))}
              />
            </label>
            <label className="check-label">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              I authorize this recurring local telemetry report
            </label>
            <button disabled={!consent} className="primary">
              Create routine
            </button>
          </form>
          <p className="muted">
            Enable health monitoring to run reports. Review and remove routines
            in System. Reports collect telemetry; they do not execute commands.
          </p>
        </section>
      </div>
    </div>
  );
}
