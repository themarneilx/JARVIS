export function parseConfirmation(
  text: string,
): { approve: boolean; code: string } | null {
  const command = text
    .normalize("NFKC")
    .toLowerCase()
    .trim()
    .replace(/^jarvis[,\s]+/, "")
    .replace(/[.!?]+$/, "");
  const match = command.match(/^(approve|reject)(?:\s+code)?\s+(.+)$/);
  if (!match) return null;
  const digits: Record<string, string> = {
    zero: "0",
    one: "1",
    two: "2",
    three: "3",
    four: "4",
    five: "5",
    six: "6",
    seven: "7",
    eight: "8",
    nine: "9",
  };
  const code = match[2]
    .split(/[\s,-]+/)
    .map((word) => digits[word] ?? word)
    .join("");
  return /^\d{4}$/.test(code)
    ? { approve: match[1] === "approve", code }
    : null;
}

export interface ReviewTicket {
  id: string;
  proposal_id: string;
  source: "action" | "memory" | "shortcut";
  title: string;
  target: string;
  effect?: string;
  content?: string;
  old_text?: string;
  reason?: string;
  code: string;
  expires: number;
}
