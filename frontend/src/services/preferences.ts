import type { Preferences } from "./types";
export const PREFERENCES_KEY = "jarvis.preferences.v3";
export function readPreferences(
  storage: Pick<Storage, "getItem">,
  reducedMotion = false,
): Preferences {
  const defaults: Preferences = {
    quality: "balanced",
    reducedMotion,
    voice: true,
    autoSpeak: true,
    volume: 0.8,
    mic: "",
    output: "",
    autoSubmit: true,
    wakeWord: false,
    backgroundWake: false,
    startupSound: true,
    processingSound: true,
    microphoneMuted: false,
    immersiveMicMode: 'always',
  };
  try {
    const current = storage.getItem(PREFERENCES_KEY);
    if (current) {
      const saved = JSON.parse(current);
      return {
        ...defaults,
        ...saved,
        backgroundWake: saved.backgroundWake === true,
        immersiveMicMode: saved.immersiveMicMode === 'wake' ? 'wake' : 'always',
      };
    }
    const previous = storage.getItem("jarvis.preferences.v2");
    if (previous)
      return {
        ...defaults,
        ...JSON.parse(previous),
        autoSubmit: true,
        backgroundWake: false,
      };
    const legacy = storage.getItem("jarvis.preferences.v1");
    return {
      ...defaults,
      ...JSON.parse(legacy || "{}"),
      voice: true,
      autoSpeak: true,
      autoSubmit: true,
      backgroundWake: false,
    };
  } catch {
    return defaults;
  }
}
