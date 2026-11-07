import { useEffect, useRef, useState } from "react";
import type { ReviewTicket } from "../services/confirmation";
import { PushToTalkButton } from "./PushToTalkButton";

export function PermissionDialog({
  ticket,
  count,
  busy,
  close,
  resolve,
  command,
  speak,
  startRecording,
  stopRecording,
  cancelRecording,
  microphoneDisabled,
  recording,
  error,
  stopVoice,
  transcript,
}: {
  ticket: ReviewTicket;
  count: number;
  busy: boolean;
  close: () => void;
  resolve: (approve: boolean) => void;
  command: (text: string) => void;
  speak: () => void;
  startRecording: () => void;
  stopRecording: () => void;
  cancelRecording: () => void;
  microphoneDisabled: boolean;
  recording: boolean;
  error?: string;
  stopVoice: () => void;
  transcript: string;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [text, setText] = useState("");
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const element = dialog.current;
    element?.showModal();
    return () => {
      element?.close();
      previous?.focus();
    };
  }, []);
  useEffect(() => setText(""), [ticket.id]);
  useEffect(() => {
    if (transcript) setText(transcript);
  }, [transcript]);
  return (
    <dialog
      ref={dialog}
      className="permission-dialog"
      aria-labelledby="permission-title"
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      <div className="panel-title">
        <span>YOUR PERMISSION · {count} PENDING</span>
        <button aria-label="Review later" onClick={close}>
          ×
        </button>
      </div>
      <h2 id="permission-title">{ticket.title}</h2>
      <dl>
        <dt>Exact target</dt>
        <dd>
          <code>{ticket.target}</code>
        </dd>
      </dl>
      {ticket.effect ? <p>{ticket.effect}</p> : null}
      {ticket.old_text ? (
        <div className="review-content">
          <small>{ticket.source === "shortcut" ? "PREVIOUS SHORTCUT" : "PREVIOUS MEMORY"}</small>
          <p>{ticket.old_text}</p>
        </div>
      ) : null}
      {ticket.content ? (
        <div className="review-content">
          <small>{ticket.source === "shortcut" ? "PROPOSED SHORTCUT" : "PROPOSED MEMORY"}</small>
          <p>{ticket.content}</p>
        </div>
      ) : null}
      {ticket.reason ? <p>Reason: {ticket.reason}</p> : null}
      <p className="confirmation-code">
        Type or say <strong>approve {ticket.code}</strong> or{" "}
        <strong>reject {ticket.code}</strong>.
      </p>
      {error ? (
        <p className="warning" role="status">
          {error}
        </p>
      ) : null}
      {transcript ? (
        <p role="status">
          Heard: {transcript}. Correct the command below if necessary.
        </p>
      ) : null}
      <p className="muted">
        This confirmation expires at{" "}
        {new Date(ticket.expires * 1000).toLocaleTimeString()}. It applies only
        to this proposal. Voice recognizes words, not the speaker.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          command(text);
          setText("");
        }}
      >
        <label htmlFor="confirmation-command">Confirmation command</label>
        <input
          id="confirmation-command"
          value={text}
          onChange={(e) => setText(e.target.value)}
          autoComplete="off"
          placeholder={`approve ${ticket.code}`}
          maxLength={100}
        />
        <div className="button-row">
          <button disabled={busy || !text.trim()}>Send confirmation</button>
          <PushToTalkButton label="Hold microphone for confirmation" disabled={microphoneDisabled} recording={recording} start={startRecording} finish={stopRecording} cancel={cancelRecording}>
            {recording ? "Release to transcribe" : "Hold to speak confirmation"}
          </PushToTalkButton>
          <button type="button" disabled={busy || recording} onClick={speak}>
            Read request aloud
          </button>
          <button type="button" onClick={stopVoice}>
            Stop voice
          </button>
        </div>
      </form>
      <div className="button-row permission-decisions">
        <button disabled={busy} autoFocus onClick={() => resolve(false)}>
          Reject
        </button>
        <button
          className="primary"
          disabled={busy}
          onClick={() => resolve(true)}
        >
          Approve once
        </button>
        <button disabled={busy} onClick={close}>
          Review later
        </button>
      </div>
      {busy ? (
        <p role="status">Waiting for the active request to finish…</p>
      ) : null}
    </dialog>
  );
}
