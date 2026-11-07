import { expect, test } from "vitest";
import { desktopOutcome } from "../src/services/desktop";

test("pending launches never claim execution", () => {
  expect(desktopOutcome({ status: "pending" })).toContain("approval");
});
test("terminal launch is distinct from command completion", () => {
  expect(desktopOutcome({ status: "executed" }, true)).toContain("Check the terminal");
  expect(desktopOutcome({ status: "executed" }, true)).not.toContain("command completed");
});
test("failed or unknown outcomes cannot become success", () => {
  expect(desktopOutcome({ status: "failed", result: { message: "Unavailable" } })).toBe("Unavailable");
  expect(desktopOutcome({ status: "unknown" })).toContain("did not execute");
});
