import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../services/api";
import { desktopOutcome, type DesktopOutcome } from "../services/desktop";

type Application = {
  id: string;
  name: string;
  desktop_id: string;
  effect: string;
};

type ApplicationCatalog = {
  available: boolean;
  applications: Application[];
  truncated: boolean;
  message?: string;
};

type HomeEntry = {
  name: string;
  path: string;
  kind: "file" | "directory";
  size: number | null;
};

type HomeListing = {
  path: string;
  entries: HomeEntry[];
  truncated: boolean;
  query?: string;
};

type FilePreview = {
  path: string;
  text: string;
  size: number;
  truncated: boolean;
};

const touchTarget = { minHeight: 44 };
const wrappingRow = { flexWrap: "wrap" as const };

export function HomeAccessPanel({
  changed,
  fail,
}: {
  changed: () => void;
  fail: (message: string) => void;
}) {
  const [catalog, setCatalog] = useState<ApplicationCatalog | null>(null);
  const [appQuery, setAppQuery] = useState("");
  const [appsLoading, setAppsLoading] = useState(false);
  const [appsError, setAppsError] = useState("");
  const [launchPending, setLaunchPending] = useState("");
  const [launchNotice, setLaunchNotice] = useState("");
  const [listing, setListing] = useState<HomeListing | null>(null);
  const [pathInput, setPathInput] = useState("");
  const [fileQuery, setFileQuery] = useState("");
  const [homeLoading, setHomeLoading] = useState(false);
  const [homeError, setHomeError] = useState("");
  const [preview, setPreview] = useState<FilePreview | null>(null);
  const appRequest = useRef<AbortController | null>(null);
  const homeRequest = useRef<AbortController | null>(null);
  const launchRequest = useRef<AbortController | null>(null);
  const callbacks = useRef({ changed, fail });

  useEffect(() => {
    callbacks.current = { changed, fail };
  }, [changed, fail]);

  const loadApplications = useCallback(async (query: string) => {
    appRequest.current?.abort();
    const controller = new AbortController();
    appRequest.current = controller;
    setAppsLoading(true);
    setAppsError("");
    try {
      const result = await api<ApplicationCatalog>(
        `/applications?query=${encodeURIComponent(query)}`,
        { signal: controller.signal },
      );
      if (!controller.signal.aborted) setCatalog(result);
    } catch (error) {
      if (!controller.signal.aborted) {
        const message = error instanceof Error ? error.message : "Application catalog unavailable";
        setAppsError(message);
        callbacks.current.fail(message);
      }
    } finally {
      if (!controller.signal.aborted) setAppsLoading(false);
    }
  }, []);

  const lookup = useCallback(async (
    kind: "list" | "search" | "read",
    path: string,
    query = "",
  ) => {
    homeRequest.current?.abort();
    const controller = new AbortController();
    homeRequest.current = controller;
    setHomeLoading(true);
    setHomeError("");
    setPreview(null);
    try {
      const result = await api<HomeListing | FilePreview>("/home/lookup", {
        method: "POST",
        body: JSON.stringify({ kind, path, query }),
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (kind === "read") {
        setPreview(result as FilePreview);
      } else {
        const next = result as HomeListing;
        setListing(next);
        setPathInput(next.path);
        if (kind === "list") setFileQuery("");
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        const message = error instanceof Error ? error.message : "Home path unavailable";
        setHomeError(message);
        callbacks.current.fail(message);
      }
    } finally {
      if (!controller.signal.aborted) setHomeLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadApplications("");
    void lookup("list", "");
    return () => {
      appRequest.current?.abort();
      homeRequest.current?.abort();
      launchRequest.current?.abort();
    };
  }, [loadApplications, lookup]);

  async function requestLaunch(application: Application) {
    if (launchRequest.current) return;
    const controller = new AbortController();
    launchRequest.current = controller;
    setLaunchPending(application.id);
    setLaunchNotice("");
    setAppsError("");
    try {
      const result = await api<DesktopOutcome>("/applications/propose", {
        method: "POST",
        body: JSON.stringify({ application_id: application.id }),
        signal: controller.signal,
      });
      if (!controller.signal.aborted) {
        if (result.status === 'failed') setAppsError(`${application.name}: ${desktopOutcome(result)}`);
        else setLaunchNotice(`${application.name}: ${desktopOutcome(result)}`);
        callbacks.current.changed();
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        const message = error instanceof Error ? error.message : "Launch request failed";
        setAppsError(message);
        callbacks.current.fail(message);
      }
    } finally {
      if (!controller.signal.aborted) setLaunchPending("");
      if (launchRequest.current === controller) launchRequest.current = null;
    }
  }

  const folder = listing?.path ?? "";
  const parentFolder = folder.split("/").slice(0, -1).join("/");

  return (
    <div className="detail-grid" style={{ marginBlock: 24 }}>
      <section className="panel" style={{ minWidth: 0 }} aria-labelledby="installed-apps-title">
        <div className="panel-title">
          <h2 id="installed-apps-title">Installed applications</h2>
          <span>DESKTOP POLICY</span>
        </div>
        <p className="muted">Request a launch from the installed catalog. Approval follows your Desktop & terminal permissions in Settings. Commands inside Kitty use the saved terminal commands there.</p>
        <form onSubmit={(event) => {
          event.preventDefault();
          void loadApplications(appQuery);
        }}>
          <label>
            Find an application
            <input value={appQuery} maxLength={120} onChange={(event) => setAppQuery(event.target.value)} placeholder="Application name" />
          </label>
          <button style={touchTarget} disabled={appsLoading}>Search applications</button>
        </form>
        {appsLoading ? <p role="status" className="muted">Reading installed applications…</p> : null}
        {appsError ? <p role="alert" className="warning">{appsError}</p> : null}
        {launchNotice ? <p role="status">{launchNotice}</p> : null}
        {catalog?.available === false ? <p className="warning">{catalog.message || "Desktop launcher unavailable"}</p> : null}
        {catalog?.available ? (
          <>
            <div className="service-list" role="region" aria-label="Installed application catalog" tabIndex={0} aria-busy={appsLoading}>
              {catalog.applications.length ? catalog.applications.map((application) => (
                <div className="service-row" style={wrappingRow} key={application.id}>
                  <div>
                    <strong>{application.name}</strong>
                    <small style={{ overflowWrap: "anywhere" }}>{application.desktop_id}</small>
                  </div>
                  <button
                    style={touchTarget}
                    type="button"
                    disabled={appsLoading || !!launchPending}
                    aria-label={`Request launch of ${application.name}`}
                    onClick={() => void requestLaunch(application)}
                  >
                    {launchPending === application.id ? "Requesting…" : "Request launch"}
                  </button>
                </div>
              )) : <p className="muted">No matching launchable applications. Try a different name or refresh the catalog.</p>}
            </div>
            {catalog.truncated ? <p className="muted">The catalog is bounded. Search by name to narrow the visible results; some deeper entries may be unavailable.</p> : null}
          </>
        ) : null}
      </section>

      <section className="panel" style={{ minWidth: 0 }} aria-labelledby="home-files-title">
        <div className="panel-title">
          <h2 id="home-files-title">Home files</h2>
          <span>READ ONLY</span>
        </div>
        <p className="muted">Browse folders, find filenames, and preview text within your home. Hidden files, credentials, private runtime data, links, and paths outside home are unavailable. The server validates every path.</p>
        <form onSubmit={(event) => {
          event.preventDefault();
          void lookup("list", pathInput);
        }}>
          <label>
            Folder relative to home
            <input value={pathInput} maxLength={1024} onChange={(event) => setPathInput(event.target.value)} placeholder="Documents or leave empty for Home" disabled={homeLoading} autoCapitalize="off" spellCheck={false} />
          </label>
          <div className="button-row">
            <button style={touchTarget} disabled={homeLoading}>Browse folder</button>
            <button type="button" style={touchTarget} disabled={homeLoading || !folder} onClick={() => void lookup("list", parentFolder)}>Up one folder</button>
            <button type="button" style={touchTarget} disabled={homeLoading} onClick={() => void lookup("list", "")}>Home</button>
          </div>
        </form>
        <form onSubmit={(event) => {
          event.preventDefault();
          void lookup("search", folder, fileQuery);
        }}>
          <label>
            Find names in this folder
            <input value={fileQuery} maxLength={120} onChange={(event) => setFileQuery(event.target.value)} placeholder="Part of a file or folder name" disabled={homeLoading || !listing} />
          </label>
          <button style={touchTarget} disabled={homeLoading || !listing || !fileQuery.trim()}>Search filenames</button>
        </form>
        {homeLoading ? <p role="status" className="muted">Reading home files…</p> : null}
        {homeError ? <p role="alert" className="warning">{homeError}</p> : null}
        {listing ? (
          <>
            <p style={{ marginTop: 20, overflowWrap: "anywhere" }}>
              {listing.query ? <>Matches for <strong>{listing.query}</strong> in </> : null}
              <code>Home{folder ? ` / ${folder}` : ""}</code>
            </p>
            <div className="service-list" role="region" aria-label="Home file results" tabIndex={0} aria-busy={homeLoading}>
              {listing.entries.length ? listing.entries.map((entry) => (
                <div className="service-row" style={wrappingRow} key={entry.path}>
                  <div>
                    <strong>{entry.name}</strong>
                    <small style={{ overflowWrap: "anywhere" }}>
                      {listing.query ? `${entry.path} · ` : ""}
                      {entry.kind === "directory" ? "Folder" : `${(entry.size ?? 0).toLocaleString()} bytes`}
                    </small>
                  </div>
                  <button
                    type="button"
                    style={touchTarget}
                    disabled={homeLoading}
                    aria-label={`${entry.kind === "directory" ? "Browse folder" : "Preview text from"} ${entry.path}`}
                    onClick={() => void lookup(entry.kind === "directory" ? "list" : "read", entry.path)}
                  >
                    {entry.kind === "directory" ? "Browse" : "Preview text"}
                  </button>
                </div>
              )) : <p className="muted">{listing.query ? "No accessible names matched within the search limits." : "No accessible entries in this folder."}</p>}
            </div>
            {listing.truncated ? <p className="warning">Partial results: the entry, depth, or scan limit was reached. Browse a narrower folder to continue.</p> : null}
          </>
        ) : null}
        {preview ? (
          <div style={{ marginTop: 24 }}>
            <div className="button-row" style={{ justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ margin: 0, overflowWrap: "anywhere" }}>Text preview: {preview.path}</h3>
              <button type="button" style={touchTarget} onClick={() => setPreview(null)}>Close preview</button>
            </div>
            <p className={preview.truncated ? "warning" : "muted"} role="status">
              {preview.size.toLocaleString()} bytes total · {preview.truncated ? "Partial preview; limited to 32 KiB." : "UTF-8 text preview, up to 32 KiB."}
            </p>
            <pre tabIndex={0} aria-label={`Plain text preview of ${preview.path}`} style={{ maxHeight: "24rem", overflow: "auto", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{preview.text || "(Empty text file)"}</pre>
          </div>
        ) : null}
      </section>
    </div>
  );
}
