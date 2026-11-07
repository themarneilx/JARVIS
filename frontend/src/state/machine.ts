export type Phase =
  | "idle"
  | "listening"
  | "transcribing"
  | "thinking"
  | "executing_tool"
  | "speaking"
  | "error";
export type PhaseEvent =
  | "RECORD"
  | "TRANSCRIBE"
  | "SEND"
  | "TOOL"
  | "TOKEN"
  | "SPEAK"
  | "DONE"
  | "CANCEL"
  | "FAIL";
const transitions: Record<Phase, Partial<Record<PhaseEvent, Phase>>> = {
  idle: {
    RECORD: "listening",
    SEND: "thinking",
    SPEAK: "speaking",
    FAIL: "error",
  },
  listening: { TRANSCRIBE: "transcribing", CANCEL: "idle", FAIL: "error" },
  transcribing: {
    DONE: "idle",
    SEND: "thinking",
    CANCEL: "idle",
    FAIL: "error",
  },
  thinking: {
    TOOL: "executing_tool",
    TOKEN: "thinking",
    SPEAK: "speaking",
    DONE: "idle",
    CANCEL: "idle",
    FAIL: "error",
  },
  executing_tool: {
    TOKEN: "thinking",
    TOOL: "executing_tool",
    DONE: "idle",
    SPEAK: "speaking",
    CANCEL: "idle",
    FAIL: "error",
  },
  speaking: {
    DONE: "idle",
    CANCEL: "idle",
    RECORD: "listening",
    SEND: "thinking",
    FAIL: "error",
  },
  error: {
    DONE: "idle",
    RECORD: "listening",
    SEND: "thinking",
    SPEAK: "speaking",
    CANCEL: "idle",
  },
};
export function transition(state: Phase, event: PhaseEvent): Phase {
  return transitions[state][event] ?? state;
}
export const phaseLabels: Record<Phase, string> = {
  idle: "Awaiting your instruction",
  listening: "Listening to your microphone",
  transcribing: "Transcribing locally",
  thinking: "Reasoning through Hermes",
  executing_tool: "Executing a reviewed tool",
  speaking: "Audio playback",
  error: "Attention required",
};
export type Quality = "low" | "balanced" | "performance";
export const presets: Record<
  Quality,
  { dpr: number; particles: number; fps: number; bloom: boolean; poll: number }
> = {
  low: { dpr: 1, particles: 180, fps: 20, bloom: false, poll: 15000 },
  balanced: { dpr: 1.25, particles: 450, fps: 30, bloom: true, poll: 7000 },
  performance: { dpr: 1.5, particles: 800, fps: 45, bloom: true, poll: 5000 },
};
