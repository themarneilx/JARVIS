import { useCallback, useEffect, useRef, useState } from "react";
import { api, post } from "../services/api";
import { applyShortcutCancellation, playClaimedShortcut } from "../services/shortcuts";
import type { ShortcutEvent } from "../services/types";

type Options = {
  authenticated: boolean;
  voiceEnabled: boolean;
  available: boolean;
  busy: boolean;
  humanBusy?: () => boolean;
  pauseWake: () => void;
  play: (url: string, requiresVoice: boolean) => Promise<"delivered" | "muted">;
  stopPlayback: () => Promise<void>;
  activeChanged: (active: boolean) => void;
  desktopChanged: (playing: boolean) => void;
};

export function useShortcutEvents(options: Options) {
  const latest = useRef(options);
  latest.current = options;
  const [events, setEvents] = useState<ShortcutEvent[]>([]);
  const [announcement, setAnnouncement] = useState<ShortcutEvent | null>(null);
  const [error, setError] = useState("");
  const [desktopPlaying, setDesktopPlaying] = useState(false);
  const active = useRef<{ event: ShortcutEvent; claimId: string | null; generation: number } | null>(null);
  const generation = useRef(0);
  const mounted = useRef(false);
  const dismissed = useRef(new Set<string>());
  const desktop = useRef(false);
  const heartbeatPending = useRef<Promise<void> | null>(null);
  const heartbeatRequested = useRef(false);
  const previousVoice = useRef(options.voiceEnabled);
  const voiceMuteEpoch = useRef(0);
  if (previousVoice.current && !options.voiceEnabled) voiceMuteEpoch.current++;
  previousVoice.current = options.voiceEnabled;

  const release = useCallback(() => {
    active.current = null;
    if (mounted.current) latest.current.activeChanged(false);
  }, []);

  const deliver = useCallback(async (candidate: ShortcutEvent) => {
    if (active.current || desktop.current || latest.current.busy || latest.current.humanBusy?.() || !latest.current.available || document.hidden) return;
    const deliveryGeneration = ++generation.current;
    active.current = { event: candidate, claimId: null, generation: deliveryGeneration };
    latest.current.activeChanged(true);
    latest.current.pauseWake();
    setAnnouncement(candidate);
    let claimId: string | null = null;
    let requestedVoice = false;
    let requestedMuteEpoch = voiceMuteEpoch.current;
    const cancelled = () => !mounted.current || generation.current !== deliveryGeneration;
    try {
      const claim = await post<{ claim_id: string; event: ShortcutEvent }>(`/shortcuts/events/${candidate.id}/claim`, {});
      claimId = claim.claim_id;
      if (cancelled()) {
        await post(`/shortcuts/events/${candidate.id}/stop`, {}).catch(() => {});
        return;
      }
      active.current = { event: claim.event, claimId, generation: deliveryGeneration };
      setAnnouncement(claim.event);
      requestedVoice = latest.current.voiceEnabled;
      requestedMuteEpoch = voiceMuteEpoch.current;
      await playClaimedShortcut({
        event: claim.event, claimId, requestedVoice,
        voiceEnabled: () => latest.current.voiceEnabled && voiceMuteEpoch.current === requestedMuteEpoch,
        cancelled,
        audio: () => post(`/shortcuts/events/${candidate.id}/audio`, { claim_id: claimId, voice: requestedVoice }),
        play: (url, requiresVoice) => latest.current.play(url, requiresVoice),
        updateText: text => {
          if (!cancelled()) setAnnouncement(current => current?.id === candidate.id ? { ...current, text, status: "playing" } : current);
        },
        finish: async status => {
          await post(`/shortcuts/events/${candidate.id}/finish`, { claim_id: claimId, status });
          if (!cancelled()) setAnnouncement(current => current?.id === candidate.id ? { ...current, status } : current);
        },
      });
    } catch (cause) {
      if (cancelled()) return;
      const muted = requestedVoice && (!latest.current.voiceEnabled || voiceMuteEpoch.current !== requestedMuteEpoch) && cause instanceof DOMException && cause.name === "AbortError";
      const message = muted ? "Jarvis voice was muted before the announcement finished." : cause instanceof Error ? cause.message : "Shortcut delivery failed.";
      if (claimId) {
        await post(`/shortcuts/events/${candidate.id}/finish`, { claim_id: claimId, status: muted ? "muted" : "failed", error: message }).catch(() => {});
        if (!cancelled()) setAnnouncement(current => current?.id === candidate.id ? { ...current, status: muted ? "muted" : "failed", error: message } : current);
      } else {
        if (!cancelled()) setAnnouncement(current => current?.id === candidate.id ? null : current);
      }
    } finally {
      if (generation.current === deliveryGeneration) release();
    }
  }, [release]);

  const refresh = useCallback(async () => {
    const result = await api<{ events: ShortcutEvent[] }>("/shortcuts/events");
    if (!mounted.current) return;
    setEvents(result.events);
    setError("");
    const current = active.current;
    if (current) {
      const serverEvent = result.events.find(item => item.id === current.event.id);
      if (serverEvent && ["cancelled", "failed", "missed"].includes(serverEvent.status)) {
        generation.current++;
        void latest.current.stopPlayback();
        setAnnouncement(serverEvent);
        release();
      } else if (serverEvent) setAnnouncement(previous => previous?.id === serverEvent.id ? { ...serverEvent, text: serverEvent.text || previous.text } : previous);
      return;
    }
    const pending = result.events.filter(item => item.status === "pending" && item.delivery !== "desktop");
    const candidate = [...pending].sort((a, b) => a.due - b.due)[0];
    if (candidate && !latest.current.busy && !latest.current.humanBusy?.() && latest.current.available && !document.hidden && !desktop.current) {
      void deliver(candidate);
    } else {
      const visible = result.events.find(item => !dismissed.current.has(item.id) && ["pending", "preparing", "playing"].includes(item.status));
      setAnnouncement(previous => {
        if (visible) return visible;
        const updated = previous && result.events.find(item => item.id === previous.id);
        return updated && !dismissed.current.has(updated.id) ? updated : previous;
      });
    }
  }, [deliver, release]);

  const heartbeat = useCallback(() => {
    heartbeatRequested.current = true;
    if (heartbeatPending.current) return heartbeatPending.current;
    const send = async () => {
      while (heartbeatRequested.current && mounted.current) {
        heartbeatRequested.current = false;
        const result = await post<{ desktop_playing: boolean }>("/shortcuts/client", {
          available: latest.current.available && !document.hidden,
          voice_enabled: latest.current.voiceEnabled,
          busy: latest.current.busy || !!latest.current.humanBusy?.() || active.current !== null,
        });
        if (!mounted.current) return;
        desktop.current = result.desktop_playing;
        setDesktopPlaying(result.desktop_playing);
        latest.current.desktopChanged(result.desktop_playing);
        if (result.desktop_playing) latest.current.pauseWake();
      }
    };
    const task = send().finally(() => { if (heartbeatPending.current === task) heartbeatPending.current = null; });
    heartbeatPending.current = task;
    return task;
  }, []);

  useEffect(() => {
    if (!options.authenticated) return;
    mounted.current = true;
    const stream = new EventSource('/api/shortcuts/stream');
    stream.onmessage = event => {
      const current = active.current;
      if (!current) return;
      applyShortcutCancellation(event.data, current.event.id, () => {
        generation.current++;
        void latest.current.stopPlayback();
        setAnnouncement(value => value?.id === current.event.id
          ? { ...value, status: 'cancelled', error: 'Stopped in another shortcut panel.' }
          : value);
        release();
      });
    };
    let polling = false, heartbeating = false;
    const poll = async () => {
      if (polling) return;
      polling = true;
      try { await refresh(); }
      catch (cause) { if (mounted.current) setError(cause instanceof Error ? cause.message : "Shortcuts are unavailable."); }
      finally { polling = false; }
    };
    const beat = async () => {
      if (heartbeating) return;
      heartbeating = true;
      try { await heartbeat(); } catch { /* The next authenticated heartbeat retries. */ }
      finally { heartbeating = false; }
    };
    void beat().then(poll);
    const eventsTimer = setInterval(() => void poll(), 2000);
    const clientTimer = setInterval(() => void beat(), 5000);
    const visibility = () => { void beat(); if (!document.hidden) void poll(); };
    document.addEventListener("visibilitychange", visibility);
    return () => {
      mounted.current = false;
      stream.close();
      generation.current++;
      clearInterval(eventsTimer);
      clearInterval(clientTimer);
      document.removeEventListener("visibilitychange", visibility);
      const current = active.current;
      active.current = null;
      latest.current.activeChanged(false);
      latest.current.desktopChanged(false);
      desktop.current = false;
      if (current) {
        void latest.current.stopPlayback();
        void api(`/shortcuts/events/${current.event.id}/stop`, { method: "POST", body: "{}", keepalive: true }).catch(() => {});
      }
      // Offline browser heartbeats expire after 15 seconds; logout also clears the
      // session directly. Avoid racing an unauthenticated heartbeat against logout.
    };
  }, [options.authenticated, refresh, heartbeat, release]);

  useEffect(() => {
    if (options.authenticated) void heartbeat().catch(() => {});
  }, [options.authenticated, options.busy, options.voiceEnabled, options.available, heartbeat]);

  const stop = useCallback(async (eventId?: string) => {
    const id = eventId || active.current?.event.id || announcement?.id;
    if (!id) return;
    if (active.current?.event.id === id) {
      generation.current++;
      await latest.current.stopPlayback();
      release();
    }
    try {
      await post(`/shortcuts/events/${id}/stop`, {});
      setAnnouncement(current => current?.id === id ? { ...current, status: "cancelled" } : current);
      await heartbeat();
      await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "The shortcut could not be stopped."); }
  }, [announcement?.id, heartbeat, refresh, release]);

  return {
    events, announcement, desktopPlaying, error, refresh, stop,
    isBusy: () => active.current !== null || desktop.current,
    dismiss: () => {
      if (announcement) dismissed.current.add(announcement.id);
      setAnnouncement(null);
    },
  };
}
