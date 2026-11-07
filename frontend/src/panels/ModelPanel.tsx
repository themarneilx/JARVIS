import { useEffect, useState } from "react";
import { api, post } from "../services/api";

interface Model {
  name: string;
  size_bytes: number;
  parameter_size: string;
  quantization: string;
  context_default: number;
  context_limit: number;
  ready: boolean;
  can_prepare: boolean;
  reason: string | null;
}
interface Catalog {
  selected_model: string | null;
  models: Model[];
}

export function ModelPanel({
  changed,
  fail,
  busy,
}: {
  changed: () => void;
  fail: (text: string) => void;
  busy: boolean;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null),
    [chosen, setChosen] = useState(""),
    [working, setWorking] = useState(false),
    [error, setError] = useState("");
  async function load() {
    try {
      const result = await api<Catalog>("/models");
      setCatalog(result);
      setChosen(
        (current) =>
          current || result.selected_model || result.models[0]?.name || "",
      );
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }
  useEffect(() => {
    void load();
  }, []);
  const model = catalog?.models.find((item) => item.name === chosen);
  async function apply() {
    if (!model) return;
    setWorking(true);
    try {
      let name = model.name;
      if (!model.ready) {
        const prepared = await post<Model>("/models/prepare", { model: name });
        name = prepared.name;
      }
      await post("/models/select", { model: name });
      setChosen(name);
      changed();
      await load();
    } catch (e) {
      fail(String(e));
    } finally {
      setWorking(false);
    }
  }
  return (
    <section className="panel model-panel">
      <div className="panel-title">
        <h2>Brain · local model</h2>
        <span>HERMES / OLLAMA</span>
      </div>
      <p className="muted">
        Active:{" "}
        <code>{catalog?.selected_model || "Loading local inventory…"}</code>
      </p>
      {error ? (
        <p role="alert" className="warning">
          {error}
        </p>
      ) : null}
      <label>
        Installed model
        <select
          aria-label="AI brain model"
          value={chosen}
          disabled={working || busy || !catalog}
          onChange={(e) => setChosen(e.target.value)}
        >
          {catalog?.models.map((item) => (
            <option key={item.name} value={item.name}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      {model ? (
        <>
          <p>
            {(model.size_bytes / 1e9).toFixed(1)} GB on disk ·{" "}
            {model.parameter_size} · {model.quantization}
          </p>
          <p>
            Context default: {model.context_default.toLocaleString()} ·
            advertised limit: {model.context_limit.toLocaleString()}
          </p>
          {model.reason ? <p className="warning">{model.reason}</p> : null}
        </>
      ) : null}
      <p className="muted">
        A model switch starts a fresh conversation. Preparing a model creates a
        separate local 64K tag using existing weights. This can increase RAM and
        VRAM usage. Metadata checks do not prove runtime performance.
      </p>
      <div className="button-row">
        <button
          className="primary"
          onClick={() => void apply()}
          disabled={
            working ||
            busy ||
            !model ||
            (!model.ready && !model.can_prepare) ||
            catalog?.selected_model === chosen
          }
        >
          {working
            ? "Applying model…"
            : model?.ready
              ? "Use this model"
              : "Prepare 64K tag and use model"}
        </button>
        <button disabled={working} onClick={() => void load()}>
          Refresh models
        </button>
      </div>
    </section>
  );
}
