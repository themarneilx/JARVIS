import { useState } from "react";
import type { Action, Telemetry, Status, MonitorView } from "../services/types";
import { post, api } from "../services/api";
import { gib } from "../components/TelemetryRail";
export function ApprovalPanel({
  actions,
  refresh,
  fail,
}: {
  actions: Action[];
  refresh: () => void;
  fail: (s: string) => void;
}) {
  const [pending, setPending] = useState("");
  async function resolve(id: string, approve: boolean) {
    setPending(id);
    try {
      await post(`/actions/${id}/resolve`, { approve });
      refresh();
    } catch (e) {
      fail(String(e));
    } finally {
      setPending("");
    }
  }
  if (!actions.length)
    return (
      <p className="muted">
        No action proposals. Desktop changes require a separate approval here.
      </p>
    );
  return (
    <div className="approval-list">
      {actions.map((a) => (
        <div className="action-row" key={a.id}>
          <div>
            <strong>{a.kind.replaceAll("_", " ")}</strong>
            <code>{a.target}</code>
            <p>{a.effect}</p>
            <small>
              {a.status.toUpperCase()}
              {a.status === "pending"
                ? ` · expires ${new Date(a.expires * 1000).toLocaleTimeString()}`
                : ""}
            </small>
          </div>
          {a.status === "pending" ? (
            <div className="button-row">
              <button
                disabled={pending === a.id}
                onClick={() => void resolve(a.id, false)}
              >
                Reject
              </button>
              <button
                className="primary"
                disabled={pending === a.id}
                onClick={() => void resolve(a.id, true)}
              >
                Approve once
              </button>
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}
export function SystemPanel({
  data,
  status,
  actions,
  monitor,
  refresh,
  fail,
}: {
  data: Telemetry | null;
  status: Status | null;
  actions: Action[];
  monitor: MonitorView | null;
  refresh: () => void;
  fail: (s: string) => void;
}) {
  const [filter, setFilter] = useState(""),
    [workspace, setWorkspace] = useState("2"),
    [volume, setVolume] = useState("50");
  async function propose(kind: string, target: string, effect: string) {
    try {
      await post("/actions", { kind, target, effect });
      refresh();
    } catch (e) {
      fail(String(e));
    }
  }
  return (
    <div className="detail-page">
      <div className="page-heading">
        <div className="small-label">DESKTOP INSTRUMENTATION</div>
        <h1>System & operations</h1>
        <p>
          Live readings from this machine. Every desktop change is reviewed
          before execution.
        </p>
      </div>
      <div className="system-summary">
        <div
          title={
            data?.cpu_temperature_source ||
            "No CPU temperature sensor available"
          }
        >
          <small>CPU TEMP</small>
          <strong>
            {data?.cpu_temperature == null
              ? "Unavailable"
              : `${data.cpu_temperature.toFixed(0)}°C`}
          </strong>
        </div>
        <div>
          <small>GPU TEMP</small>
          <strong>
            {data?.gpu?.temperature == null
              ? "Unavailable"
              : `${data.gpu.temperature}°C`}
          </strong>
        </div>
        <div>
          <small>UPTIME</small>
          <strong>
            {data
              ? `${Math.floor(data.uptime_seconds / 3600)}h ${Math.floor(data.uptime_seconds / 60) % 60}m`
              : "Unavailable"}
          </strong>
        </div>
        <div>
          <small>BACKEND MEMORY</small>
          <strong>
            {data
              ? `${(data.backend_rss / 1048576).toFixed(0)} MB`
              : "Unavailable"}
          </strong>
        </div>
        <div>
          <small>RAM AVAILABLE</small>
          <strong>
            {data ? gib(data.ram.total - data.ram.used) : "Unavailable"}
          </strong>
        </div>
        <div>
          <small>NETWORK</small>
          <strong>
            {data?.network
              ?.filter((n) => n.up)
              .map((n) => n.name)
              .join(", ") || "Unavailable"}
          </strong>
        </div>
      </div>
      <section className="panel">
        <div className="panel-title">
          <h2>Approval queue</h2>
          <span>SCOPED · ONE USE · 120 SECONDS</span>
        </div>
        <ApprovalPanel actions={actions} refresh={refresh} fail={fail} />
      </section>
      <div className="detail-grid">
        <section className="panel">
          <div className="panel-title">
            <h2>Services</h2>
            <span>{data?.services?.length ?? "—"} DISCOVERED</span>
          </div>
          <input
            aria-label="Filter services"
            placeholder="Filter services…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <div className="service-list">
            {data?.services ? (
              data.services
                .filter((s) =>
                  s.unit?.toLowerCase().includes(filter.toLowerCase()),
                )
                .map((s) => (
                  <div className="service-row" key={s.scope + s.unit}>
                    <div>
                      <strong>{s.unit}</strong>
                      <small>
                        {s.scope} · {s.sub}
                      </small>
                    </div>
                    <span
                      className={s.active === "failed" ? "warning" : "muted"}
                    >
                      {s.active}
                    </span>
                    {s.scope === "user" &&
                    status?.approved_services.includes(s.unit) ? (
                      <button
                        onClick={() =>
                          void propose(
                            "service_restart",
                            s.unit,
                            `Restart user service ${s.unit}; active connections may be interrupted.`,
                          )
                        }
                      >
                        Propose restart
                      </button>
                    ) : null}
                  </div>
                ))
            ) : (
              <p className="muted">
                Systemd is unavailable in this execution environment.
              </p>
            )}
          </div>
        </section>
        <section className="panel">
          <div className="panel-title">
            <h2>Hyprland desktop</h2>
            <span>{data?.desktop.available ? "CONNECTED" : "UNAVAILABLE"}</span>
          </div>
          <p className="small-label">FOCUSED WINDOW</p>
          <p>
            {data?.desktop.focused?.title || "No focus information available"}
          </p>
          <div className="window-list">
            {data?.desktop.clients.map((w, i) => (
              <div key={i}>
                <strong>{w.class}</strong>
                <span>{w.title}</span>
                <small>WORKSPACE {w.workspace}</small>
              </div>
            ))}
          </div>
          <form
            className="inline-form"
            onSubmit={(e) => {
              e.preventDefault();
              void propose(
                "workspace",
                workspace,
                `Switch the desktop to workspace ${workspace}.`,
              );
            }}
          >
            <label>
              Workspace
              <input
                type="number"
                min="1"
                max="99"
                value={workspace}
                onChange={(e) => setWorkspace(e.target.value)}
              />
            </label>
            <button>Propose switch</button>
          </form>
          <form
            className="inline-form"
            onSubmit={(e) => {
              e.preventDefault();
              void propose(
                "volume",
                volume,
                `Set the default PipeWire output volume to ${volume}%.`,
              );
            }}
          >
            <label>
              Volume %
              <input
                type="number"
                min="0"
                max="100"
                value={volume}
                onChange={(e) => setVolume(e.target.value)}
              />
            </label>
            <button>Propose volume</button>
          </form>
        </section>
      </div>
      <section className="panel">
        <div className="panel-title">
          <h2>Health events & routines</h2>
          <span>NO BACKGROUND MODEL INFERENCE</span>
        </div>
        {monitor?.alerts.length ? (
          monitor.alerts.map((a) => (
            <p className="warning" key={a.id}>
              {new Date(a.at * 1000).toLocaleTimeString()} · {a.message}
            </p>
          ))
        ) : (
          <p className="muted">
            No health alerts recorded. Monitoring is{" "}
            {monitor?.settings.enabled ? "enabled" : "disabled"}.
          </p>
        )}
        {monitor?.routines.map((r) => (
          <div className="service-row" key={r.id}>
            <div>
              <strong>{r.name}</strong>
              <small>
                Telemetry report every {r.interval / 60} min ·{" "}
                {r.enabled ? "enabled" : "disabled"}
              </small>
            </div>
            <button
              onClick={() =>
                void post(`/routines/${r.id}`, { enabled: !r.enabled })
                  .then(refresh)
                  .catch((e) => fail(String(e)))
              }
            >
              {r.enabled ? "Disable" : "Enable"}
            </button>
            <button
              onClick={() =>
                void api(`/routines/${r.id}`, { method: "DELETE" })
                  .then(refresh)
                  .catch((e) => fail(String(e)))
              }
            >
              Delete
            </button>
          </div>
        ))}
        {monitor?.reports.map((r) => (
          <details key={r.id}>
            <summary>
              Saved telemetry report · {new Date(r.at * 1000).toLocaleString()}
            </summary>
            <pre>{JSON.stringify(r.payload, null, 2)}</pre>
          </details>
        ))}
      </section>
    </div>
  );
}
