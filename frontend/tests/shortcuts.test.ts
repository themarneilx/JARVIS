import { expect, test, vi } from "vitest";
import { applyShortcutCancellation, isShortcutAudioUrl, newShortcut, playClaimedShortcut, shortcutReview, shortcutTemplate } from "../src/services/shortcuts";
import type { ShortcutEvent } from "../src/services/types";

const event: ShortcutEvent = {
  id: "event", shortcut_id: "shortcut", revision: 1, name: "Alarm", status: "preparing",
  due: 1, created: 1, delivery: "browser", text: "Sir, it is seven.", sources: [], error: "",
};
const artifact = { url: `/api/audio/${"a".repeat(48)}`, duration: 1, text: event.text };

function delivery(overrides: Partial<Parameters<typeof playClaimedShortcut>[0]> = {}) {
  return {
    event, claimId: "claim", requestedVoice: true,
    voiceEnabled: () => true, cancelled: () => false,
    audio: vi.fn(async () => artifact),
    play: vi.fn(async () => "delivered" as const),
    updateText: vi.fn(), finish: vi.fn(async () => {}), ...overrides,
  };
}

test("templates supply strict specs without activating shortcuts", () => {
  expect(newShortcut("Asia/Manila")).toMatchObject({ trigger: "once", time: "07:00", date: "", timezone: "Asia/Manila", delivery: "auto" });
  const battery = shortcutTemplate("battery", "Asia/Manila");
  expect(battery).toMatchObject({ trigger: "battery", threshold: 20, time: "", weather: false, chime: false });
  const briefing = shortcutTemplate("briefing", "Asia/Manila");
  expect(briefing).toMatchObject({ trigger: "daily", time: "07:00", weather: true, weekdays: [0, 1, 2, 3, 4, 5, 6] });
  expect(briefing).not.toHaveProperty("enabled");
  expect(briefing).not.toHaveProperty("authorized");
  expect(shortcutReview(briefing)).toContain("Asia/Manila");
  expect(shortcutReview(battery)).toContain("while discharging");
});

test("finishes only after the actual artifact finishes playback", async () => {
  let ended!: () => void;
  const options = delivery({ play: vi.fn(() => new Promise<"delivered">(resolve => { ended = () => resolve("delivered"); })) });
  const task = playClaimedShortcut(options);
  await vi.waitFor(() => expect(options.play).toHaveBeenCalledWith(artifact.url, true));
  expect(options.finish).not.toHaveBeenCalled();
  ended(); await task;
  expect(options.finish).toHaveBeenCalledExactlyOnceWith("delivered");
});

test("voice mute while server audio is preparing discards the stale speech", async () => {
  let resolve!: (value: typeof artifact) => void;
  let voice = true;
  const options = delivery({ audio: () => new Promise(value => { resolve = value; }), voiceEnabled: () => voice });
  const task = playClaimedShortcut(options);
  voice = false; resolve(artifact); await task;
  expect(options.play).not.toHaveBeenCalled();
  expect(options.finish).toHaveBeenCalledExactlyOnceWith("muted");
  expect(options.updateText).toHaveBeenCalledWith(event.text);
});

test("a chime artifact can play with voice disabled", async () => {
  const options = delivery({ requestedVoice: false, voiceEnabled: () => false });
  await playClaimedShortcut(options);
  expect(options.play).toHaveBeenCalledWith(artifact.url, false);
  expect(options.finish).toHaveBeenCalledWith("delivered");
});

test("visible-only delivery is marked muted rather than claiming audio", async () => {
  const options = delivery({ requestedVoice: false, voiceEnabled: () => false, audio: async () => ({ ...artifact, url: "", duration: 0 }) });
  await playClaimedShortcut(options);
  expect(options.play).not.toHaveBeenCalled();
  expect(options.finish).toHaveBeenCalledWith("muted");
});

test("stopped preparation never plays or finishes a cancelled claim", async () => {
  let resolve!: (value: typeof artifact) => void;
  let cancelled = false;
  const options = delivery({ audio: () => new Promise(value => { resolve = value; }), cancelled: () => cancelled });
  const task = playClaimedShortcut(options);
  cancelled = true; resolve(artifact); await task;
  expect(options.play).not.toHaveBeenCalled();
  expect(options.finish).not.toHaveBeenCalled();
});

test("artifacts remain authenticated same-origin opaque audio URLs", async () => {
  expect(isShortcutAudioUrl(artifact.url)).toBe(true);
  for (const url of ["https://example.com/audio.wav", "/api/audio/startup", "/api/audio/../../secret", `/api/audio/${"a".repeat(48)}?token=secret`]) {
    expect(isShortcutAudioUrl(url)).toBe(false);
    const options = delivery({ audio: async () => ({ ...artifact, url }) });
    await expect(playClaimedShortcut(options)).rejects.toThrow("invalid local audio");
    expect(options.play).not.toHaveBeenCalled();
    expect(options.finish).not.toHaveBeenCalled();
  }
});

test("cancellation notices stop only the matching active shortcut", () => {
  const stop = vi.fn();
  expect(applyShortcutCancellation('{"type":"cancel","event_id":"event"}', "event", stop)).toBe(true);
  expect(stop).toHaveBeenCalledOnce();
  expect(applyShortcutCancellation('{"type":"cancel","event_id":"other"}', "event", stop)).toBe(false);
  expect(applyShortcutCancellation('{"type":"complete","event_id":"event"}', "event", stop)).toBe(false);
  expect(applyShortcutCancellation('not json', "event", stop)).toBe(false);
  expect(stop).toHaveBeenCalledOnce();
});
