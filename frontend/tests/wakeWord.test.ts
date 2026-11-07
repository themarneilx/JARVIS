import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import type { Mock } from "vitest";
import { api } from "../src/services/api";
import {
  canListenForWake,
  extractWakeCommand,
  WakeWordListener,
} from "../src/services/wakeWord";
import type { WakeWordState } from "../src/services/wakeWord";

vi.mock("../src/services/api", () => ({ api: vi.fn() }));
vi.mock("../src/services/audioBus", () => ({ audioBus: { microphone: vi.fn(), detach: vi.fn() } }));

test.each([
  [true, false, false, false, true],
  [true, false, true, false, false],
  [true, false, true, true, true],
  [false, false, false, true, false],
  [false, false, true, true, false],
  [true, true, false, true, false],
  [true, true, true, true, false],
])(
  "wake policy enabled=%j suspended=%j hidden=%j background=%j returns %j",
  (enabled, suspended, hidden, background, allowed) => {
    expect(canListenForWake({ enabled, suspended, hidden, background })).toBe(allowed);
  },
);

test.each([
  ["Hey Jarvis", ""],
  ["Jarvis", ""],
  ["Jarvis, show my CPU", "show my CPU"],
  ["  HEY, JARVIS! Check my CPU.  ", "Check my CPU."],
  ["“Hey, Jarvis.”", ""],
  ["hey jarvis: what time is it?", "what time is it?"],
  ["Hey—Jarvis, open settings", "open settings"],
])("accepts a leading wake phrase in %j", (text, command) => {
  expect(extractWakeCommand(text)).toBe(command);
});

test.each([
  "",
  "They Jarvis",
  "Hey Travis",
  "Hey Jervis",
  "Hey Jarvison",
  "Jarvison",
  "I asked Jarvis earlier",
  "HeyJarvis",
  "Please say hey Jarvis",
  "I said, ‘hey Jarvis’",
])("does not wake from %j", (text) => {
  expect(extractWakeCommand(text)).toBeNull();
});

class Recorder {
  static instances: Recorder[] = [];
  static isTypeSupported = () => true;
  state = "inactive";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    Recorder.instances.push(this);
  }
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["encoded microphone audio"]) });
    this.onstop?.();
  }
}

let amplitude = 0;
class Context {
  static instances: Context[] = [];
  state = "running";
  onstatechange: (() => void) | null = null;
  source = { connect: vi.fn(), disconnect: vi.fn() };
  analyser = {
    fftSize: 1024,
    disconnect: vi.fn(),
    getFloatTimeDomainData(data: Float32Array) {
      data.fill(amplitude);
    },
  };
  constructor() {
    Context.instances.push(this);
  }
  createAnalyser() {
    return this.analyser;
  }
  createMediaStreamSource() {
    return this.source;
  }
  resume = vi.fn(async () => {});
  close = vi.fn(async () => {
    this.state = "closed";
  });
}

function microphone() {
  const track = { stop: vi.fn() };
  return { track, stream: { getTracks: () => [track] } };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

async function flush() {
  for (let i = 0; i < 8; i++) await Promise.resolve();
}

describe("wake microphone lifecycle", () => {
  let getUserMedia: ReturnType<typeof vi.fn>;
  let listener: WakeWordListener;
  let onWake: Mock<(command: string) => void>;
  let fail: Mock<(message: string) => void>;
  let onState: Mock<(state: WakeWordState) => void>;
  let page: EventTarget & { hidden: boolean };
  let browser: EventTarget;
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(api).mockReset();
    amplitude = 0;
    Recorder.instances = [];
    Context.instances = [];
    getUserMedia = vi.fn();
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    vi.stubGlobal("MediaRecorder", Recorder);
    vi.stubGlobal("AudioContext", Context);
    page = Object.assign(new EventTarget(), { hidden: false });
    browser = new EventTarget();
    vi.stubGlobal("document", page);
    vi.stubGlobal("window", browser);
    onWake = vi.fn();
    fail = vi.fn();
    onState = vi.fn();
    listener = new WakeWordListener({ onWake, fail, onState });
  });
  afterEach(() => {
    listener.stop();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  async function speakThenPause() {
    amplitude = 0.08;
    await vi.advanceTimersByTimeAsync(360);
    amplitude = 0;
    await vi.advanceTimersByTimeAsync(780);
  }

  test("immersive conversation submits a phrase without requiring a wake prefix", async () => {
    listener = new WakeWordListener({ onWake, fail, onState, conversation: true });
    const capture = microphone();
    getUserMedia.mockResolvedValue(capture.stream);
    vi.mocked(api).mockResolvedValue({ text: "What time is it?" });
    listener.start(""); await flush(); await speakThenPause();
    expect(onWake).toHaveBeenCalledExactlyOnceWith("What time is it?");
    expect(capture.track.stop).toHaveBeenCalledOnce();
  });
  test("immersive listening still acknowledges a bare wake phrase", async () => {
    listener = new WakeWordListener({ onWake, fail, onState, conversation: true });
    getUserMedia.mockResolvedValue(microphone().stream);
    vi.mocked(api).mockResolvedValue({ text: "Hey Jarvis" });
    listener.start(""); await flush(); await speakThenPause();
    expect(onWake).toHaveBeenCalledExactlyOnceWith("");
  });
  test("immersive cancellation ignores a late transcript including approval codes", async () => {
    listener = new WakeWordListener({ onWake, fail, onState, conversation: true });
    getUserMedia.mockResolvedValue(microphone().stream);
    const response = deferred<{ text: string }>();
    vi.mocked(api).mockReturnValue(response.promise);
    listener.start(""); await flush(); await speakThenPause();
    listener.stop(); response.resolve({ text: "approve 1234" }); await flush();
    expect(onWake).not.toHaveBeenCalled();
  });

  test("does not request permission until explicitly started", () => {
    expect(getUserMedia).not.toHaveBeenCalled();
    expect(Recorder.instances).toHaveLength(0);
  });

  test("does not request a hidden-tab microphone without background consent", async () => {
    page.hidden = true;
    listener.start("");
    await flush();
    expect(getUserMedia).not.toHaveBeenCalled();
    expect(Recorder.instances).toHaveLength(0);
  });

  test("keeps the same capture while hidden only with background consent", async () => {
    const capture = microphone();
    getUserMedia.mockResolvedValue(capture.stream);
    listener.start("", true);
    await flush();
    page.hidden = true;
    page.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(3000);
    expect(capture.track.stop).not.toHaveBeenCalled();
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(onState).toHaveBeenLastCalledWith({ listening: true, processing: false });
  });

  test("allows a hidden-tab wake transcript with explicit background consent", async () => {
    page.hidden = true;
    getUserMedia.mockResolvedValue(microphone().stream);
    vi.mocked(api).mockResolvedValue({ text: "Hey Jarvis, show my CPU." });
    listener.start("", true);
    await flush();
    await speakThenPause();
    expect(onWake).toHaveBeenCalledExactlyOnceWith("show my CPU.");
  });

  test.each(['mute', 'mute mic', 'mute microphone', 'unmute voice'])("accepts the standalone local audio command %s without a wake prefix", async text => {
    getUserMedia.mockResolvedValue(microphone().stream);
    vi.mocked(api).mockResolvedValue({ text });
    listener.start(''); await flush(); await speakThenPause();
    expect(onWake).toHaveBeenCalledExactlyOnceWith(text);
  });

  test("releases foreground-only capture immediately when hidden", async () => {
    const capture = microphone();
    getUserMedia.mockResolvedValue(capture.stream);
    listener.start("");
    await flush();
    page.hidden = true;
    page.dispatchEvent(new Event("visibilitychange"));
    expect(capture.track.stop).toHaveBeenCalledOnce();
    expect(Context.instances[0].close).toHaveBeenCalledOnce();
    expect(onState).toHaveBeenLastCalledWith({ listening: false, processing: false });
    expect(vi.getTimerCount()).toBe(0);
  });

  test("rejects microphone permission granted after a foreground tab becomes hidden", async () => {
    const pending = deferred<ReturnType<typeof microphone>["stream"]>();
    const capture = microphone();
    getUserMedia.mockReturnValue(pending.promise);
    listener.start("");
    page.hidden = true;
    pending.resolve(capture.stream);
    await flush();
    expect(capture.track.stop).toHaveBeenCalledOnce();
    expect(Recorder.instances).toHaveLength(0);
  });

  test("aborts foreground-only transcription when hidden and ignores its late result", async () => {
    getUserMedia.mockResolvedValue(microphone().stream);
    const response = deferred<{ text: string }>();
    vi.mocked(api).mockReturnValue(response.promise);
    listener.start("");
    await flush();
    await speakThenPause();
    const signal = vi.mocked(api).mock.calls[0][1]?.signal;
    page.hidden = true;
    page.dispatchEvent(new Event("visibilitychange"));
    expect(signal?.aborted).toBe(true);
    response.resolve({ text: "Hey Jarvis, show my CPU." });
    await flush();
    expect(onWake).not.toHaveBeenCalled();
    expect(getUserMedia).toHaveBeenCalledTimes(1);
  });

  test.each(["freeze", "pagehide"])("stops background capture on browser %s", async (event) => {
    const capture = microphone();
    getUserMedia.mockResolvedValue(capture.stream);
    listener.start("", true);
    await flush();
    (event === "freeze" ? page : browser).dispatchEvent(new Event(event));
    expect(capture.track.stop).toHaveBeenCalledOnce();
    expect(onState).toHaveBeenLastCalledWith({ listening: false, processing: false });
    expect(vi.getTimerCount()).toBe(0);
  });

  test("releases background capture if the browser suspends Web Audio", async () => {
    const capture = microphone();
    getUserMedia.mockResolvedValue(capture.stream);
    listener.start("", true);
    await flush();
    Context.instances[0].state = "suspended";
    Context.instances[0].onstatechange?.();
    expect(capture.track.stop).toHaveBeenCalledOnce();
    expect(onState).toHaveBeenLastCalledWith({ listening: false, processing: false });
    expect(vi.getTimerCount()).toBe(0);
  });

  test("stops a permission result that arrives after cancellation", async () => {
    const pending = deferred<ReturnType<typeof microphone>["stream"]>();
    const capture = microphone();
    getUserMedia.mockReturnValue(pending.promise);
    listener.start("");
    listener.stop();
    pending.resolve(capture.stream);
    await flush();
    expect(capture.track.stop).toHaveBeenCalledOnce();
    expect(Context.instances).toHaveLength(0);
    expect(Recorder.instances).toHaveLength(0);
    expect(api).not.toHaveBeenCalled();
  });

  test("cannot let an old permission result replace a newly enabled capture", async () => {
    const pending = deferred<ReturnType<typeof microphone>["stream"]>();
    const oldCapture = microphone();
    const currentCapture = microphone();
    getUserMedia.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(currentCapture.stream);
    listener.start("old-microphone");
    listener.stop();
    listener.start("new-microphone");
    await flush();
    pending.resolve(oldCapture.stream);
    await flush();
    expect(oldCapture.track.stop).toHaveBeenCalledOnce();
    expect(currentCapture.track.stop).not.toHaveBeenCalled();
    expect(Context.instances).toHaveLength(1);
    expect(Recorder.instances).toHaveLength(1);
    expect(onState).toHaveBeenLastCalledWith({ listening: true, processing: false });
  });

  test("does not start a recorder if cancellation occurs while Web Audio resumes", async () => {
    const resumed = deferred<void>();
    class SuspendedContext extends Context {
      state = "suspended";
      resume = vi.fn(() => resumed.promise);
    }
    vi.stubGlobal("AudioContext", SuspendedContext);
    const capture = microphone();
    getUserMedia.mockResolvedValue(capture.stream);
    listener.start("");
    await flush();
    listener.stop();
    resumed.resolve();
    await flush();
    expect(capture.track.stop).toHaveBeenCalledOnce();
    expect(Context.instances[0].close).toHaveBeenCalledOnce();
    expect(Recorder.instances).toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  test("keeps silence local with one capture and no transcription", async () => {
    const capture = microphone();
    getUserMedia.mockResolvedValue(capture.stream);
    listener.start("selected-microphone");
    listener.start("selected-microphone");
    await flush();
    await vi.advanceTimersByTimeAsync(23000);
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(getUserMedia).toHaveBeenCalledWith({
      audio: {
        deviceId: { exact: "selected-microphone" },
        echoCancellation: true,
        noiseSuppression: true,
      },
    });
    expect(api).not.toHaveBeenCalled();
    expect(onWake).not.toHaveBeenCalled();
    listener.stop();
    expect(capture.track.stop).toHaveBeenCalledOnce();
    expect(Context.instances[0].close).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  test("sends one bounded spoken phrase through the authenticated local STT API", async () => {
    const capture = microphone();
    const response = deferred<{ text: string }>();
    getUserMedia.mockResolvedValue(capture.stream);
    vi.mocked(api).mockReturnValue(response.promise);
    listener.start("");
    await flush();
    await speakThenPause();
    expect(api).toHaveBeenCalledOnce();
    const [path, options] = vi.mocked(api).mock.calls[0];
    expect(path).toBe("/audio/transcribe");
    expect(options?.method).toBe("POST");
    expect(options?.body).toBeInstanceOf(Blob);
    expect(options?.headers).toEqual({ "Content-Type": "audio/webm;codecs=opus" });
    expect(capture.track.stop).toHaveBeenCalledOnce();
    expect(Context.instances[0].close).toHaveBeenCalledOnce();
    expect(onState).toHaveBeenLastCalledWith({ listening: false, processing: true });
    await vi.advanceTimersByTimeAsync(10000);
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(api).toHaveBeenCalledOnce();
    response.resolve({ text: "Hey, Jarvis! Show my CPU." });
    await flush();
    expect(onWake).toHaveBeenCalledExactlyOnceWith("Show my CPU.");
    expect(onState).toHaveBeenLastCalledWith({ listening: false, processing: false });
    expect(getUserMedia).toHaveBeenCalledTimes(1);
  });

  test("discards a short noise burst without uploading it", async () => {
    getUserMedia.mockResolvedValue(microphone().stream);
    listener.start("");
    await flush();
    amplitude = 0.08;
    await vi.advanceTimersByTimeAsync(60);
    amplitude = 0;
    await vi.advanceTimersByTimeAsync(1700);
    expect(api).not.toHaveBeenCalled();
  });

  test("signals sustained speech once without waiting for a long phrase to finish", async () => {
    const onSpeechStart = vi.fn();
    listener = new WakeWordListener({ onWake, fail, onState, conversation: true, onSpeechStart });
    getUserMedia.mockResolvedValue(microphone().stream);
    listener.start(''); await flush();
    amplitude = .08; await vi.advanceTimersByTimeAsync(60);
    expect(onSpeechStart).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(7200);
    expect(onSpeechStart).toHaveBeenCalledOnce();
    expect(api).not.toHaveBeenCalled();
  });

  test("reports an empty follow-up phrase without submitting an agent command", async () => {
    const onEmptyPhrase = vi.fn();
    listener = new WakeWordListener({ onWake, fail, onState, conversation: true, onEmptyPhrase });
    getUserMedia.mockResolvedValue(microphone().stream);
    vi.mocked(api).mockResolvedValue({ text: '' });
    listener.start(''); await flush(); await speakThenPause();
    expect(onEmptyPhrase).toHaveBeenCalledOnce();
    expect(onWake).not.toHaveBeenCalled();
  });

  test("reports a wake phrase without a command as an empty command", async () => {
    getUserMedia.mockResolvedValue(microphone().stream);
    vi.mocked(api).mockResolvedValue({ text: "Hey, Jarvis." });
    listener.start("");
    await flush();
    await speakThenPause();
    expect(onWake).toHaveBeenCalledExactlyOnceWith("");
    expect(getUserMedia).toHaveBeenCalledTimes(1);
  });

  test("rejects an oversized encoded clip without uploading it", async () => {
    const capture = microphone();
    getUserMedia.mockResolvedValue(capture.stream);
    listener.start("");
    await flush();
    Recorder.instances[0].ondataavailable?.({ data: new Blob([new Uint8Array(3 * 1024 * 1024)]) });
    expect(api).not.toHaveBeenCalled();
    expect(fail).toHaveBeenCalledOnce();
    expect(capture.track.stop).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  test("ends a continuous spoken clip after ten seconds", async () => {
    getUserMedia.mockResolvedValue(microphone().stream);
    vi.mocked(api).mockReturnValue(new Promise(() => {}));
    listener.start("");
    await flush();
    amplitude = 0.08;
    await vi.advanceTimersByTimeAsync(9999);
    expect(api).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(api).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  test("rearms after ordinary speech without passing it to the assistant", async () => {
    getUserMedia.mockImplementation(async () => microphone().stream);
    vi.mocked(api).mockResolvedValue({ text: "I said hey Jarvis yesterday" });
    listener.start("");
    await flush();
    await speakThenPause();
    await flush();
    expect(onWake).not.toHaveBeenCalled();
    expect(getUserMedia).toHaveBeenCalledTimes(2);
    expect(Recorder.instances.filter((rec) => rec.state === "recording")).toHaveLength(1);
  });

  test.each([false, true])("aborts STT and ignores a late transcript after cancellation (background=%j)", async (background) => {
    getUserMedia.mockResolvedValue(microphone().stream);
    const response = deferred<{ text: string }>();
    vi.mocked(api).mockReturnValue(response.promise);
    listener.start("", background);
    await flush();
    await speakThenPause();
    const signal = vi.mocked(api).mock.calls[0][1]?.signal;
    listener.stop();
    expect(signal?.aborted).toBe(true);
    response.resolve({ text: "hey jarvis, do something" });
    await flush();
    expect(onWake).not.toHaveBeenCalled();
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  test("ignores old recorder callbacks after stopping", async () => {
    getUserMedia.mockResolvedValue(microphone().stream);
    listener.start("");
    await flush();
    amplitude = 0.08;
    await vi.advanceTimersByTimeAsync(360);
    const oldStop = Recorder.instances[0].onstop;
    listener.stop();
    oldStop?.();
    await flush();
    expect(api).not.toHaveBeenCalled();
    expect(onWake).not.toHaveBeenCalled();
    expect(getUserMedia).toHaveBeenCalledTimes(1);
  });

  test("stops on STT failure instead of repeatedly retrying", async () => {
    getUserMedia.mockResolvedValue(microphone().stream);
    vi.mocked(api).mockRejectedValue(new Error("Local transcription unavailable"));
    listener.start("");
    await flush();
    await speakThenPause();
    await flush();
    await vi.advanceTimersByTimeAsync(20000);
    expect(fail).toHaveBeenCalledOnce();
    expect(onWake).not.toHaveBeenCalled();
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });
});
