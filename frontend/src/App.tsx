import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState,
} from "react";
import { Icon } from "./components/Icon";
import { TelemetryRail } from "./components/TelemetryRail";
import { ChatPanel } from "./panels/ChatPanel";
import { HomeAccessPanel } from './panels/HomeAccessPanel';
import { SystemPanel, ApprovalPanel } from "./panels/SystemPanel";
import { MemoryPanel } from "./panels/MemoryPanel";
import { SettingsPanel } from "./panels/SettingsPanel";
import { ShortcutsPanel } from "./panels/ShortcutsPanel";
import { api, post, setCsrf, chat } from "./services/api";
import type {
  Action,
  Message,
  MonitorView,
  Status,
  Telemetry,
} from "./services/types";
import { phaseLabels, presets, transition } from "./state/machine";
import { useVoice } from "./hooks/useVoice";
import { useProcessingSound } from "./hooks/useProcessingSound";
import { parseAudioCommand, type AudioCommand } from "./services/audioCommands";
import { ListeningFrame } from "./components/ListeningFrame";
import { handleWakeCommand } from "./services/wakeWord";
import { useWakeWord } from "./hooks/useWakeWord";
import { useShortcutEvents } from "./hooks/useShortcutEvents";
import { parseConfirmation, type ReviewTicket } from "./services/confirmation";
import { PermissionDialog } from "./components/PermissionDialog";
import { PushToTalkButton } from "./components/PushToTalkButton";
import { readPreferences, PREFERENCES_KEY } from "./services/preferences";
const InformationPanel = lazy(() => import("./panels/InformationPanel"));
const MapPanel = lazy(() => import("./panels/MapPanel"));
const JarvisCore = lazy(() => import("./scenes/JarvisCore"));
function loadPreferences() {
  return readPreferences(
    localStorage,
    matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
}
function Login({ done }: { done: () => void }) {
  const [token, setToken] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <div className="pairing">
      <div className="pairing-symbol">
        <Icon name="core" size={52} />
      </div>
      <div className="small-label">LOCAL COMMAND CENTER</div>
      <h1>J.A.R.V.I.S.</h1>
      <p>Pair this browser with your local assistant.</p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            const r = await post<{ csrf: string }>("/auth/login", { token });
            setCsrf(r.csrf);
            setToken("");
            done();
          } catch (e) {
            setError(String(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        <label htmlFor="pairing-token">Local pairing token</label>
        <input
          id="pairing-token"
          type="password"
          autoComplete="off"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          required
        />
        <button className="primary" disabled={busy}>
          {busy ? "Connecting…" : "Connect local session"}
        </button>
      </form>
      <p className="muted">
        Read the pairing token with <code>bash scripts/token.sh</code> in the
        project terminal. It remains on this machine.
      </p>
      {error ? (
        <p role="alert" className="warning">
          {error}
        </p>
      ) : null}
    </div>
  );
}
export default function App() {
  const [authenticated, setAuthenticated] = useState(false),
    [checking, setChecking] = useState(true),
    [tab, setTab] = useState("command");
  const [immersive, setImmersive] = useState(false);
  const [attention, setAttention] = useState(0);
  useEffect(() => {
    if (!attention) return;
    const timer = setTimeout(() => setAttention(0), 3200);
    return () => clearTimeout(timer);
  }, [attention]);
  const [informationOpen, setInformationOpen] = useState(false);
  const [informationReceipt, setInformationReceipt] = useState<string | null>(null);
  const [mapLocating, setMapLocating] = useState(false);
  const [mapOpen, setMapOpen] = useState(false);
  const [mapReceipt, setMapReceipt] = useState<string | null>(null);
  const [handsFree, setHandsFree] = useState(false);
  const [awaitingWakeCommand, setAwaitingWakeCommand] = useState(false);
  const [wakeCommandStarted, setWakeCommandStarted] = useState(false);
  const wakeCommandDeadline = useRef(0);
  const [chatExpanded, setChatExpanded] = useState(false);
  const [speakerTail, setSpeakerTail] = useState(false);
  const [shortcutActive, setShortcutActive] = useState(false);
  const [desktopPlaying, setDesktopPlaying] = useState(false);
  const bootAttempted = useRef(false);
  const entryButton = useRef<HTMLButtonElement>(null);

  const overlayOpen = immersive || mapOpen || informationOpen;
  useEffect(() => {
    if (!overlayOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previous; };
  }, [overlayOpen]);
  const [preferences, setPreferences] = useState(loadPreferences),
    [phase, event] = useReducer(transition, "idle");
  const [data, setData] = useState<Telemetry | null>(null),
    [status, setStatus] = useState<Status | null>(null),
    [actions, setActions] = useState<Action[]>([]),
    [reviews, setReviews] = useState<ReviewTicket[]>([]),
    [reviewId, setReviewId] = useState<string | null>(null),
    [resolving, setResolving] = useState(false),
    [confirmationTranscript, setConfirmationTranscript] = useState(""),
    [wakeCycle, setWakeCycle] = useState(0),
    [wakeAcknowledgement, setWakeAcknowledgement] = useState(""),
    [monitor, setMonitor] = useState<MonitorView | null>(null);
  const seenReviews = useRef(new Set<string>());
  const announcedReviews = useRef(new Set<string>());
  const review = reviews.find((item) => item.id === reviewId);
  const [history, setHistory] = useState<number[]>([]),
    [input, setInput] = useState(""),
    [messages, setMessages] = useState<Message[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice,setNotice] = useState(''),
    [memoryRevision,setMemoryRevision] = useState(0),
    [activity, setActivity] = useState(""),
    [time, setTime] = useState(new Date());
  const abort = useRef<AbortController | null>(null),
    session = useRef<string | null>(sessionStorage.getItem("jarvis.session")),
    epoch = useRef(Number(sessionStorage.getItem("jarvis.memory_epoch") || 0));
  const response = useRef(""),
    sendRef = useRef<(s: string) => void>(() => {}),
    busyRef = useRef(false);
  const fail = useCallback((s: string) => {
    setError(s.replace(/^Error: /, ""));
    event("FAIL");
  }, []);
  const onTranscript = useCallback(
    (s: string) => {
      setInput(s);
      if (parseAudioCommand(s)) sendRef.current(s);
      else if (review) {
        setConfirmationTranscript(s);
        if (parseConfirmation(s)) sendRef.current(s);
      } else if (preferences.autoSubmit) sendRef.current(s);
    },
    [preferences.autoSubmit, review?.id],
  );
  const voice = useVoice(preferences, event, onTranscript, fail);
  useProcessingSound(
    (phase === "thinking" || phase === "executing_tool" || voice.synthesizing) &&
      phase !== "speaking" && !voice.startupActive && !voice.recording && !voice.acquiring,
    authenticated && preferences.processingSound, preferences.volume, preferences.output,
  );
  useEffect(() => {
    if (authenticated && preferences.voice) void voice.prepare();
  }, [authenticated, preferences.voice, voice.prepare]);
  useEffect(() => {
    if (authenticated && !bootAttempted.current) {
      bootAttempted.current = true;
      if (preferences.startupSound) void voice.playStartup();
    }
  }, [authenticated]);
  useEffect(() => {
    if (phase !== "speaking" && !voice.synthesizing) {
      const timer = setTimeout(() => setSpeakerTail(false), 900);
      return () => clearTimeout(timer);
    }
    setSpeakerTail(true);
  }, [phase, voice.synthesizing]);
  useEffect(() => {
    const changed = () => {
      if (!document.fullscreenElement) setImmersive(false);
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !document.fullscreenElement) setImmersive(false);
    };
    document.addEventListener("fullscreenchange", changed);
    window.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("fullscreenchange", changed);
      window.removeEventListener("keydown", escape);
    };
  }, []);
  const wake = useWakeWord({
    enabled: authenticated && !preferences.microphoneMuted && (immersive ? handsFree : preferences.wakeWord),
    conversation: immersive && handsFree && (preferences.immersiveMicMode === 'always' || awaitingWakeCommand),
    background: !immersive && preferences.backgroundWake,
    suspended:
      busy ||
      speakerTail ||
      resolving ||
      voice.recording ||
      voice.acquiring ||
      voice.synthesizing ||
      shortcutActive ||
      desktopPlaying ||
      phase === "speaking" ||
      phase === "transcribing",
    mic: preferences.mic,
    restartKey: wakeCycle,
    onAttention: () => setAttention(Date.now()),
    onSpeechStart: () => {
      if (awaitingWakeCommand && wakeCommandDeadline.current > performance.now()) setWakeCommandStarted(true);
    },
    onEmptyPhrase: () => {
      if (awaitingWakeCommand) { setAwaitingWakeCommand(false); setAttention(0); }
    },
    onWake: (command) => {
      setWakeCycle((current) => current + 1);
      if (immersive && handsFree) {
        wake.stop();
        if (preferences.immersiveMicMode === 'wake') {
          wakeCommandDeadline.current = 0;
          setWakeCommandStarted(false);
          setAwaitingWakeCommand(!command.trim());
        }
        handleWakeCommand(command, (text) => {
          setWakeAcknowledgement(text);
          if (preferences.voice && preferences.autoSpeak) void voice.speak(text);
        }, (text) => {
          if (review) setConfirmationTranscript(text);
          sendRef.current(text);
        });
        return;
      }
      handleWakeCommand(command, (text) => {
        wake.stop();
        setWakeAcknowledgement(text);
        if (preferences.voice && preferences.autoSpeak) void voice.speak(text);
      }, (text) => {
        setWakeAcknowledgement("");
        if (review) setConfirmationTranscript(text);
        sendRef.current(text);
      });
    },
    fail: (message) => {
      setHandsFree(false);
      setPreferences((current) => ({ ...current, wakeWord: false, backgroundWake: false }));
      fail(message);
    },
  });
  const shortcuts = useShortcutEvents({
    authenticated,
    voiceEnabled: preferences.voice,
    available: preferences.volume > 0,
    humanBusy: () => busyRef.current || (preferences.volume === 0 && !document.hidden),
    busy: busy || busyRef.current || resolving || !!review || voice.recording || voice.acquiring || voice.synthesizing || voice.startupActive || wake.processing || speakerTail || (phase !== "idle" && phase !== "error"),
    pauseWake: () => { wake.stop(); setAwaitingWakeCommand(false); },
    play: voice.playAnnouncement,
    stopPlayback: voice.stopSpeaking,
    activeChanged: setShortcutActive,
    desktopChanged: setDesktopPlaying,
  });
  useEffect(() => {
    setAwaitingWakeCommand(false);
    setWakeCommandStarted(false);
    setAttention(0);
  }, [immersive, handsFree, preferences.microphoneMuted, preferences.immersiveMicMode]);
  useEffect(() => {
    if (!awaitingWakeCommand) { wakeCommandDeadline.current = 0; return; }
    if (wakeCommandStarted) return;
    if (!wakeCommandDeadline.current) {
      if (!wake.listening) return;
      wakeCommandDeadline.current = performance.now() + 5000;
    }
    const timer = setTimeout(() => setAwaitingWakeCommand(false), Math.max(0, wakeCommandDeadline.current - performance.now()));
    return () => clearTimeout(timer);
  }, [awaitingWakeCommand, wake.listening, wakeCommandStarted]);
  useEffect(() => {
    const hide = () => { if (document.hidden) { setAwaitingWakeCommand(false); setAttention(0); } };
    document.addEventListener('visibilitychange', hide);
    return () => document.removeEventListener('visibilitychange', hide);
  }, []);
  const immersiveListening = immersive && handsFree && !preferences.microphoneMuted;
  const immersiveCaption = !immersiveListening ? 'MICROPHONE MUTED'
    : wake.processing ? 'TRANSCRIBING LOCALLY'
    : !wake.listening ? 'MIC PAUSED · ' + phaseLabels[phase].toUpperCase()
    : preferences.immersiveMicMode === 'wake' && !awaitingWakeCommand ? 'SAY “JARVIS” OR “HEY JARVIS”'
    : 'LISTENING · SPEAK NATURALLY';
  const listeningFrameMode = preferences.microphoneMuted ? null
    : immersiveListening && awaitingWakeCommand && wake.listening ? 'listening'
    : attention ? 'attention' : null;
  const displayPhase = phase === "idle" && wake.listening ? "listening"
    : phase === "idle" && wake.processing ? "transcribing" : phase;
  function enterImmersive() {
    setTab("command");
    setChatExpanded(false);
    setImmersive(true);
    setHandsFree(true);
    if (!document.fullscreenElement)
      void document.documentElement.requestFullscreen?.().catch(() => {});
  }
  function leaveImmersive() {
    setImmersive(false);
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
    requestAnimationFrame(() => entryButton.current?.focus());
  }
  const refreshReviews = useCallback(async () => {
    const next = await api<ReviewTicket[]>("/reviews");
    setReviews(next);
  }, []);
  useEffect(() => {
    if (!authenticated) return;
    void refreshReviews().catch(() => {});
    const timer = setInterval(() => {
      if (!document.hidden) void refreshReviews().catch(() => {});
    }, 4000);
    return () => clearInterval(timer);
  }, [authenticated, refreshReviews]);
  useEffect(() => {
    setConfirmationTranscript("");
  }, [reviewId]);
  useEffect(() => {
    if (reviewId && reviews.some((item) => item.id === reviewId)) return;
    const next = reviews.find(
      (item) => !seenReviews.current.has(item.source + ":" + item.proposal_id),
    );
    if (next) {
      seenReviews.current.add(next.source + ":" + next.proposal_id);
      setError("");
      setReviewId(next.id);
    } else setReviewId(null);
  }, [reviews, reviewId]);
  useEffect(() => {
    if (
      review &&
      preferences.voice &&
      preferences.autoSpeak &&
      !busy &&
      !resolving &&
      !voice.recording &&
      !voice.acquiring &&
      !voice.synthesizing &&
      !shortcutActive &&
      !desktopPlaying &&
      phase === "idle" &&
      review.expires * 1000 > Date.now() + 10000 &&
      !announcedReviews.current.has(review.id)
    )
      readPermission();
  }, [
    review?.id,
    preferences.voice,
    preferences.autoSpeak,
    busy,
    resolving,
    voice.recording,
    voice.acquiring,
    voice.synthesizing,
    shortcutActive,
    desktopPlaying,
    phase,
  ]);
  const refresh = useCallback(async () => {
    const results = await Promise.allSettled([
      api<Telemetry>("/telemetry"),
      api<Action[]>("/actions"),
      api<MonitorView>("/monitoring"),
    ]);
    if (results[0].status === "fulfilled") {
      const next = results[0].value;
      setData((previous) => {
        if (previous?.sampled_at !== next.sampled_at)
          setHistory((h) => [...h, next.cpu_percent].slice(-28));
        return next;
      });
    }
    if (results[1].status === "fulfilled") setActions(results[1].value);
    if (results[2].status === "fulfilled") setMonitor(results[2].value);
  }, []);
  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await api<Status>("/status"));
    } catch (e) {
      setError(String(e));
    }
  }, []);
  useEffect(() => {
    void api<{ csrf: string }>("/auth/session")
      .then((r) => {
        setCsrf(r.csrf);
        setAuthenticated(true);
      })
      .catch(() => {})
      .finally(() => setChecking(false));
  }, []);
  useEffect(() => {
    if (!authenticated || !session.current) return;
    void api<{
      messages: {
        id: string;
        role: "user" | "assistant";
        text: string;
        timestamp?: string | number;
      }[];
      epoch: number;
    }>(`/conversations/${session.current}`)
      .then((result) => {
        epoch.current = result.epoch;
        setMessages(
          result.messages.map((m) => ({
            id: m.id,
            role: m.role,
            text: m.text,
            at:
              typeof m.timestamp === "number"
                ? m.timestamp * 1000
                : Date.parse(m.timestamp || "") || Date.now(),
          })),
        );
      })
      .catch(() => {
        session.current = null;
        sessionStorage.removeItem("jarvis.session");
      });
  }, [authenticated]);
  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!authenticated) return;
    void refresh();
    void refreshStatus();
    const timer = setInterval(() => {
        if (!document.hidden) void refresh();
      }, presets[preferences.quality].poll),
      health = setInterval(() => {
        if (!document.hidden) void refreshStatus();
      }, 30000);
    return () => {
      clearInterval(timer);
      clearInterval(health);
    };
  }, [authenticated, preferences.quality, refresh, refreshStatus]);
  useEffect(() => {
    try {
      localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences));
    } catch {}
  }, [preferences]);
  function newSession() {
    session.current = null;
    sessionStorage.removeItem("jarvis.session");
    setMessages([]);
    setActivity("");
    setError("");
    setNotice('');
    event("DONE");
    epoch.current = status?.memory_epoch ?? epoch.current;
  }
  function memoryChanged() {
    newSession();
    setMemoryRevision(value=>value+1);
    void refreshStatus();
    setNotice(
      "Memory updated. A fresh conversation will load the current native memory.",
    );
  }
  async function send(value?: string) {
    const text = (value ?? input).trim();
    if (!text) return;
    const audioCommand = parseAudioCommand(text);
    if (audioCommand) { applyAudioCommand(audioCommand); setInput(""); return; }
    if (shortcuts.isBusy()) {
      setNotice("A shortcut announcement is active. Stop it before starting a conversation.");
      return;
    }
    if (busyRef.current || voice.recording || voice.acquiring) return;
    setAwaitingWakeCommand(false);
    setWakeAcknowledgement("");
    setNotice('');
    const confirmation = parseConfirmation(text);
    if (confirmation) {
      if (!review) {
        fail("Open the pending permission request before confirming its code.");
        return;
      }
      if (confirmation.code !== review.code) {
        fail(
          "That code does not match the displayed proposal. Review its code and try again.",
        );
        return;
      }
      setInput("");
      await resolveReview(confirmation.approve);
      return;
    }
    wake.stop();
    voice.dismissStartup();
    const silence = voice.stopSpeaking();
    if (preferences.voice && preferences.autoSpeak)
      void silence.then(() => voice.prepare());
    setError("");
    setInput("");
    busyRef.current = true;
    setBusy(true);
    setActivity("Hermes is preparing the local agent turn…");
    event("SEND");
    const id = crypto.randomUUID();
    response.current = "";
    const controller = new AbortController();
    abort.current = controller;
    setMessages((previous) => [
      ...previous,
      { id: crypto.randomUUID(), role: "user", text, at: Date.now() },
      { id, role: "assistant", text: "", at: Date.now() },
    ]);
    try {
      await chat(
        text,
        session.current,
        epoch.current,
        controller.signal,
        (item) => {
          if (item.type === "session" && item.session_id) {
            session.current = item.session_id;
            sessionStorage.setItem("jarvis.session", item.session_id);
            if (item.epoch != null) {
              epoch.current = item.epoch;
              sessionStorage.setItem("jarvis.memory_epoch", String(item.epoch));
            }
          }
          if (item.type === "tool") {
            event("TOOL");
            setActivity(item.label || "Running a reviewed tool…");
          }
          if (item.type === "delta" && item.text) {
            event("TOKEN");
            setActivity("");
            response.current += item.text;
            const current = response.current;
            setMessages((previous) =>
              previous.map((m) => (m.id === id ? { ...m, text: current } : m)),
            );
          }
          if (item.type === "map_locating") {
            setMapLocating(true); setMapReceipt(null); setMapOpen(true); setInformationOpen(false);
          }
          if (item.type === "map" && item.receipt) {
            setMapReceipt(item.receipt); setMapOpen(true); setInformationOpen(false); setTab("command");
          }
          if (item.type === "information" && item.receipt) {
            setInformationReceipt(item.receipt); setInformationOpen(true); setMapOpen(false);
          }
          if (item.type === "error")
            throw new Error(item.message || "Agent failed");
          if (item.type === "done") {
            setActivity("");
            event("DONE");
          }
        },
      );
      if (response.current && preferences.voice && preferences.autoSpeak)
        void voice.speak(response.current);
    } catch (e) {
      if (!controller.signal.aborted) {
        fail(e instanceof Error ? e.message : "Agent request failed");
        setInput(text);
      } else event("CANCEL");
      setMessages((previous) =>
        previous.map((m) =>
          m.id === id
            ? {
                ...m,
                failed: true,
                text:
                  m.text ||
                  "No completed assistant response. Start a new conversation before retrying.",
              }
            : m,
        ),
      );
      session.current = null;
      sessionStorage.removeItem("jarvis.session");
    } finally {
      busyRef.current = false;
      setBusy(false);
      setMapLocating(false);
      setActivity("");
      void refresh();
      void refreshReviews().catch(() => {});
    }
  }
  sendRef.current = (s) => void send(s);
  async function resolveReview(approve: boolean) {
    if (!review || resolving || busyRef.current) return;
    wake.stop();
    setResolving(true);
    try {
      await voice.stopAll();
      const result = await post<{
        status: string;
        kind?: string;
        new_session_required?: boolean;
        action?: 'add'|'patch'|'remove';
        target?: 'user'|'memory';
      }>(`/reviews/${review.id}/resolve`, { approve, code: review.code });
      if (result.new_session_required) memoryChanged();
      setReviewId(null);
      await Promise.all([refresh(), refreshReviews()]);
      const message =
        result.status === "executed"
          ? result.kind === 'terminal'
            ? "Kitty accepted the launch. Check the terminal for command output and completion."
            : result.kind === 'launch' ? "The desktop launcher accepted the request." : "The approved operation completed."
          : result.status === "failed"
            ? "The approved operation failed. Inspect the System panel for its result."
            : result.status === 'approved'
              ? review.source === 'shortcut'
                ? "Shortcut authorized and created. Open Shortcuts to review its schedule and delivery status."
                : result.action === 'remove'
                ? `The memory entry was removed from ${result.target==='user'?'USER.md':result.target==='memory'?'MEMORY.md':'Hermes memory'}.`
                : `The preference was saved to ${result.target==='user'?'USER.md':result.target==='memory'?'MEMORY.md':'Hermes memory'}.`
              : result.status==='rejected' ? "The proposal is rejected." : 'The operation outcome could not be confirmed.';
      if(result.status==='failed')setError(message);
      else setNotice(message);
      if (preferences.voice && preferences.autoSpeak) void voice.speak(message);
    } catch (e) {
      fail(String(e));
      void refreshReviews().catch(() => {});
    } finally {
      setResolving(false);
    }
  }
  function readPermission() {
    if (!review || shortcuts.isBusy()) return;
    announcedReviews.current.add(review.id);
    wake.stop();
    voice.cancelRecording();
    void voice.speak(
      `Your permission is required to ${review.title} for ${review.target}. Review the details on screen. Say approve ${review.code.split("").join(" ")}, or reject ${review.code.split("").join(" ")}.`,
    );
  }
  function startRecording() {
    if (preferences.microphoneMuted || shortcuts.isBusy()) return;
    wake.stop();
    void voice.startRecording();
  }
  function applyAudioCommand(command: AudioCommand) {
    setError("");
    if (command === "voice_mute" || command === "voice_unmute") {
      const muted = command === "voice_mute";
      if (muted) void voice.stopSpeaking();
      setPreferences(current => ({ ...current, voice: !muted }));
      setNotice(muted ? "Jarvis voice muted. System audio is unchanged." : "Jarvis voice enabled.");
    } else {
      const muted = command === "microphone_mute";
      if (muted) { wake.stop(); voice.cancelRecording(); }
      setPreferences(current => ({ ...current, microphoneMuted: muted }));
      setNotice(muted ? "Jarvis microphone muted. Unmute it on screen or type ‘unmute microphone’. System audio is unchanged." : "Jarvis microphone enabled.");
    }
  }
  function cancel() {
    const id = session.current;
    if (id)
      void post(`/chat/${id}/cancel`, {})
        .then(() =>
          setError(
            "Stream cancelled. Remote inference cancellation depends on the connected Hermes API.",
          ),
        )
        .catch(() => {});
    abort.current?.abort();
    session.current = null;
    sessionStorage.removeItem("jarvis.session");
    event("CANCEL");
  }
  async function lockSession() {
    leaveImmersive();
    setHandsFree(false);
    setMapOpen(false);
    setInformationOpen(false);
    wake.stop();
    if (shortcuts.isBusy()) await shortcuts.stop();
    const stopping = voice.stopAll();
    if (busyRef.current) cancel();
    abort.current?.abort();
    setAuthenticated(false);
    await stopping;
    await post("/auth/logout", {}).catch(() => {});
    setMessages([]);
  }
  if (checking)
    return (
      <div className="boot-screen">
        <Icon name="core" size={36} />
        <span>Establishing local channel…</span>
      </div>
    );
  if (!authenticated) return <Login done={() => setAuthenticated(true)} />;
  return (
    <div className={`app-shell ${immersive ? "immersive" : ""} ${chatExpanded ? "chat-expanded" : ""} ${mapOpen || informationOpen ? "map-active" : ""}`}>
      <ListeningFrame mode={listeningFrameMode} reduced={preferences.reducedMotion} pulse={attention} />
      <aside className="navigation">
        <a
          className="brand-mark"
          href="#command"
          aria-label="Command center"
          onClick={() => setTab("command")}
        >
          <Icon name="core" size={28} />
        </a>
        <nav aria-label="Main navigation">
          {[
            ["command", "core", "Command center"],
            ["system", "system", "System"],
            ["memory", "memory", "Memory"],
            ["shortcuts", "shortcuts", "Shortcuts"],
            ["settings", "settings", "Settings"],
          ].map(([key, icon, label]) => (
            <button
              key={key}
              aria-label={label}
              title={label}
              aria-current={tab === key ? "page" : undefined}
              className={tab === key ? "selected" : ""}
              onClick={() => setTab(key)}
            >
              <Icon name={icon} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <button
          className="logout"
          title="Lock session"
          aria-label="Lock session"
          onClick={() => void lockSession()}
        >
          <Icon name="power" />
        </button>
        <span className="nav-version">J / 01</span>
      </aside>
      <main>
        <header className="topbar">
          <div className="wordmark">
            J.A.R.V.I.S.<span>PERSONAL INTELLIGENCE SYSTEM</span>
          </div>
          <button ref={entryButton} className="immersive-entry" onClick={enterImmersive}
            title="Fullscreen core with hands-free local listening">Enter immersive mode</button>
          <div className="topbar-views"><button onClick={() => {setMapOpen(true);setInformationOpen(false);}}>Map</button><button onClick={() => {setInformationOpen(true);setMapOpen(false);}}>News & markets</button></div>
          <div className="topbar-status">
            <i
              className={`status-dot ${status?.agent.connected ? "" : "warn"}`}
            />
            <span>
              {status?.agent.connected
                ? "HERMES CONNECTED"
                : "AGENT SETUP REQUIRED"}
            </span>
          </div>
          <div className="clock">
            <time>{time.toLocaleTimeString("en-GB",{timeZone:status?.online?.timezone??'Asia/Manila'})}</time>
            <span>
              {time
                .toLocaleDateString("en-GB", {
                  day: "2-digit",
                  month: "short",
                  year: "numeric",
                  timeZone: status?.online?.timezone??'Asia/Manila',
                })
                .toUpperCase()}
              {' · '+(status?.online?.timezone??'Asia/Manila')}
            </span>
          </div>
        </header>
        {preferences.wakeWord || preferences.microphoneMuted || !preferences.voice || reviews.length ? (
          <div className="interaction-status">
            {preferences.microphoneMuted ? <><span role="status">Jarvis microphone muted</span><button onClick={() => applyAudioCommand("microphone_unmute")}>Unmute Jarvis microphone</button></> : null}
            {!preferences.voice ? <><span role="status">Jarvis voice muted</span><button onClick={() => applyAudioCommand("voice_unmute")}>Unmute Jarvis voice</button></> : null}
            {preferences.wakeWord ? (
              <>
                <span role="status">
                  Wake microphone:{" "}
                  {wake.listening
                    ? "listening for Hey Jarvis or Jarvis"
                    : wake.processing
                      ? "transcribing locally"
                      : "paused"}
                  {preferences.backgroundWake?' · background allowed':''}
                </span>
                {wakeAcknowledgement ? <span role="status">{wakeAcknowledgement}</span> : null}
                <button
                  onClick={() => {
                    wake.stop();
                    setPreferences((current) => ({
                      ...current,
                      wakeWord: false,
                      backgroundWake: false,
                    }));
                  }}
                >
                  Stop wake listening
                </button>
              </>
            ) : null}
            {reviews.length ? (
              <button
                className="permission-trigger"
                onClick={() => setReviewId(reviews[0].id)}
              >
                Review permissions ({reviews.length})
              </button>
            ) : null}
          </div>
        ) : null}
        {notice ? <div className="notice result-notice" role="status"><span>{notice}</span><button aria-label="Dismiss status" onClick={()=>setNotice('')}>×</button></div>:null}
        {shortcuts.error && tab === "shortcuts" ? <div className="notice warning" role="status">Shortcut delivery: {shortcuts.error}</div> : null}
        {shortcuts.announcement || shortcuts.desktopPlaying ? <aside className="shortcut-announcement" aria-label="Shortcut announcement" aria-live="polite">
          <div><span className="small-label">{shortcuts.desktopPlaying ? "DESKTOP ANNOUNCEMENT IN PROGRESS" : "SHORTCUT ANNOUNCEMENT"}</span><strong>{shortcuts.announcement?.name || "Desktop announcement"}</strong>
            <p>{shortcuts.announcement?.text || (shortcuts.desktopPlaying ? "Desktop delivery is preparing or playing. Wake listening is paused." : "Waiting for an available delivery channel.")}</p>
            <span className="muted">{shortcuts.announcement?.status}{shortcuts.announcement?.delivery ? ` · ${shortcuts.announcement.delivery}` : ""}{!preferences.voice ? " · Jarvis voice muted; a requested chime can still play" : ""}{!preferences.volume ? " · Browser volume is zero" : ""}</span>
            {shortcuts.announcement?.error ? <p className="warning">{shortcuts.announcement.error}</p> : null}
          </div>
          <div className="button-row">{shortcuts.announcement && ["pending", "preparing", "playing"].includes(shortcuts.announcement.status) ? <button onClick={() => void shortcuts.stop()}>Stop announcement</button> : null}<button onClick={() => { leaveImmersive(); setTab("shortcuts"); }}>View shortcuts</button>{!shortcutActive && !shortcuts.desktopPlaying ? <button onClick={shortcuts.dismiss}>Dismiss</button> : null}</div>
        </aside> : null}
        {error ? (
          <div className="error-banner" role="alert">
            <span>{error}</span>
            <button
              onClick={() => {
                setError("");
                if (phase === "error") event("DONE");
              }}
              aria-label="Dismiss message"
            >
              ×
            </button>
          </div>
        ) : null}
        {voice.startupBlocked && preferences.startupSound ? <div className="startup-prompt">
          <button onClick={() => { wake.stop(); void voice.playStartup(); }}>Play welcome sound</button>
          <button aria-label="Skip welcome sound" onClick={voice.dismissStartup}>Skip</button>
        </div> : null}
        <div className="command-view" hidden={tab !== "command"}>
            <div className="command-heading">
              <div>
                <div className="small-label">COMMAND CENTER</div>
                <h1>Your systems. In perspective.</h1>
              </div>
              <div className="connection-tag">
                LOCAL-FIRST<span>ARCH / WAYLAND</span>
              </div>
            </div>
            <div className="command-layout">
              <TelemetryRail data={data} history={history} />
              <section className="core-column">
                <Suspense
                  fallback={
                    <div className="core-loading">
                      Initializing holographic display…
                    </div>
                  }
                >
                  <JarvisCore
                    phase={displayPhase}
                    immersive={immersive}
                    active={tab === "command"}
                    quality={preferences.quality}
                    reducedMotion={preferences.reducedMotion}
                  />
                </Suspense>
                <div className="core-state" aria-live="polite">
                  <span
                    className={`status-dot ${phase === "error" ? "warn" : ""}`}
                  />
                  {phaseLabels[phase]}
                  <span className="phase-code">
                    {phase.replace("_", " ").toUpperCase()}
                  </span>
                </div>
                <div className="voice-dock">
                  <PushToTalkButton
                    className={`microphone ${voice.recording ? "recording" : ""}`}
                    disabled={preferences.microphoneMuted || busy || shortcutActive || desktopPlaying || phase === "transcribing"}
                    label="Hold microphone to speak"
                    recording={voice.recording}
                    start={startRecording}
                    finish={voice.stopRecording}
                    cancel={voice.cancelRecording}
                  >
                    <Icon name="mic" size={23} />
                  </PushToTalkButton>
                  <div>
                    <strong>
                      {preferences.microphoneMuted ? "Jarvis microphone muted" : voice.recording
                        ? "Listening… release to transcribe"
                        : phase === "transcribing"
                          ? "Processing your voice"
                          : voice.synthesizing
                            ? "Preparing JarvisLuxTTS audio"
                            : voice.acquiring ? "Requesting microphone access…" : "Hold to speak to J.A.R.V.I.S."}
                    </strong>
                    <span>
                      {voice.recording
                        ? "RELEASE TO TRANSCRIBE · MAX 60 SECONDS"
                        : "HOLD THE MIC OR SPACE · RELEASE TO TRANSCRIBE"}
                    </span>
                  </div>
                  {voice.recording ? (
                    <button
                      className="icon-button"
                      aria-label="Cancel recording"
                      onClick={voice.cancelRecording}
                    >
                      ×
                    </button>
                  ) : (
                    <button
                      className="icon-button"
                      aria-label="Stop speaking"
                      title="Stop speaking"
                      onClick={() => { if (shortcuts.isBusy()) void shortcuts.stop(); else void voice.stopSpeaking(); }}
                    >
                      <Icon name="stop" size={16} />
                    </button>
                  )}
                </div>
                <div className="core-footer">
                  {preferences.wakeWord ? (
                    <span role="status">
                      HEY JARVIS / JARVIS{" "}
                      <b>
                        {wake.listening
                          ? "LISTENING"
                          : wake.processing
                            ? "TRANSCRIBING"
                            : "PAUSED"}
                      </b>
                    </span>
                  ) : null}
                  <span>
                    VOICE <b>{preferences.voice ? "ENABLED" : "OFF"}</b>
                  </span>
                  <span>
                    AUDIO <b>CPU</b>
                  </span>
                  <span>
                    MEMORY <b>HERMES</b>
                  </span>
                </div>
              </section>
              <div id="conversation-drawer" className="conversation-drawer" hidden={immersive && !chatExpanded}>
              <ChatPanel
                timezone={status?.online?.timezone??'Asia/Manila'}
                messages={messages}
                input={input}
                setInput={setInput}
                send={(s) => void send(s)}
                cancel={cancel}
                busy={busy}
                announcementBlocked={shortcutActive || desktopPlaying}
                activity={activity}
                replay={(s) => {
                  if (shortcuts.isBusy()) return;
                  wake.stop();
                  void voice.speak(s);
                }}
                newSession={newSession}
              />
              </div>
            </div>
            {actions.some((a) => a.status === "pending") ? (
              <section className="panel command-approvals">
                <div className="panel-title">
                  <h2>Your approval is required</h2>
                </div>
                <ApprovalPanel
                  actions={actions.filter((a) => a.status === "pending")}
                  refresh={() => void refresh()}
                  fail={fail}
                />
              </section>
            ) : null}
            <footer className="bottom-bar">
              <span>
                <i className="status-dot" />
                {data
                  ? `TELEMETRY SAMPLED ${new Date(data.sampled_at * 1000).toLocaleTimeString([],{timeZone:status?.online?.timezone??'Asia/Manila'})}`
                  : "AWAITING TELEMETRY"}
              </span>
              <span>
                {data?.unavailable.length
                  ? `${data.unavailable.join(" / ")} UNAVAILABLE`
                  : "PRIVATE COMPUTE · LOOPBACK INTERFACE"}
              </span>
            </footer>
        </div>
        {tab === "system" ? (
          <>
          <SystemPanel
            data={data}
            status={status}
            actions={actions}
            monitor={monitor}
            refresh={() => {void refresh();void refreshStatus();}}
            fail={fail}
          />
          <div className="detail-page"><HomeAccessPanel changed={()=>{void refresh();void refreshReviews().catch(()=>{});}} fail={fail}/></div>
          </>
        ) : null}
        {tab === "memory" ? (
          <MemoryPanel
            revision={memoryRevision}
            changed={() => {
              memoryChanged();
              void refreshReviews().catch(() => {});
            }}
            fail={fail}
          />
        ) : null}
        {tab === "shortcuts" ? <ShortcutsPanel events={shortcuts.events} refreshEvents={shortcuts.refresh} stopEvent={shortcuts.stop}/> : null}
        {tab === "settings" ? (
          <SettingsPanel
            preferences={preferences}
            change={(p) => {
              if (p.immersiveMicMode != null) { wake.stop(); voice.cancelRecording(); setAwaitingWakeCommand(false); setWakeCycle(value => value + 1); }
              if (p.microphoneMuted != null) applyAudioCommand(p.microphoneMuted ? "microphone_mute" : "microphone_unmute");
              if (p.startupSound === false && voice.startupActive) void voice.stopSpeaking();
              if (p.voice === false) {
                void voice.stopSpeaking();
              }
              setPreferences((current) => ({ ...current, ...p }));
            }}
            status={status}
            monitor={monitor}
            refresh={() => {void refresh();void refreshStatus();}}
            fail={fail}
            modelBusy={
              busy ||
              resolving ||
              voice.recording ||
              voice.acquiring ||
              voice.synthesizing
              || shortcutActive || desktopPlaying
            }
            modelChanged={() => {
              wake.stop();
              void voice.stopAll();
              newSession();
              void refreshStatus();
            }}
            speechBusy={busy || resolving || shortcutActive || desktopPlaying || voice.recording || voice.acquiring || phase === "transcribing"}
            stopSpeech={async () => {
              wake.stop();
              await voice.stopAll();
            }}
            testSpeech={() => {
              wake.stop();
              void voice.speak("At your service, sir. Your selected speech device is ready. I will keep replies brief and clearly spoken. You can change the voice processing device here, adjust the playback volume, or stop me whenever you wish. I await your next instruction.");
            }}
          />
        ) : null}
      </main>
      {informationOpen ? <Suspense fallback={<div className="startup-prompt">Loading information view…</div>}>
        <InformationPanel receipt={informationReceipt} changed={setInformationReceipt} close={() => setInformationOpen(false)} />
      </Suspense> : null}
      {mapOpen ? <Suspense fallback={<div className="startup-prompt">Loading map…</div>}>
        <MapPanel failure={error} locating={mapLocating} receipt={mapReceipt} changed={setMapReceipt} reduced={preferences.reducedMotion} close={() => setMapOpen(false)} />
      </Suspense> : null}
      {immersive ? <>
        <div className="immersive-caption" aria-live="polite">
          <span>JARVIS</span>
          <small>{immersiveCaption}</small>
        </div>
        <nav className="immersive-controls" aria-label="Immersive controls">
          <button className="immersive-mode-toggle" role="switch" aria-label="Wake phrase only in immersive mode"
            aria-checked={preferences.immersiveMicMode === 'wake'}
            title="Switch between always listening and wake phrase mode"
            onClick={() => {
              wake.stop(); voice.cancelRecording(); setAwaitingWakeCommand(false);
              setWakeCycle(value => value + 1);
              setPreferences(current => ({ ...current, immersiveMicMode: current.immersiveMicMode === 'wake' ? 'always' : 'wake' }));
            }}><span>{preferences.immersiveMicMode === 'wake' ? 'Wake phrase' : 'Always listening'}</span></button>
          <button aria-label={handsFree && !preferences.microphoneMuted ? "Mute immersive microphone" : "Enable immersive microphone"}
            aria-pressed={handsFree && !preferences.microphoneMuted} title={handsFree && !preferences.microphoneMuted ? "Mute microphone" : "Enable microphone"}
            onClick={() => { applyAudioCommand(handsFree && !preferences.microphoneMuted ? "microphone_mute" : "microphone_unmute"); setHandsFree(true); }}>
            <Icon name="mic" size={18}/><span>{handsFree && !preferences.microphoneMuted ? "Mic on" : "Muted"}</span>
          </button>
          <button aria-label="Stop Jarvis" title="Stop Jarvis" onClick={() => {
            wake.stop(); if (shortcuts.isBusy()) void shortcuts.stop(); else void voice.stopSpeaking(); if (busyRef.current) cancel();
            setWakeCycle(value => value + 1);
          }}><Icon name="stop" size={17}/><span>Stop</span></button>
          <button aria-expanded={chatExpanded} aria-controls="conversation-drawer"
            onClick={() => setChatExpanded(value => !value)} title="Toggle conversation">
            <Icon name="chat" size={18}/><span>{chatExpanded ? "Hide chat" : "Chat"}</span>
          </button>
          <button title="Open map" onClick={() => {setMapOpen(value => !value);setInformationOpen(false);}}>Map</button>
          <button title="Open news and markets" onClick={() => {setInformationOpen(value => !value);setMapOpen(false);}}>News</button>
          {reviews.length ? <button onClick={() => setReviewId(reviews[0].id)}>Permissions ({reviews.length})</button> : null}
          <button aria-label="Exit immersive mode" title="Return to dashboard" onClick={leaveImmersive}>
            <span>Exit ↗</span>
          </button>
        </nav>
      </> : null}
      {review ? (
        <PermissionDialog
          key={review.id}
          ticket={review}
          count={reviews.length}
          busy={
            busy ||
            resolving ||
            voice.acquiring ||
            voice.synthesizing ||
            shortcutActive || desktopPlaying ||
            phase === "transcribing"
          }
          close={() => {
            void voice.stopAll();
            setReviewId(null);
          }}
          resolve={(approve) => void resolveReview(approve)}
          command={(text) => void send(text)}
          speak={readPermission}
          startRecording={startRecording}
          stopRecording={voice.stopRecording}
          cancelRecording={voice.cancelRecording}
          microphoneDisabled={preferences.microphoneMuted || busy || resolving || shortcutActive || desktopPlaying || phase === "transcribing"}
          recording={voice.recording}
          error={error}
          transcript={confirmationTranscript}
          stopVoice={() => {
            void voice.stopSpeaking();
          }}
        />
      ) : null}
    </div>
  );
}
