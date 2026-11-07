import type { Telemetry } from "../services/types";
export const gib = (n: number) => `${(n / 1073741824).toFixed(1)} GiB`;
export const pct = (n: number | null | undefined) =>
  n == null ? "Unavailable" : `${Math.round(n)}%`;
function Meter({
  label,
  value,
  detail,
}: {
  label: string;
  value: number | null | undefined;
  detail?: string;
}) {
  return (
    <div className="meter">
      <div>
        <span>{label}</span>
        <strong>{pct(value)}</strong>
      </div>
      <div className="meter-track">
        <i style={{ width: `${value ?? 0}%` }} />
      </div>
      {detail ? <small>{detail}</small> : null}
    </div>
  );
}
export function TelemetryRail({
  data,
  history,
}: {
  data: Telemetry | null;
  history: number[];
}) {
  return (
    <aside className="telemetry-rail">
      <section className="panel telemetry-panel">
        <div className="panel-title">
          <h2>System overview</h2>
          <span className="panel-index">01</span>
        </div>
        <div className="host-label">
          <i className={data ? "status-dot" : "status-dot warn"} />
          ARCH LINUX<span>HYPRLAND</span>
        </div>
        <Meter label="CPU LOAD" value={data?.cpu_percent} />
        <Meter
          label="MEMORY"
          value={data?.ram.percent}
          detail={
            data ? `${gib(data.ram.used)} / ${gib(data.ram.total)}` : undefined
          }
        />
        <Meter
          label="GPU UTILIZATION"
          value={data?.gpu?.utilization}
          detail={data?.gpu?.name}
        />
        <Meter
          label="STORAGE"
          value={data?.disk.percent}
          detail={
            data
              ? `${gib(data.disk.total - data.disk.used)} available`
              : undefined
          }
        />
        <div className="telemetry-pair">
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
        </div>
        <div className="telemetry-pair">
          <div>
            <small>VRAM</small>
            <strong>
              {data?.gpu?.vram_used_mb == null
                ? "—"
                : `${(data.gpu.vram_used_mb / 1024).toFixed(1)}`}
              <em>
                {data?.gpu?.vram_used_mb == null ? "UNAVAILABLE" : "GiB USED"}
              </em>
            </strong>
          </div>
        </div>
      </section>
      <section className="panel signal-panel">
        <div className="panel-title">
          <h2>Resource signal</h2>
          <span className="panel-index">02</span>
        </div>
        <div className="signal-chart">
          {history.length > 1 ? (
            <svg
              viewBox="0 0 200 70"
              preserveAspectRatio="none"
              aria-label="Recent measured CPU usage"
            >
              <path
                d={`M ${history.map((v, i) => `${(i / (history.length - 1)) * 200},${68 - v * 0.6}`).join(" L ")}`}
                fill="none"
                stroke="currentColor"
                strokeWidth="1.4"
              />
            </svg>
          ) : (
            <span>Collecting live samples</span>
          )}
        </div>
        <div className="tiny-row">
          <span>CPU / RECENT SAMPLES</span>
          <span>{history.length}</span>
        </div>
      </section>
      <section className="power-panel">
        <div>
          <span className="small-label">POWER RESERVE</span>
          <strong>
            {data?.battery ? `${Math.round(data.battery.percent)}%` : "—"}
          </strong>
        </div>
        <span>
          {data?.battery
            ? data.battery.charging == null
              ? "POWER STATE UNAVAILABLE"
              : data.battery.charging
                ? "AC CONNECTED"
                : "ON BATTERY"
            : "BATTERY UNAVAILABLE"}
        </span>
      </section>
    </aside>
  );
}
