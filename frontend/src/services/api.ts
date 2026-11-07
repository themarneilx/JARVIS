let csrf = "";
export function setCsrf(token: string) {
  csrf = token;
}
export async function api<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && typeof options.body === "string")
    headers.set("Content-Type", "application/json");
  if (options.method && options.method !== "GET")
    headers.set("X-CSRF-Token", csrf);
  const response = await fetch(`/api${path}`, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    const body = await response
      .json()
      .catch(() => ({ detail: `Request failed (${response.status})` }));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Invalid request (${response.status})`,
    );
  }
  return response.json();
}
export const post = <T = unknown>(path: string, body: unknown) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
export type StreamEvent = {
  type: string;
  text?: string;
  label?: string;
  message?: string;
  state?: string;
  session_id?: string;
  epoch?: number;
  receipt?: string;
};
export async function chat(
  text: string,
  session: string | null,
  epoch: number,
  signal: AbortSignal,
  onEvent: (event: StreamEvent) => void,
) {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf,
      "X-Memory-Epoch": String(epoch),
    },
    body: JSON.stringify({
      text,
      session_id: session,
      request_id: crypto.randomUUID(),
    }),
    signal,
    credentials: "same-origin",
  });
  if (!response.ok)
    throw new Error((await response.json()).detail || "Agent request failed");
  if (!response.body) throw new Error("Streaming is unavailable");
  const reader = response.body.getReader(),
    decoder = new TextDecoder();
  let buffer = "";
  let terminal = false;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const data = frame
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (data) {
          const event = JSON.parse(data) as StreamEvent;
          if (event.type === "done" || event.type === "error") terminal = true;
          onEvent(event);
        }
      }
    }
    if (!terminal && !signal.aborted)
      throw new Error(
        "The stream ended early. Start a fresh conversation before retrying.",
      );
  } finally {
    reader.releaseLock();
  }
}
