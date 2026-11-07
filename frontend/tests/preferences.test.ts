import { expect, test } from "vitest";
import { readPreferences, PREFERENCES_KEY } from "../src/services/preferences";
const storage = (values: Record<string, string>) => ({
  getItem: (key: string) => values[key] ?? null,
});
test("new sessions speak completed replies by default", () => {
  const preferences = readPreferences(storage({}));
  expect(preferences.voice && preferences.autoSpeak).toBe(true);
  expect(preferences.wakeWord).toBe(false);
  expect(preferences.backgroundWake).toBe(false);
  expect(preferences.autoSubmit).toBe(true);
});
test("migrates the previous manual-playback default once", () => {
  const preferences = readPreferences(
    storage({
      "jarvis.preferences.v1": JSON.stringify({
        autoSpeak: false,
        volume: 0.4,
      }),
    }),
  );
  expect(preferences.autoSpeak).toBe(true);
  expect(preferences.volume).toBe(0.4);
});
test("retains an explicit opt-out after migration", () => {
  const preferences = readPreferences(
    storage({
      "jarvis.preferences.v2": JSON.stringify({
        autoSpeak: false,
        voice: false,
      }),
    }),
  );
  expect(preferences.autoSpeak || preferences.voice).toBe(false);
});
test("moves existing click-record profiles to release-and-send once", () => {
  const migrated=readPreferences(storage({"jarvis.preferences.v2":JSON.stringify({autoSubmit:false,volume:.4,voice:false})}));
  expect(migrated.autoSubmit).toBe(true);
  expect(migrated.volume).toBe(.4);
  expect(migrated.voice).toBe(false);
  expect(readPreferences(storage({"jarvis.preferences.v3":JSON.stringify({autoSubmit:false})})).autoSubmit).toBe(false);
});

test.each(["jarvis.preferences.v1", "jarvis.preferences.v2", "jarvis.preferences.v3"])(
  "keeps existing wake profiles foreground-only in %s",
  (key) => {
    const preferences = readPreferences(
      storage({ [key]: JSON.stringify({ wakeWord: true }) }),
    );
    expect(preferences.wakeWord).toBe(true);
    expect(preferences.backgroundWake).toBe(false);
  },
);

test("retains an explicit background wake choice in the current schema", () => {
  const preferences = readPreferences(
    storage({
      "jarvis.preferences.v3": JSON.stringify({ wakeWord: true, backgroundWake: true }),
    }),
  );
  expect(preferences.backgroundWake).toBe(true);
});

test.each(["true", 1, null])("does not treat %j as background microphone consent", (backgroundWake) => {
  const preferences = readPreferences(
    storage({ "jarvis.preferences.v3": JSON.stringify({ backgroundWake }) }),
  );
  expect(preferences.backgroundWake).toBe(false);
});


test("preserves the saved boot-up sound opt-out", () => {
  const storage = { getItem: (key: string) => key === PREFERENCES_KEY ? JSON.stringify({ startupSound: false }) : null };
  expect(readPreferences(storage).startupSound).toBe(false);
});

test("processing sound can be disabled independently of voice and boot sound", () => {
  const preferences = readPreferences(storage({ [PREFERENCES_KEY]: JSON.stringify({ processingSound: false, startupSound: true, voice: true }) }));
  expect(preferences.processingSound).toBe(false);
  expect(preferences.startupSound && preferences.voice).toBe(true);
});

test("Jarvis microphone mute persists separately from system device choices and voice", () => {
  const preferences = readPreferences(storage({ [PREFERENCES_KEY]: JSON.stringify({ microphoneMuted: true, mic: 'chosen-input', output: 'chosen-output', voice: true }) }));
  expect(preferences.microphoneMuted).toBe(true);
  expect(preferences.voice).toBe(true);
  expect(preferences.mic).toBe('chosen-input');
  expect(preferences.output).toBe('chosen-output');
  expect(readPreferences(storage({})).microphoneMuted).toBe(false);
});

test("immersive listening mode preserves the saved wake choice and validates old preferences", () => {
  expect(readPreferences(storage({})).immersiveMicMode).toBe('always');
  expect(readPreferences(storage({ [PREFERENCES_KEY]: JSON.stringify({ immersiveMicMode: 'wake' }) })).immersiveMicMode).toBe('wake');
  expect(readPreferences(storage({ [PREFERENCES_KEY]: JSON.stringify({ immersiveMicMode: 'unknown' }) })).immersiveMicMode).toBe('always');
});
