import { useEffect, useState } from "react";
import { api, post } from "../services/api";
import { desktopOutcome, type DesktopOutcome } from "../services/desktop";

type Recipe = { id: string; name: string; command: string; cwd: string; available: boolean; error?: string };
type Catalog = { commands: Recipe[]; ask_before_launch: boolean };

export function DesktopSettings({ changed }: { changed: () => void }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [name, setName] = useState(""), [command, setCommand] = useState(""), [cwd, setCwd] = useState("");
  useEffect(() => {
    let disposed = false;
    void api<Catalog>("/terminal/commands").then(value => { if (!disposed) setCatalog(value); })
      .catch(e => { if (!disposed) setError(String(e)); });
    return () => { disposed = true; };
  }, []);
  async function run(work: () => Promise<string>) {
    setBusy(true); setError(""); setNotice("");
    try { setNotice(await work()); setCatalog(await api<Catalog>("/terminal/commands")); changed(); }
    catch (e) { setError(e instanceof Error ? e.message : "Desktop settings could not be updated."); }
    finally { setBusy(false); }
  }
  return <section className="panel" style={{ minWidth: 0 }} aria-labelledby="desktop-permissions-title">
    <div className="panel-title"><h2 id="desktop-permissions-title">Desktop & terminal permissions</h2></div>
    <p className="muted">These permissions are saved on this computer and enforced by the backend.</p>
    {catalog ? <>
      <label className="check-label"><input type="checkbox" checked={catalog.ask_before_launch} disabled={busy}
        onChange={e => { const ask = e.target.checked, previous = catalog; setCatalog({ ...catalog, ask_before_launch: ask }); void run(async () => {
          try { await post("/desktop/settings", { ask_before_launch: ask }); }
          catch (e) { setCatalog(previous); throw e; }
          return ask ? "Desktop launch approval is required again." : "Installed apps and exact saved commands can now launch without repeated approval.";
        }); }} />Ask before opening apps or running saved terminal commands</label>
      <p className={catalog.ask_before_launch ? "muted" : "warning"}>
        {catalog.ask_before_launch ? "Each new launch waits for the review popup or its spoken approval code."
          : "Preauthorized launches are enabled. Jarvis can open installed apps and run any exact command listed here when a tool requests it. Existing pending requests still need approval."}
        {" "}Memory edits, services and other desktop operations still require approval.
      </p>
      <h3>Saved commands · Kitty</h3>
      <p className="muted">Say “Open Kitty and run fastfetch.” Add other commands below, then ask Jarvis to run their saved name. The terminal stays open after the command exits.</p>
      <div className="service-list" role="region" aria-label="Saved terminal commands" tabIndex={0}>
        {catalog.commands.length ? catalog.commands.map(recipe => <div className="service-row" style={{ flexWrap: "wrap" }} key={recipe.id}>
          <div style={{ minWidth: 0 }}><strong>{recipe.name}</strong><small style={{ overflowWrap: "anywhere", whiteSpace: "pre-wrap" }}>{recipe.command}</small>
            <small style={{ overflowWrap: "anywhere" }}>Home{recipe.cwd ? ` / ${recipe.cwd}` : ""}</small>
            {!recipe.available ? <small className="warning">{recipe.error}</small> : null}</div>
          <div className="button-row">
            <button style={{ minHeight: 44 }} type="button" disabled={busy || !recipe.available} aria-label={`Run ${recipe.name} in Kitty`}
              onClick={() => void run(async () => {
                const result = await post<DesktopOutcome>("/terminal/propose", { command_id: recipe.id });
                if (result.status === 'failed') throw new Error(desktopOutcome(result, true));
                return desktopOutcome(result, true);
              })}>Run in Kitty</button>
            <button style={{ minHeight: 44 }} type="button" disabled={busy} aria-label={`Remove saved command ${recipe.name}`}
              onClick={() => void run(async () => { await api(`/terminal/commands/${recipe.id}`, { method: "DELETE" }); return "Saved command removed. Older proposals for it cannot execute."; })}>Remove</button>
          </div>
        </div>) : <p className="muted">No saved commands. Add one below.</p>}
      </div>
      <form onSubmit={e => { e.preventDefault(); void run(async () => {
        await post("/terminal/commands", { name, command, cwd }); setName(""); setCommand(""); setCwd("");
        return "Exact terminal command saved. Jarvis can now request it by name.";
      }); }}>
        <label>Saved command name<input value={name} maxLength={60} required disabled={busy} onChange={e => setName(e.target.value)} placeholder="Project status" /></label>
        <label>Exact command<input value={command} maxLength={512} required disabled={busy} onChange={e => setCommand(e.target.value)} placeholder="git status --short" autoCapitalize="off" spellCheck={false} /></label>
        <label>Working folder relative to home<input value={cwd} maxLength={512} disabled={busy} onChange={e => setCwd(e.target.value)} placeholder="Leave empty for Home" autoCapitalize="off" spellCheck={false} /></label>
        <button style={{ minHeight: 44 }} disabled={busy || !name.trim() || !command.trim()}>Save terminal command</button>
      </form>
      <p className="muted">One installed command with quoted arguments; no shell operators, variables, root commands or shell wrappers. Jarvis cannot create or alter these commands. Save only commands you trust: they run as your account and may read or change files. The home folder limits the starting directory, not the program’s OS permissions. Keep passwords and tokens out of commands.</p>
    </> : <p role="status">Loading desktop permissions…</p>}
    {notice ? <p role="status">{notice}</p> : null}
    {error ? <p role="alert" className="warning">{error}</p> : null}
  </section>;
}
