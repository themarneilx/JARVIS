import { useCallback, useEffect, useRef, useState } from "react";
import { api, post } from "../services/api";
import { audioBus } from "../services/audioBus";
import { playSpeechPhrases } from "../services/speechQueue";
import type { PhaseEvent } from "../state/machine";
import type { Preferences } from "../services/types";
import { isShortcutAudioUrl } from "../services/shortcuts";

export function useVoice(
  preferences: Preferences,
  event: (event: PhaseEvent) => void,
  transcript: (text: string) => void,
  fail: (message: string) => void,
) {
  const recorder = useRef<MediaRecorder | null>(null),
    stream = useRef<MediaStream | null>(null),
    audio = useRef<HTMLAudioElement | null>(null);
  const cancelled = useRef(false),
    captureGeneration = useRef(0),
    captureIntent = useRef(false),
    timer = useRef<ReturnType<typeof setTimeout> | null>(null),
    generation = useRef(0),
    url = useRef("");
  const [recording, setRecording] = useState(false),
    [acquiring, setAcquiring] = useState(false),
    [synthesizing, setSynthesizing] = useState(false),
    [startupBlocked, setStartupBlocked] = useState(false),
    [startupActive, setStartupActive] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const transcriptionAbort = useRef<AbortController | null>(null);
  const currentPreferences = useRef(preferences);
  currentPreferences.current = preferences;
  const synthesisId = useRef<string | null>(null),
    cancellation = useRef<Promise<void>>(Promise.resolve());
  const playbackPreferences = useRef({ volume: preferences.volume, output: preferences.output });
  playbackPreferences.current = { volume: preferences.volume, output: preferences.output };
  const prepare = useCallback(async () => {
    await cancellation.current;
    if (!currentPreferences.current.voice) return;
    // Preparation is optional; a failed attempt must leave typed interaction usable.
    await post("/audio/prepare", {}).catch(() => {});
  }, []);
  function release() {
    const hadMicrophone = stream.current !== null;
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    if (timer.current) clearTimeout(timer.current);
    if (hadMicrophone) audioBus.detach();
  }
  function stopSpeaking() {
    const hadPlayback = !!audio.current || !!synthesisId.current || synthesizing;
    const previous = synthesisId.current;
    synthesisId.current = null;
    generation.current++;
    abort.current?.abort();
    abort.current = null;
    if (audio.current) {
      audio.current.pause();
      audio.current.src = "";
      audio.current = null;
    }
    if (url.current) {
      URL.revokeObjectURL(url.current);
      url.current = "";
    }
    if (hadPlayback) audioBus.detach();
    setSynthesizing(false);
    setStartupActive(false);
    if (hadPlayback) event("CANCEL");
    if (previous)
      cancellation.current = cancellation.current
        .catch(() => {})
        .then(async () => {
          await post("/audio/cancel", { request_id: previous });
        })
        .catch(() => {});
    return cancellation.current;
  }
  async function startRecording() {
    if (captureIntent.current || currentPreferences.current.microphoneMuted) return;
    stopSpeaking();
    captureIntent.current = true;
    const captureId = ++captureGeneration.current;
    setAcquiring(true);
    cancelled.current = false;
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder)
        throw new Error(
          "This browser does not support microphone recording. Use text input.",
        );
      const capture = await navigator.mediaDevices.getUserMedia({
        audio: {
          deviceId: preferences.mic ? { exact: preferences.mic } : undefined,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      if (!captureIntent.current || captureGeneration.current !== captureId) {
        capture.getTracks().forEach((t) => t.stop());
        return;
      }
      stream.current = capture;
      audioBus.microphone(capture);
      const mime = [
        "audio/webm;codecs=opus",
        "audio/ogg;codecs=opus",
        "audio/mp4",
      ].find((m) => MediaRecorder.isTypeSupported(m));
      if (!mime) throw new Error("No supported recording format is available");
      const rec = new MediaRecorder(capture, { mimeType: mime }),
        chunks: Blob[] = [];
      const startedAt=performance.now();
      recorder.current = rec;
      let bytes = 0;
      rec.ondataavailable = (e) => {
        if (e.data.size) {
          chunks.push(e.data);
          bytes += e.data.size;
          if (bytes > 12 * 1024 * 1024) cancelRecording();
        }
      };
      rec.onstop = async () => {
        if (captureGeneration.current !== captureId) return;
        release();
        setRecording(false);
        captureIntent.current = false;
        if (cancelled.current || performance.now()-startedAt<150) {
          event("CANCEL");
          return;
        }
        event("TRANSCRIBE");
        const controller = new AbortController();
        transcriptionAbort.current = controller;
        try {
          const blob = new Blob(chunks, { type: mime });
          const result = await api<{ text: string }>("/audio/transcribe", {
            method: "POST",
            headers: { "Content-Type": mime },
            body: blob,
            signal: controller.signal,
          });
          if (controller.signal.aborted || captureGeneration.current !== captureId || currentPreferences.current.microphoneMuted) return;
          if (!result.text.trim()) {
            event("DONE");
            fail("No speech was detected. Try again or type your instruction.");
            return;
          }
          event("DONE");
          transcript(result.text);
        } catch (error) {
          if (!controller.signal.aborted)
            fail(
              error instanceof Error ? error.message : "Transcription failed",
            );
        } finally {
          if (transcriptionAbort.current === controller) transcriptionAbort.current = null;
        }
      };
      rec.onerror = () => {
        cancelRecording();
        fail("Microphone recording failed");
      };
      rec.start(250);
      setRecording(true);
      event("RECORD");
      timer.current = setTimeout(() => stopRecording(), 60000);
    } catch (error) {
      if (captureGeneration.current !== captureId) return;
      captureIntent.current = false;
      release();
      fail(
        error instanceof Error
          ? error.message
          : "Microphone permission was denied",
      );
    } finally {
      if (captureGeneration.current === captureId) setAcquiring(false);
    }
  }
  function stopRecording() {
    const pending=captureIntent.current;
    captureIntent.current = false;
    if (recorder.current?.state === "recording") recorder.current.stop();
    else if(pending)cancelRecording();
  }
  function cancelRecording() {
    const hadCapture = captureIntent.current || recording || acquiring || !!transcriptionAbort.current;
    captureGeneration.current++;
    setAcquiring(false);
    cancelled.current = true;
    captureIntent.current = false;
    transcriptionAbort.current?.abort();
    transcriptionAbort.current = null;
    if (recorder.current?.state === "recording") recorder.current.stop();
    release();
    setRecording(false);
    if (hadCapture) event("CANCEL");
  }
  async function speak(text: string, startup = false) {
    setStartupBlocked(false);
    const stopping = stopSpeaking(),
      id = generation.current;
    await stopping;
    if ((!startup && !currentPreferences.current.voice) || generation.current !== id) return;
    setStartupActive(startup);
    const requestId = crypto.randomUUID();
    synthesisId.current = startup ? null : requestId;
    const controller = new AbortController();
    abort.current = controller;
    setSynthesizing(true);
    try {
      const { phrases } = startup ? { phrases: ["startup"] } : await api<{ phrases: string[] }>("/audio/plan", {
        method: "POST",
        body: JSON.stringify({ text, request_id: requestId }),
        signal: controller.signal,
      });
      let phraseIndex = 0;
      await playSpeechPhrases(phrases, async () => {
        const artifact = startup ? { url: "/api/audio/startup" } : await api<{ url: string }>("/audio/synthesize", {
          method: "POST",
          body: JSON.stringify({ text, phrase_index: phraseIndex++, request_id: requestId }),
          signal: controller.signal,
        });
        const response = await fetch(artifact.url, {
          credentials: "same-origin", signal: controller.signal,
        });
        if (!response.ok) throw new Error("Generated audio has expired");
        return response.blob();
      }, async (blob) => {
        controller.signal.throwIfAborted();
        const source = URL.createObjectURL(blob);
        url.current = source;
        const player = new Audio(source);
        audio.current = player;
        player.volume = playbackPreferences.current.volume;
        try {
          const sink = player as HTMLAudioElement & { setSinkId?: (id: string) => Promise<void> };
          if (playbackPreferences.current.output && sink.setSinkId) await sink.setSinkId(playbackPreferences.current.output);
          controller.signal.throwIfAborted();
          audioBus.playback(player);
          await new Promise<void>((resolve, reject) => {
            const finish = (error?: unknown) => {
              controller.signal.removeEventListener("abort", onAbort);
              player.onended = player.onerror = null;
              if (error) reject(error); else resolve();
            };
            const onAbort = () => finish(new DOMException("Speech cancelled", "AbortError"));
            controller.signal.addEventListener("abort", onAbort, { once: true });
            player.onended = () => finish();
            player.onerror = () => finish(new Error("Browser audio playback failed. The text response is still available."));
            void player.play().then(() => {
              if (generation.current === id && !controller.signal.aborted) {
                setSynthesizing(false);
                event("SPEAK");
              }
            }, finish);
          });
        } finally {
          player.pause();
          player.src = "";
          URL.revokeObjectURL(source);
          if (url.current === source) url.current = "";
          if (audio.current === player) {
            audio.current = null;
            audioBus.detach();
          }
        }
      }, controller.signal, () => {
        if (generation.current === id) {
          setSynthesizing(true);
          event("SEND");
        }
      });
      if (generation.current === id) event("DONE");
    } catch (error) {
      if (!controller.signal.aborted && generation.current === id) {
        if (startup && error instanceof DOMException && error.name === "NotAllowedError") {
          setStartupBlocked(true);
          event("DONE");
          return;
        }
        const message = error instanceof Error ? error.message : "JarvisLuxTTS failed";
        const stopped = stopSpeaking();
        const stoppedId = generation.current;
        await stopped;
        if (generation.current === stoppedId) fail(message);
      }
    } finally {
      if (generation.current === id) {
        setSynthesizing(false);
        setStartupActive(false);
        synthesisId.current = null;
        if (abort.current === controller) abort.current = null;
      }
    }
  }
  async function playAnnouncement(artifactUrl: string, requiresVoice: boolean): Promise<"delivered" | "muted"> {
    if (!isShortcutAudioUrl(artifactUrl)) throw new Error("Invalid shortcut audio artifact.");
    if (requiresVoice && !currentPreferences.current.voice) return "muted";
    const stopping = stopSpeaking(), id = generation.current;
    await stopping;
    if (generation.current !== id) throw new DOMException("Announcement cancelled", "AbortError");
    if (requiresVoice && !currentPreferences.current.voice) return "muted";
    const controller = new AbortController();
    abort.current = controller;
    setSynthesizing(true);
    let player: HTMLAudioElement | null = null;
    let source = "";
    try {
      const response = await fetch(artifactUrl, { credentials: "same-origin", signal: controller.signal });
      if (!response.ok) throw new Error("Shortcut audio has expired. Its text is still available.");
      const blob = await response.blob();
      controller.signal.throwIfAborted();
      if (requiresVoice && !currentPreferences.current.voice) return "muted";
      source = URL.createObjectURL(blob);
      url.current = source;
      player = new Audio(source);
      audio.current = player;
      player.volume = playbackPreferences.current.volume;
      const sink = player as HTMLAudioElement & { setSinkId?: (id: string) => Promise<void> };
      if (playbackPreferences.current.output && sink.setSinkId) await sink.setSinkId(playbackPreferences.current.output);
      controller.signal.throwIfAborted();
      if (requiresVoice && !currentPreferences.current.voice) return "muted";
      audioBus.playback(player);
      const playback = player;
      await new Promise<void>((resolve, reject) => {
        const finish = (error?: unknown) => {
          controller.signal.removeEventListener("abort", onAbort);
          playback.onended = playback.onerror = null;
          if (error) reject(error); else resolve();
        };
        const onAbort = () => finish(new DOMException("Announcement cancelled", "AbortError"));
        controller.signal.addEventListener("abort", onAbort, { once: true });
        playback.onended = () => finish();
        playback.onerror = () => finish(new Error("Shortcut playback failed. Read the announcement on screen."));
        void playback.play().then(() => {
          if (generation.current === id && !controller.signal.aborted) {
            setSynthesizing(false);
            event("SPEAK");
          }
        }, finish);
      });
      return "delivered";
    } finally {
      player?.pause();
      if (player) player.src = "";
      if (source) URL.revokeObjectURL(source);
      if (url.current === source) url.current = "";
      if (player && audio.current === player) {
        audio.current = null;
        audioBus.detach();
      }
      if (generation.current === id) {
        setSynthesizing(false);
        if (abort.current === controller) abort.current = null;
        event("DONE");
      }
    }
  }
  useEffect(() => {
    if (audio.current) audio.current.volume = preferences.volume;
  }, [preferences.volume]);
  useEffect(
    () => () => {
      captureIntent.current = false;
      captureGeneration.current++;
      cancelled.current = true;
      generation.current++;
      abort.current?.abort();
      transcriptionAbort.current?.abort();
      if (synthesisId.current) void api("/audio/cancel", {
        method: "POST", body: JSON.stringify({ request_id: synthesisId.current }), keepalive: true,
      }).catch(() => {});
      if (recorder.current?.state === "recording") recorder.current.stop();
      stream.current?.getTracks().forEach((t) => t.stop());
      audio.current?.pause();
      if (url.current) URL.revokeObjectURL(url.current);
      if (timer.current) clearTimeout(timer.current);
      audioBus.detach();
    },
    [],
  );
  function stopAll() {
    cancelRecording();
    return stopSpeaking();
  }
  return {
    startupActive,
    startupBlocked,
    dismissStartup: () => setStartupBlocked(false),
    playStartup: () => speak("", true),
    recording,
    acquiring,
    synthesizing,
    prepare,
    startRecording,
    stopRecording,
    cancelRecording,
    speak,
    playAnnouncement,
    stopSpeaking,
    stopAll,
  };
}
