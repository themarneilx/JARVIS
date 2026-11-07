import { useCallback, useEffect, useRef, useState } from "react";
import { canListenForWake, WakeWordListener } from "../services/wakeWord";
import type { WakeWordState } from "../services/wakeWord";

interface WakeWordOptions {
  enabled: boolean;
  conversation?: boolean;
  background?: boolean;
  suspended: boolean;
  mic: string;
  onWake: (command: string) => void;
  onAttention?: () => void;
  onSpeechStart?: () => void;
  onEmptyPhrase?: () => void;
  fail: (message: string) => void;
  restartKey?: number;
}

export function useWakeWord({
  enabled,
  conversation = false,
  background = false,
  suspended,
  mic,
  onWake,
  onAttention,
  onSpeechStart,
  onEmptyPhrase,
  fail,
  restartKey = 0,
}: WakeWordOptions) {
  const callbacks = useRef({ onWake, fail, onAttention, onSpeechStart, onEmptyPhrase });
  callbacks.current = { onWake, fail, onAttention, onSpeechStart, onEmptyPhrase };
  const [state, setState] = useState<WakeWordState>({
    listening: false,
    processing: false,
  });
  const listener = useRef<WakeWordListener | null>(null);

  useEffect(() => {
    const capture = new WakeWordListener({
      onWake: (command) => callbacks.current.onWake(command),
      fail: (message) => callbacks.current.fail(message),
      onState: setState,
      conversation,
      onAttention: () => callbacks.current.onAttention?.(),
      onSpeechStart: () => callbacks.current.onSpeechStart?.(),
      onEmptyPhrase: () => callbacks.current.onEmptyPhrase?.(),
    });
    listener.current = capture;
    const update = () => {
      if (
        canListenForWake({
          enabled,
          suspended,
          hidden: document.hidden,
          background,
        })
      )
        capture.start(mic, background);
      else capture.stop();
    };
    document.addEventListener("visibilitychange", update);
    update();
    return () => {
      document.removeEventListener("visibilitychange", update);
      capture.stop();
      if (listener.current === capture) listener.current = null;
    };
  }, [enabled, background, suspended, mic, restartKey, conversation]);

  const stop = useCallback(() => listener.current?.stop(), []);
  return { ...state, stop };
}
