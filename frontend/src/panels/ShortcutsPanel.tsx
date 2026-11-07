import { useEffect, useRef, useState } from "react";
import { api, post } from "../services/api";
import { newShortcut, shortcutEventTime, shortcutReview, shortcutTemplate, shortcutWeekdays } from "../services/shortcuts";
import type { ShortcutEvent, ShortcutSpec, ShortcutView, ShortcutsView } from "../services/types";

export function ShortcutsPanel({ events, refreshEvents, stopEvent }: {
  events: ShortcutEvent[];
  refreshEvents: () => Promise<void>;
  stopEvent: (id: string) => Promise<void>;
}) {
  const [view, setView] = useState<ShortcutsView | null>(null);
  const [spec, setSpec] = useState(() => newShortcut(""));
  const [editing, setEditing] = useState<ShortcutView | null>(null);
  const [authorized, setAuthorized] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);
  const form = useRef<HTMLFormElement>(null);
  const initialized = useRef(false);

  async function load() {
    const next = await api<ShortcutsView>("/shortcuts");
    setView(next);
    if (!initialized.current) {
      initialized.current = true;
      setSpec(newShortcut(next.capabilities.timezone));
    }
  }
  useEffect(() => {
    let disposed = false;
    void load().catch(cause => { if (!disposed) setError(String(cause).replace(/^Error: /, "")); });
    const timer = setInterval(() => { if (!document.hidden) void load().catch(() => {}); }, 10000);
    return () => { disposed = true; clearInterval(timer); };
  }, []);

  async function mutate(action: () => Promise<unknown>, message: string) {
    setBusy(true); setError(""); setNotice("");
    try {
      await action();
      await Promise.all([load(), refreshEvents()]);
      setNotice(message);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "The shortcut could not be updated."); }
    finally { setBusy(false); }
  }
  function change(patch: Partial<ShortcutSpec>) {
    setSpec(current => ({ ...current, ...patch }));
    setAuthorized(false);
  }
  function template(kind: "alarm" | "battery" | "briefing") {
    setEditing(null); setAuthorized(false); setError(""); setNotice("");
    setSpec(shortcutTemplate(kind, view?.capabilities.timezone || ""));
    form.current?.scrollIntoView({ behavior: "instant", block: "start" });
    form.current?.querySelector<HTMLInputElement>("input")?.focus({ preventScroll: true });
  }
  function edit(shortcut: ShortcutView) {
    setEditing(shortcut); setSpec({ ...shortcut.spec, weekdays: [...shortcut.spec.weekdays] });
    setAuthorized(false); setError(""); setNotice("");
    form.current?.scrollIntoView({ behavior: "instant", block: "start" });
    form.current?.querySelector<HTMLInputElement>("input")?.focus({ preventScroll: true });
  }
  const timezone = view?.capabilities.timezone;
  const weatherUnavailable = spec.weather && !view?.capabilities.weather_available;
  const scheduleIncomplete = (spec.trigger === "daily" && !spec.weekdays.length) || ((spec.trigger === "daily" || spec.trigger === "once") && !spec.time);

  return <div className="detail-page shortcuts-page">
    <div className="page-heading">
      <div className="small-label">LOCAL TIMING & ANNOUNCEMENTS</div>
      <h1>Shortcuts</h1>
      <p>Set an alarm, a battery warning or a daily briefing. Your backend and laptop must be awake. Desktop delivery can play with the browser closed.</p>
    </div>
    {!view && !error ? <p role="status">Loading local shortcuts…</p> : null}
    {error ? <div className="notice warning" role="alert"><span>{error}</span><button onClick={() => void mutate(load, "Shortcuts refreshed.")}>Refresh shortcuts</button></div> : null}
    {view?.capabilities.scheduler_error ? <p className="warning" role="alert">{view.capabilities.scheduler_error}</p> : null}
    {notice ? <p className="notice" role="status">{notice}</p> : null}
    <section className="shortcut-templates" aria-labelledby="shortcut-templates-title">
      <div><h2 id="shortcut-templates-title">Start from a template</h2><p className="muted">Fills the builder. Nothing runs until you authorize it.</p></div>
      <div className="shortcut-template-buttons">
        <button disabled={!view || busy} onClick={() => template("alarm")}><strong>Alarm</strong><span>One time · chime + voice</span></button>
        <button disabled={!view || busy} onClick={() => template("battery")}><strong>Low battery</strong><span>At 20% · spoken reminder</span></button>
        <button disabled={!view || busy} onClick={() => template("briefing")}><strong>Morning briefing</strong><span>Daily 07:00 · saved-city weather</span></button>
      </div>
    </section>
    <div className="shortcuts-workspace">
      <section className="panel shortcut-builder">
        <div className="panel-title"><h2>{editing ? "Edit shortcut" : "Build a shortcut"}</h2><span>{editing ? "REVIEW CHANGES" : "EXPLICIT AUTHORIZATION"}</span></div>
        <form ref={form} onSubmit={event => {
          event.preventDefault();
          if (!authorized || !view || busy || scheduleIncomplete || weatherUnavailable) return;
          void mutate(async () => {
            if (editing) await api(`/shortcuts/${editing.id}`, { method: "PUT", body: JSON.stringify({ spec, authorized: true, revision: editing.revision }) });
            else await post("/shortcuts", { spec, authorized: true });
            setEditing(null); setAuthorized(false); setSpec(newShortcut(view.capabilities.timezone));
          }, editing ? "Shortcut changes authorized and saved." : "Shortcut authorized and created.");
        }}>
          <fieldset className="shortcut-fields" disabled={busy || !view}>
          <label>Shortcut name<input required maxLength={80} value={spec.name} disabled={busy} onChange={event => change({ name: event.target.value })}/></label>
          <label>When<select aria-label="When" value={spec.trigger} disabled={busy} onChange={event => {
            const trigger = event.target.value as ShortcutSpec["trigger"];
            change({ trigger, time: trigger === "daily" || trigger === "once" ? spec.time || "07:00" : "", date: trigger === "once" ? spec.date : "" });
          }}><option value="once">At a time, once</option><option value="daily">Daily on selected weekdays</option><option value="battery">Battery is low</option><option value="manual">Only when I run it</option></select></label>
          {spec.trigger === "once" || spec.trigger === "daily" ? <>
            <div className="form-grid">
              <label>Time<input type="time" required value={spec.time} disabled={busy} onChange={event => change({ time: event.target.value })}/></label>
              {spec.trigger === "once" ? <label>Date (optional)<input type="date" value={spec.date} disabled={busy} onChange={event => change({ date: event.target.value })}/></label> : null}
            </div>
            <label>Timezone<input required value={spec.timezone} maxLength={80} disabled={busy} placeholder={timezone || "IANA timezone, e.g. Asia/Manila"} onChange={event => change({ timezone: event.target.value })}/></label>
            {spec.trigger === "once" && !spec.date ? <p className="muted">No date means the next occurrence of this time in the selected timezone.</p> : null}
          </> : null}
          {spec.trigger === "daily" ? <fieldset className="shortcut-weekdays"><legend>Weekdays</legend>{shortcutWeekdays.map((day, index) => <label key={day}><input type="checkbox" checked={spec.weekdays.includes(index)} disabled={busy} onChange={event => change({ weekdays: event.target.checked ? [...spec.weekdays, index].sort((a, b) => a - b) : spec.weekdays.filter(value => value !== index) })}/>{day}</label>)}</fieldset> : null}
          {spec.trigger === "battery" ? <label>Battery threshold (%)<input type="number" required min={1} max={50} value={spec.threshold} disabled={busy} onChange={event => change({ threshold: Number(event.target.value) })}/><span className="muted"> Uses measured battery data while discharging. Charging and unknown readings do not trigger it.</span></label> : null}
          <fieldset className="shortcut-actions"><legend>Then, in this order</legend>
            <label className="check-label"><input type="checkbox" checked={spec.chime} disabled={busy} onChange={event => change({ chime: event.target.checked })}/>Play a short chime</label>
            <label>Say this<textarea rows={3} maxLength={500} value={spec.message} disabled={busy} onChange={event => change({ message: event.target.value })} placeholder="Your short announcement"/></label>
            <p className="muted">Optional placeholders: <code>{"{time}"}</code>, <code>{"{date}"}</code>, <code>{"{location}"}</code>, <code>{"{battery_percent}"}</code>. Voice uses your selected JarvisLuxTTS voice.</p>
            <label className="check-label"><input type="checkbox" checked={spec.weather} disabled={busy} onChange={event => change({ weather: event.target.checked })}/>Add current weather for the saved city</label>
            <p className={weatherUnavailable ? "warning" : "muted"}>{view?.capabilities.location_label ? `Saved city: ${view.capabilities.location_label}. ` : "No saved city. "}{weatherUnavailable ? "Set a city and enable internet information in Settings before saving this weather shortcut." : "Weather is fetched when the shortcut runs."}</p>
          </fieldset>
          <label>Deliver through<select aria-label="Deliver through" value={spec.delivery} disabled={busy} onChange={event => change({ delivery: event.target.value as ShortcutSpec["delivery"] })}><option value="auto">Auto: browser, otherwise desktop (recommended)</option><option value="browser">Paired browser only</option><option value="desktop">Desktop speakers</option></select></label>
          <p className="muted">{view?.capabilities.desktop_audio_available ? "Desktop audio is available. " : "Desktop audio is unavailable. "}Browser playback requires an open, available paired tab. Jarvis voice mute leaves requested chimes enabled. System volume is unchanged.</p>
          <div className="shortcut-review" aria-label="Shortcut review"><strong>{spec.name || "Untitled shortcut"}</strong><p>{shortcutReview(spec)}</p><p>{spec.chime ? "Chime. " : ""}{spec.message || "No spoken message."}{spec.weather ? " Then current saved-city weather." : ""}</p></div>
          <label className="check-label shortcut-authorization"><input type="checkbox" checked={authorized} disabled={busy || !view} onChange={event => setAuthorized(event.target.checked)}/>{editing ? "I authorize these changes to this shortcut." : "I authorize this shortcut and its scheduled announcements."}</label>
          <div className="button-row"><button className="primary" disabled={busy || !view || !authorized || scheduleIncomplete || weatherUnavailable}>{busy ? "Saving…" : editing ? "Authorize & save changes" : "Authorize & create shortcut"}</button>{editing ? <button type="button" disabled={busy} onClick={() => { setEditing(null); setAuthorized(false); setSpec(newShortcut(timezone || "")); }}>Cancel edit</button> : null}</div>
          </fieldset>
        </form>
      </section>
      <section className="panel shortcut-list">
        <div className="panel-title"><h2>Your shortcuts</h2><span>{view ? `${view.shortcuts.length} SAVED` : "LOADING"}</span></div>
        {view?.shortcuts.length ? view.shortcuts.map(shortcut => <article className="shortcut-entry" key={shortcut.id}>
          <div className="shortcut-entry-heading"><h3>{shortcut.spec.name}</h3><span className={shortcut.enabled ? "shortcut-enabled" : "muted"}>{shortcut.enabled ? "Enabled" : "Disabled"}</span></div>
          <p>{shortcut.summary}</p>
          <dl className="shortcut-run-times"><div><dt>Next run</dt><dd>{shortcut.enabled && shortcut.next_run ? shortcutEventTime(shortcut.next_run, shortcut.spec.timezone) : shortcut.spec.trigger === "battery" && shortcut.enabled ? "At battery threshold" : shortcut.spec.trigger === "manual" ? "Run manually" : "Not scheduled"}</dd></div><div><dt>Last run</dt><dd>{shortcutEventTime(shortcut.last_run, shortcut.spec.timezone)}</dd></div></dl>
          {shortcut.last_error ? <p className="warning">{shortcut.last_error}</p> : null}
          <div className="button-row"><button disabled={busy} onClick={() => void mutate(() => post(`/shortcuts/${shortcut.id}/enabled`, { enabled: !shortcut.enabled, revision: shortcut.revision }), shortcut.enabled ? "Shortcut disabled. Queued runs cancelled." : "Shortcut enabled.")}>{shortcut.enabled ? "Disable" : "Enable"}</button><button disabled={busy} onClick={() => void mutate(() => post(`/shortcuts/${shortcut.id}/run`, {}), "Shortcut queued for delivery.")}>Run now</button><button disabled={busy} onClick={() => edit(shortcut)}>Edit</button><button disabled={busy} onClick={() => setDeleting(shortcut.id)}>Delete</button></div>
          {deleting === shortcut.id ? <div className="shortcut-delete-review"><p>Delete “{shortcut.spec.name}” and cancel its queued runs?</p><div className="button-row"><button disabled={busy} onClick={() => void mutate(async () => { await api(`/shortcuts/${shortcut.id}?revision=${shortcut.revision}`, { method: "DELETE" }); setDeleting(null); if (editing?.id === shortcut.id) { setEditing(null); setAuthorized(false); setSpec(newShortcut(timezone || "")); } }, "Shortcut deleted. Queued runs cancelled.")}>Delete shortcut</button><button disabled={busy} onClick={() => setDeleting(null)}>Keep shortcut</button></div></div> : null}
        </article>) : <p className="muted">{view ? "No shortcuts yet. Choose a template or build your own." : "Loading saved shortcuts…"}</p>}
      </section>
    </div>
    <section className="panel shortcut-history"><div className="panel-title"><h2>Run history</h2><span>{events.length} EVENTS</span></div>
      {events.length ? events.map(item => <article className="shortcut-history-entry" key={item.id}><div><strong>{item.name}</strong><span className={item.status === "failed" || item.status === "missed" ? "warning" : "muted"}>{item.status} · {shortcutEventTime(item.due, timezone)} · {item.delivery}</span></div>{item.text ? <p>{item.text}</p> : null}{item.error ? <p className="warning">{item.error}</p> : null}{item.sources?.length ? <div className="shortcut-sources">{item.sources.filter(source => /^https:\/\//i.test(source.url)).map((source, index) => <a key={index} href={source.url} target="_blank" rel="noopener noreferrer">{source.title || source.name || "Weather source"}</a>)}</div> : null}{["pending", "preparing", "playing"].includes(item.status) ? <button disabled={busy} onClick={() => void stopEvent(item.id)}>Stop this run</button> : null}</article>) : <p className="muted">No runs yet. Scheduled and manual outcomes appear here, including delivery failures.</p>}
    </section>
  </div>;
}
