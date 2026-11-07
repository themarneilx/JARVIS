import { useEffect, useState } from "react";
import { api, post } from "../services/api";

interface SpeechSettings {
  device: "cpu" | "cuda";
  ready: boolean;
}

export function SpeechDeviceControls({ enabled, busy, stop, changed, testVoice }: {
  enabled: boolean;
  busy: boolean;
  stop: () => Promise<void>;
  changed: () => void;
  testVoice: () => void;
}) {
  const [settings, setSettings] = useState<SpeechSettings | null>(null);
  const [working, setWorking] = useState(false), [error, setError] = useState("");
  useEffect(() => {
    let disposed = false;
    const load = () => void api<SpeechSettings>("/audio/settings")
      .then(value => { if (!disposed) setSettings(value); })
      .catch(() => { if (!disposed) setError("Speech settings could not be loaded."); });
    load();
    const timer = setInterval(() => { if (!document.hidden) load(); }, 5000);
    return () => { disposed = true; clearInterval(timer); };
  }, []);
  async function select(device: "cpu" | "cuda") {
    setWorking(true);
    setError("");
    try {
      await stop();
      const selected = await post<SpeechSettings>("/audio/settings", { device });
      setSettings(selected);
      if (enabled) setSettings(await post<SpeechSettings>("/audio/prepare", {}));
      changed();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Speech device could not be changed.");
    } finally {
      setWorking(false);
    }
  }
  return (
    <div>
      <label>
        Speech processing device
        <select aria-label="Speech processing device" value={settings?.device ?? "cpu"} disabled={!settings || busy || working}
          onChange={e => void select(e.target.value as "cpu" | "cuda")}>
          <option value="cpu">CPU · conserve VRAM</option>
          <option value="cuda">NVIDIA GPU · CUDA</option>
        </select>
      </label>
      <p className="muted" role="status">
        {working ? "Preparing the selected speech device…" : settings ? `${settings.device === "cuda" ? "NVIDIA GPU" : "CPU"} · ${settings.ready ? "Voice ready" : enabled ? "Voice loads on the next request" : "Loads when voice is enabled"}` : "Loading speech settings…"}
      </p>
      <p className="muted">Both use your JarvisLuxTTS voice. GPU shares video memory with Ollama. This choice is saved on this computer.</p>
      <div className="button-row">
        <button disabled={!enabled || !settings || busy || working} onClick={testVoice}>Test voice</button>
        <button disabled={busy} onClick={() => void stop()}>Stop voice</button>
      </div>
      {error ? <p role="alert" className="warning">{error}</p> : null}
    </div>
  );
}
