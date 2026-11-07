export type DesktopOutcome = { status: string; authorization?: string; result?: { message?: string } };

export function desktopOutcome(result: DesktopOutcome, terminal = false): string {
  if (result.status === "pending") return "Waiting for your approval in the review popup.";
  if (result.status === "executed") return terminal
    ? "Kitty accepted the launch. Check the terminal for command output and completion."
    : "The desktop launcher accepted the request.";
  if (result.status === "failed") return result.result?.message || "The launch failed. Check your desktop session and installed program.";
  return "The request did not execute. Check the System activity list.";
}
