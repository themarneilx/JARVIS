import { api } from "./api";
import { audioBus } from "./audioBus";
import { parseAudioCommand } from "./audioCommands";

const POLL_MS = 60;
const SILENCE_MS = 700;
const MIN_SPEECH_MS = 180;
const IDLE_CLIP_MS = 1500;
const MAX_CLIP_MS = 10000;
const MAX_CLIP_BYTES = 2 * 1024 * 1024;
const SPEECH_RMS = 0.018;

export function canListenForWake({
  enabled,
  suspended,
  hidden,
  background,
}: {
  enabled: boolean;
  suspended: boolean;
  hidden: boolean;
  background: boolean;
}) {
  return enabled && !suspended && (!hidden || background === true);
}

export function extractWakeCommand(text: string): string | null {
  const normalized = text.normalize("NFKC").trim();
  const prefix = normalized.match(
    /^[\p{P}\s]*(?:hey[\p{P}\s]+)?jarvis(?=$|[\p{P}\s])[\p{P}\s]*/iu,
  );
  return prefix ? normalized.slice(prefix[0].length).trim() : null;
}

export function handleWakeCommand(
  command: string,
  acknowledge: (text: string) => void,
  submit: (text: string) => void,
) {
  if (command.trim()) submit(command.trim());
  else acknowledge("At your service, sir.");
}

export interface WakeWordState {
  listening: boolean;
  processing: boolean;
}

interface Callbacks {
  onWake: (command: string) => void;
  fail: (message: string) => void;
  onState: (state: WakeWordState) => void;
  conversation?: boolean;
  onAttention?: () => void;
  onSpeechStart?: () => void;
  onEmptyPhrase?: () => void;
}

interface Clip {
  recorder: MediaRecorder;
  chunks: Blob[];
  bytes: number;
  startedAt: number;
  lastSampleAt: number;
  lastSpeechAt: number;
  speechMs: number;
  closing: boolean;
  upload: boolean;
  timer: ReturnType<typeof setTimeout> | null;
}

interface ListeningRun {
  mic: string;
  background: boolean;
  removeLifecycleListeners: (() => void) | null;
  mime: string;
  stream: MediaStream | null;
  context: AudioContext | null;
  source: MediaStreamAudioSourceNode | null;
  analyser: AnalyserNode | null;
  samples: Float32Array<ArrayBuffer> | null;
  interval: ReturnType<typeof setInterval> | null;
  clip: Clip | null;
  request: AbortController | null;
}

// Local STT transcribes bounded phrases; this is not a dedicated wake-word model.
export class WakeWordListener {
  private run: ListeningRun | null = null;

  constructor(private readonly callbacks: Callbacks) {}

  start(mic: string, background = false) {
    if (
      this.run ||
      !canListenForWake({
        enabled: true,
        suspended: false,
        hidden: document.hidden,
        background,
      })
    )
      return;
    const run: ListeningRun = {
      mic,
      background,
      removeLifecycleListeners: null,
      mime: "",
      stream: null,
      context: null,
      source: null,
      analyser: null,
      samples: null,
      interval: null,
      clip: null,
      request: null,
    };
    this.run = run;
    const visibility = () => {
      this.canContinue(run);
    };
    const suspend = () => {
      if (this.run === run) this.stop();
    };
    document.addEventListener("visibilitychange", visibility);
    document.addEventListener("freeze", suspend);
    window.addEventListener("pagehide", suspend);
    run.removeLifecycleListeners = () => {
      document.removeEventListener("visibilitychange", visibility);
      document.removeEventListener("freeze", suspend);
      window.removeEventListener("pagehide", suspend);
    };
    void this.capture(run);
  }

  stop() {
    const run = this.run;
    this.run = null;
    if (run) {
      run.removeLifecycleListeners?.();
      run.removeLifecycleListeners = null;
      run.request?.abort();
      run.request = null;
      this.releaseCapture(run);
    }
    this.callbacks.onState({ listening: false, processing: false });
  }

  private canContinue(run: ListeningRun) {
    if (this.run !== run) return false;
    if (
      !canListenForWake({
        enabled: true,
        suspended: false,
        hidden: document.hidden,
        background: run.background,
      })
    ) {
      this.stop();
      return false;
    }
    return true;
  }

  private async capture(run: ListeningRun) {
    try {
      if (!this.canContinue(run)) return;
      if (
        !navigator.mediaDevices?.getUserMedia ||
        typeof MediaRecorder === "undefined" ||
        typeof AudioContext === "undefined"
      )
        throw new Error(
          "Wake listening is unavailable in this browser. Use text input.",
        );
      run.mime =
        ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"].find(
          (mime) => MediaRecorder.isTypeSupported(mime),
        ) || "";
      if (!run.mime)
        throw new Error(
          "No supported microphone recording format is available.",
        );
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          deviceId: run.mic ? { exact: run.mic } : undefined,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      if (!this.canContinue(run)) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      run.stream = stream;
      if (this.callbacks.conversation) audioBus.microphone(stream);
      const context = new AudioContext();
      run.context = context;
      if (context.state === "suspended") await context.resume();
      if (!this.canContinue(run)) return;
      if (context.state !== "running")
        throw new Error(
          "The browser suspended wake audio. Re-enable listening to retry, or use text input.",
        );
      context.onstatechange = () => {
        if (
          this.run === run &&
          run.context === context &&
          context.state !== "running"
        )
          this.failure(
            run,
            new Error(
              "The browser suspended wake audio. Re-enable listening to retry, or use text input.",
            ),
          );
      };
      run.analyser = context.createAnalyser();
      run.analyser.fftSize = 1024;
      run.samples = new Float32Array(run.analyser.fftSize);
      run.source = context.createMediaStreamSource(stream);
      run.source.connect(run.analyser);
      this.beginClip(run);
      run.interval = setInterval(() => this.sample(run), POLL_MS);
      this.callbacks.onState({ listening: true, processing: false });
    } catch (error) {
      this.failure(run, error);
    }
  }

  private beginClip(run: ListeningRun) {
    if (!this.canContinue(run) || !run.stream) return;
    const now = Date.now();
    const recorder = new MediaRecorder(run.stream, { mimeType: run.mime });
    const clip: Clip = {
      recorder,
      chunks: [],
      bytes: 0,
      startedAt: now,
      lastSampleAt: now,
      lastSpeechAt: now,
      speechMs: 0,
      closing: false,
      upload: false,
      timer: null,
    };
    run.clip = clip;
    recorder.ondataavailable = ({ data }) => {
      if (this.run !== run || run.clip !== clip || !data.size) return;
      clip.bytes += data.size;
      if (clip.bytes > (this.callbacks.conversation ? 12 * 1024 * 1024 : MAX_CLIP_BYTES)) {
        this.failure(
          run,
          new Error("Wake microphone clip exceeded its size limit."),
        );
        return;
      }
      clip.chunks.push(data);
    };
    recorder.onerror = () => {
      this.failure(
        run,
        new Error("Wake microphone recording failed. Use text input."),
      );
    };
    recorder.onstop = () => {
      void this.completeClip(run, clip);
    };
    recorder.start(250);
    clip.timer = setTimeout(() => this.finishClip(run, clip), this.callbacks.conversation ? 60000 : MAX_CLIP_MS);
  }

  private sample(run: ListeningRun) {
    const clip = run.clip;
    if (
      !this.canContinue(run) ||
      !clip ||
      clip.closing ||
      !run.analyser ||
      !run.samples
    )
      return;
    try {
      run.analyser.getFloatTimeDomainData(run.samples);
      let sum = 0;
      for (const value of run.samples) sum += value * value;
      const now = Date.now();
      if (Math.sqrt(sum / run.samples.length) >= SPEECH_RMS) {
        const previousSpeechMs = clip.speechMs;
        clip.speechMs += Math.min(now - clip.lastSampleAt, POLL_MS * 2);
        clip.lastSpeechAt = now;
        if (previousSpeechMs < MIN_SPEECH_MS && clip.speechMs >= MIN_SPEECH_MS)
          this.callbacks.onSpeechStart?.();
      }
      clip.lastSampleAt = now;
      const quiet = now - clip.lastSpeechAt >= SILENCE_MS;
      if (
        (clip.speechMs >= MIN_SPEECH_MS && quiet) ||
        (clip.speechMs < MIN_SPEECH_MS &&
          quiet &&
          now - clip.startedAt >= IDLE_CLIP_MS)
      )
        this.finishClip(run, clip);
    } catch (error) {
      this.failure(run, error);
    }
  }

  private finishClip(run: ListeningRun, clip: Clip) {
    if (!this.canContinue(run) || run.clip !== clip || clip.closing) return;
    clip.closing = true;
    clip.upload = clip.speechMs >= MIN_SPEECH_MS;
    if (clip.timer) clearTimeout(clip.timer);
    clip.timer = null;
    try {
      clip.recorder.stop();
    } catch (error) {
      this.failure(run, error);
    }
  }

  private async completeClip(run: ListeningRun, clip: Clip) {
    if (!this.canContinue(run) || run.clip !== clip) return;
    if (!clip.closing) {
      this.failure(
        run,
        new Error("Wake microphone recording stopped unexpectedly."),
      );
      return;
    }
    run.clip = null;
    this.detachRecorder(clip);
    if (!clip.upload || !clip.bytes) {
      try {
        this.beginClip(run);
      } catch (error) {
        this.failure(run, error);
      }
      return;
    }
    this.releaseCapture(run);
    const controller = new AbortController();
    run.request = controller;
    this.callbacks.onState({ listening: false, processing: true });
    const blob = new Blob(clip.chunks, { type: run.mime });
    clip.chunks = [];
    try {
      const result = await api<{ text: string }>("/audio/transcribe", {
        method: "POST",
        headers: { "Content-Type": run.mime },
        body: blob,
        signal: controller.signal,
      });
      if (!this.canContinue(run) || controller.signal.aborted) return;
      if (typeof result.text !== "string")
        throw new Error("Local transcription returned invalid text.");
      run.request = null;
      if (extractWakeCommand(result.text) !== null) this.callbacks.onAttention?.();
      const command = parseAudioCommand(result.text) ? result.text.trim() : this.callbacks.conversation
        ? (extractWakeCommand(result.text) ?? result.text.trim())
        : extractWakeCommand(result.text);
      if (command !== null && (command || extractWakeCommand(result.text) !== null)) {
        this.stop();
        this.callbacks.onWake(command);
      } else {
        if (this.callbacks.conversation) this.callbacks.onEmptyPhrase?.();
        this.callbacks.onState({ listening: false, processing: false });
        void this.capture(run);
      }
    } catch (error) {
      if (!controller.signal.aborted) this.failure(run, error);
    }
  }

  private detachRecorder(clip: Clip) {
    if (clip.timer) clearTimeout(clip.timer);
    clip.timer = null;
    clip.recorder.ondataavailable = null;
    clip.recorder.onstop = null;
    clip.recorder.onerror = null;
  }

  private releaseCapture(run: ListeningRun) {
    if (run.interval) clearInterval(run.interval);
    run.interval = null;
    if (run.clip) {
      const clip = run.clip;
      run.clip = null;
      this.detachRecorder(clip);
      if (clip.recorder.state !== "inactive") clip.recorder.stop();
      clip.chunks = [];
    }
    if (run.stream && this.callbacks.conversation) audioBus.detach();
    run.stream?.getTracks().forEach((track) => track.stop());
    run.stream = null;
    run.source?.disconnect();
    run.source = null;
    run.analyser?.disconnect();
    run.analyser = null;
    run.samples = null;
    if (run.context) {
      run.context.onstatechange = null;
      void run.context.close().catch(() => {});
    }
    run.context = null;
  }

  private failure(run: ListeningRun, error: unknown) {
    if (this.run !== run) return;
    this.stop();
    this.callbacks.fail(
      error instanceof Error
        ? error.message
        : "Wake listening failed. Use text input.",
    );
  }
}
