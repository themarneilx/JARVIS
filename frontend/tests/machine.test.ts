import { expect, test } from "vitest";
import { transition, presets, type Phase } from "../src/state/machine";
test("complete voice/tool cycle follows actual events", () => {
  let state: Phase = "idle";
  for (const event of [
    "RECORD",
    "TRANSCRIBE",
    "SEND",
    "TOOL",
    "TOKEN",
    "SPEAK",
    "DONE",
  ] as const)
    state = transition(state, event);
  expect(state).toBe("idle");
});
test("invalid events do not pretend a tool is running", () =>
  expect(transition("idle", "TOOL")).toBe("idle"));
test("errors and interruption recover", () => {
  expect(transition("listening", "FAIL")).toBe("error");
  expect(transition("error", "SEND")).toBe("thinking");
  expect(transition("speaking", "CANCEL")).toBe("idle");
});
test("all graphics presets cap resolution", () =>
  Object.values(presets).forEach((p) =>
    expect(p.dpr).toBeLessThanOrEqual(1.5),
  ));
