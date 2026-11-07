import { useEffect, useState } from "react";
import { api, post } from "../services/api";
import type { MemoryEntry, MemoryView } from "../services/types";
export function MemoryPanel({
  changed,
  fail,
  revision=0,
}: {
  changed: () => void;
  fail: (s: string) => void;
  revision?: number;
}) {
  const [view, setView] = useState<MemoryView | null>(null),
    [error, setError] = useState(""),
    [text, setText] = useState(""),
    [reason, setReason] = useState(""),
    [target, setTarget] = useState("user"),
    [editing, setEditing] = useState<MemoryEntry | null>(null),
    [busy, setBusy] = useState(false);
  async function load() {
    try {
      setView(await api<MemoryView>("/memory"));
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }
  useEffect(() => {
    void load();
  }, [revision]);
  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    try {
      await action();
      await load();
    } catch (e) {
      fail(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function propose(action: string, entry?: MemoryEntry) {
    await post("/memory/proposals", {
      action,
      target: entry?.target || target,
      content: action === "remove" ? "" : text,
      old_text: entry?.text || editing?.text || "",
      reason:
        action === "remove"
          ? "User requested removal of this saved entry"
          : reason,
    });
    setText("");
    setReason("");
    setEditing(null);
  }
  return (
    <div className="detail-page memory-page">
      <div className="page-heading">
        <div className="small-label">CURATED LONG-TERM KNOWLEDGE</div>
        <h1>Memory</h1>
        <p>
          Preferences and useful facts in Hermes’ native memory. Identity is
          maintained separately in SOUL.md.
        </p>
      </div>
      {error ? (
        <div className="notice warning">
          {error}
          <button onClick={() => void load()}>Reconnect</button>
        </div>
      ) : null}
      <section className="panel">
        <div className="panel-title">
          <h2>Propose a memory</h2>
          <span>REVIEW REQUIRED</span>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run(() => propose(editing ? "patch" : "add"));
          }}
        >
          <div className="form-grid">
            <label>
              Store
              <select
                value={target}
                disabled={!!editing}
                onChange={(e) => setTarget(e.target.value)}
              >
                <option value="user">User preferences</option>
                <option value="memory">System & project knowledge</option>
              </select>
            </label>
            <label>
              Why keep this?
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                required
                maxLength={300}
                placeholder="How it will help in future sessions"
              />
            </label>
          </div>
          <label>
            {editing ? "Edited memory" : "Memory content"}
            <textarea
              required
              rows={3}
              value={text}
              maxLength={target === "user" ? 1375 : 2200}
              onChange={(e) => setText(e.target.value)}
              placeholder="One concise, durable preference or verified fact"
            />
          </label>
          <div className="button-row">
            <button className="primary" disabled={busy || !view}>
              {editing ? "Review edit" : "Propose memory"}
            </button>
            {editing ? (
              <button
                type="button"
                onClick={() => {
                  setEditing(null);
                  setText("");
                  setReason("");
                }}
              >
                Cancel edit
              </button>
            ) : null}
          </div>
        </form>
        <p className="muted">
          Passwords and access tokens are refused. Deleted entries are not
          recreated from old suggestions. Pinning prevents automatic changes; it
          does not expand Hermes’ memory budget.
        </p>
      </section>
      <div className="toggle-row">
        <label>
          <input
            type="checkbox"
            checked={view?.suggestions ?? false}
            disabled={!view || busy}
            onChange={(e) =>
              void run(() =>
                post("/memory/suggestions", { enabled: e.target.checked }),
              )
            }
          />
          Allow automatic memory suggestions
        </label>
        <span>Suggestions always wait for review</span>
      </div>
      {view?.pending.length ? (
        <section className="panel">
          <div className="panel-title">
            <h2>Awaiting your review</h2>
          </div>
          {view.pending.map((p) => (
            <div className="memory-entry" key={p.id}>
              <small>
                {p.action.toUpperCase()} · {p.target.toUpperCase()}
              </small>
              {p.old_text ? <p className="old-text">{p.old_text}</p> : null}
              {p.content ? <p>{p.content}</p> : null}
              <div className="muted">Reason: {p.reason}</div>
              <div className="button-row">
                <button
                  disabled={busy}
                  onClick={() =>
                    void run(() =>
                      post(`/memory/proposals/${p.id}/resolve`, {
                        approve: false,
                      }),
                    )
                  }
                >
                  Reject
                </button>
                <button
                  className="primary"
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      await post(`/memory/proposals/${p.id}/resolve`, {
                        approve: true,
                      });
                      changed();
                    })
                  }
                >
                  Approve memory change
                </button>
              </div>
            </div>
          ))}
        </section>
      ) : null}
      <section className="panel">
        <div className="panel-title">
          <h2>Saved knowledge</h2>
          <span>{view?.entries.length ?? "—"} ENTRIES</span>
        </div>
        {view?.entries.length ? (
          view.entries
            .sort((a, b) => Number(b.pinned) - Number(a.pinned))
            .map((entry) => (
              <div key={entry.id} className="memory-entry">
                <small>
                  {entry.target === "user"
                    ? "USER PREFERENCE"
                    : "SYSTEM / PROJECT KNOWLEDGE"}
                  {entry.pinned ? " · PINNED" : ""}
                </small>
                <p>{entry.text}</p>
                <div className="muted">{entry.reason}</div>
                <div className="button-row">
                  <button
                    disabled={busy}
                    onClick={() =>
                      void run(() =>
                        post(`/memory/${entry.id}/pin`, {
                          pinned: !entry.pinned,
                        }),
                      )
                    }
                  >
                    {entry.pinned ? "Unpin" : "Pin"}
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => {
                      setEditing(entry);
                      setTarget(entry.target);
                      setText(entry.text);
                      setReason("User edited an existing memory");
                      window.scrollTo({ top: 0, behavior: "instant" });
                    }}
                  >
                    Edit
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => void run(() => propose("remove", entry))}
                  >
                    Review deletion
                  </button>
                </div>
              </div>
            ))
        ) : (
          <p className="muted">
            {view
              ? "No saved entries. J.A.R.V.I.S. retains its identity through SOUL.md."
              : "Connect native Hermes memory to view saved entries."}
          </p>
        )}
      </section>
      {view?.history.length ? (
        <details>
          <summary>Memory change history (fingerprints only)</summary>
          {view.history.map((h, i) => (
            <p key={i}>
              {new Date(h.at * 1000).toLocaleString()} · {h.action} ·{" "}
              {h.fingerprint.slice(0, 12)}
            </p>
          ))}
        </details>
      ) : null}
    </div>
  );
}
