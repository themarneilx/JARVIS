import type { ShortcutEvent, ShortcutSpec } from "./types";

export const shortcutWeekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function newShortcut(timezone: string): ShortcutSpec {
  return {
    name: "Alarm", trigger: "once", time: "07:00", date: "", timezone,
    weekdays: [0, 1, 2, 3, 4, 5, 6], threshold: 20,
    message: "Sir, it is {time}.", weather: false, chime: true, delivery: "auto",
  };
}

export function shortcutTemplate(kind: "alarm" | "battery" | "briefing", timezone: string): ShortcutSpec {
  const spec = newShortcut(timezone);
  if (kind === "battery") return {
    ...spec, name: "Low battery", trigger: "battery", time: "", chime: false,
    message: "Sir, your battery is at {battery_percent} percent. Please connect the charger.",
  };
  if (kind === "briefing") return {
    ...spec, name: "Morning briefing", trigger: "daily", weather: true, chime: false,
    message: "Good morning, sir. It is {time}.",
  };
  return spec;
}

export function shortcutReview(spec: ShortcutSpec): string {
  const schedule = spec.trigger === "manual" ? "When you choose Run now"
    : spec.trigger === "battery" ? `When battery reaches ${spec.threshold}% or lower while discharging`
    : spec.trigger === "once" ? `Once at ${spec.time || "a selected time"}${spec.date ? ` on ${spec.date}` : " at its next occurrence"}`
    : `At ${spec.time || "a selected time"} on ${spec.weekdays.map(day => shortcutWeekdays[day]).join(", ") || "selected weekdays"}`;
  const delivery = spec.delivery === "auto" ? "Available browser, otherwise desktop speakers"
    : spec.delivery === "desktop" ? "Desktop speakers" : "This paired browser";
  return `${schedule}${spec.trigger === "once" || spec.trigger === "daily" ? ` · ${spec.timezone || "saved timezone"}` : ""}. ${delivery}.`;
}

export function shortcutEventTime(value: number | null, timezone?: string): string {
  if (!value) return "None yet";
  try {
    return new Date(value * 1000).toLocaleString([], { timeZone: timezone || undefined, month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return new Date(value * 1000).toLocaleString();
  }
}

export function isShortcutAudioUrl(url: string): boolean {
  return /^\/api\/audio\/[a-f0-9]{48}$/.test(url);
}

export function applyShortcutCancellation(data: string, activeEventId: string, stop: () => void): boolean {
  try {
    const value: unknown = JSON.parse(data);
    if (!value || typeof value !== "object") return false;
    const notice = value as { type?: unknown; event_id?: unknown };
    if (notice.type !== "cancel" || notice.event_id !== activeEventId) return false;
    stop();
    return true;
  } catch {
    return false;
  }
}

export async function playClaimedShortcut(options: {
  event: ShortcutEvent;
  claimId: string;
  requestedVoice: boolean;
  voiceEnabled: () => boolean;
  cancelled: () => boolean;
  audio: () => Promise<{ url: string; duration: number; text: string }>;
  play: (url: string, requiresVoice: boolean) => Promise<"delivered" | "muted">;
  updateText: (text: string) => void;
  finish: (status: "delivered" | "muted") => Promise<unknown>;
}): Promise<void> {
  const artifact = await options.audio();
  if (options.cancelled()) return;
  options.updateText(artifact.text || options.event.text);
  if ((options.requestedVoice && !options.voiceEnabled()) || !artifact.url) {
    await options.finish("muted");
    return;
  }
  if (!isShortcutAudioUrl(artifact.url)) throw new Error("The shortcut returned an invalid local audio artifact.");
  const status = await options.play(artifact.url, options.requestedVoice);
  if (!options.cancelled()) await options.finish(status);
}
