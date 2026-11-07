import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import { Icon } from "../components/Icon";
import type { Message } from "../services/types";
export function ChatPanel({
  messages,
  input,
  setInput,
  send,
  cancel,
  busy,
  announcementBlocked = false,
  activity,
  replay,
  newSession,
  timezone='Asia/Manila',
}: {
  messages: Message[];
  input: string;
  setInput: (v: string) => void;
  send: (text?: string) => void;
  cancel: () => void;
  busy: boolean;
  announcementBlocked?: boolean;
  activity: string;
  replay: (text: string) => void;
  newSession: () => void;
  timezone?: string;
}) {
  const log = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  const previousLast = useRef('');
  const [copied, setCopied] = useState("");
  useEffect(() => {
    const last = messages.at(-1);
    if (last && last.id !== previousLast.current && (last.role === 'user' || !last.text)) followLatest.current = true;
    previousLast.current = last?.id ?? '';
    if (followLatest.current && log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [messages, activity]);
  useEffect(() => {
    if (!log.current) return;
    const resize = new ResizeObserver(() => {
      if (followLatest.current && log.current) log.current.scrollTop = log.current.scrollHeight;
    });
    resize.observe(log.current);
    return () => resize.disconnect();
  }, []);
  return (
    <section className="panel chat-panel">
      <div className="panel-title">
        <h2>Communication</h2>
        <button
          className="icon-button"
          title="New conversation"
          aria-label="New conversation"
          onClick={newSession}
          disabled={busy || announcementBlocked}
        >
          <Icon name="plus" size={17} />
        </button>
      </div>
      <div className="chat-channel">
        <span className="status-dot" />
        PRIVATE LOCAL CHANNEL<span>HERMES</span>
      </div>
      <div ref={log} className="messages" role="log" aria-label="Conversation" tabIndex={0}
        onScroll={e => { const node = e.currentTarget; followLatest.current = node.scrollHeight - node.clientHeight - node.scrollTop < 64; }}>
        {!messages.length ? (
          <div className="chat-empty">
            <div className="empty-glyph">
              <Icon name="core" size={36} />
            </div>
            <h3>At your service.</h3>
            <p>Give an instruction by text, or activate the microphone.</p>
            <div className="suggestions">
              <button
                disabled={announcementBlocked}
                onClick={() =>
                  send("Jarvis, give me a live system status report.")
                }
              >
                Give me a status report <span>↗</span>
              </button>
              <button
                disabled={announcementBlocked}
                onClick={() => send("Check my GPU using live telemetry.")}
              >
                Inspect the graphics processor <span>↗</span>
              </button>
            </div>
          </div>
        ) : null}
        {messages.map((m) => (
          <article
            key={m.id}
            className={`message ${m.role} ${m.failed ? "failed" : ""}`}
          >
            <div className="message-meta">
              <span>{m.role === "assistant" ? "J.A.R.V.I.S." : "YOU"}</span>
              <time>
                {new Date(m.at).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                  timeZone: timezone,
                })}
              </time>
            </div>
            <Markdown
              skipHtml
              components={{
                img: () => null,
                a: ({ children,href }) => href?.startsWith('https://')
                  ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
                  : <span>{children}</span>,
              }}
            >
              {m.text}
            </Markdown>
            {m.role === "assistant" && m.text ? (
              <div className="message-actions">
                <button
                  aria-label="Copy message"
                  onClick={() =>
                    void navigator.clipboard
                      .writeText(m.text)
                      .then(() => setCopied(m.id))
                  }
                >
                  <Icon name="copy" size={13} />
                  {copied === m.id ? "Copied" : "Copy"}
                </button>
                <button
                  aria-label="Speak message"
                  onClick={() => replay(m.text)}
                  disabled={busy || announcementBlocked}
                >
                  <Icon name="sound" size={13} />
                  Replay
                </button>
              </div>
            ) : null}
          </article>
        ))}
        {activity ? (
          <div className="activity" role="status">
            <i />
            {activity}
          </div>
        ) : null}
      </div>
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <label className="sr-only" htmlFor="instruction">
          Your instruction
        </label>
        <textarea
          id="instruction"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Your instruction, sir…"
          rows={3}
          maxLength={16000}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              !e.shiftKey &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              send();
            }
          }}
        />
        <div className="composer-foot">
          <span>{announcementBlocked ? "SHORTCUT ANNOUNCEMENT IN PROGRESS" : "ENTER TO SEND · SHIFT + ENTER FOR NEW LINE"}</span>
          {busy ? (
            <button
              type="button"
              className="send-button"
              onClick={cancel}
              aria-label="Cancel generation"
            >
              <Icon name="stop" size={16} />
            </button>
          ) : (
            <button
              className="send-button"
              type="submit"
              disabled={!input.trim() || announcementBlocked}
              aria-label="Send instruction"
            >
              <Icon name="send" size={18} />
            </button>
          )}
        </div>
      </form>
    </section>
  );
}
