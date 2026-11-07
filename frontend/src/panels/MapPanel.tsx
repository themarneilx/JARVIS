import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import GeographicMap from '../scenes/GeographicMap';
import { api } from '../services/api';

interface Place { label: string; lat: number; lon: number }
export interface MapView {
  receipt: string;
  kind: 'map' | 'directions';
  destinations: Place[];
  origins: Place[];
  selected_destination: number | null;
  selected_origin: number | null;
  route: { coordinates: [number, number][]; distance_m: number; duration_s: number } | null;
}
export default function MapPanel({ receipt, reduced, close, changed, locating = false, failure = "" }: { receipt: string | null; reduced: boolean; close: () => void; changed: (receipt: string) => void; locating?: boolean; failure?: string }) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const initialCenter = useRef<[number, number]>([10.33, 123.94]);
  const layers = useRef<L.LayerGroup | null>(null);
  const [flatMap, setFlatMap] = useState(false);
  const [view, setView] = useState<MapView | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [query, setQuery] = useState('');
  const [origin, setOrigin] = useState('');
  const [directions, setDirections] = useState(false);
  const [destination, setDestination] = useState(0);
  const [start, setStart] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => { if (locating) { generation.current++; controller.current?.abort(); setBusy(false); setView(null); setError(""); } }, [locating]);
  useEffect(() => {
    let alive = true;
    async function permission() {
      try {
        const settings = await api<{ enabled: boolean; location?: { latitude: number; longitude: number } | null }>('/information/settings');
        if (!alive) return;
        if (settings.location) initialCenter.current = [settings.location.latitude, settings.location.longitude];
        setEnabled(settings.enabled);
        if (!settings.enabled) {
          generation.current++; controller.current?.abort(); setView(null); setBusy(false);
          setError('Internet lookups are disabled. Enable them in Settings to use maps.');
        }
      } catch { if (alive) { generation.current++; controller.current?.abort(); setBusy(false); setEnabled(false); setView(null); setError("Cannot verify internet permission. Reopen the map after reconnecting."); } }
    }
    void permission();
    const timer = setInterval(() => void permission(), 4000);
    return () => { alive = false; clearInterval(timer); generation.current++; controller.current?.abort(); };
  }, []);
  async function load(loadView: (signal: AbortSignal) => Promise<MapView>) {
    controller.current?.abort();
    const request = new AbortController(); controller.current = request;
    const id = ++generation.current;
    setBusy(true); setError('');
    try {
      const next = await loadView(request.signal);
      if (generation.current === id && !request.signal.aborted) {
        setView(next); changed(next.receipt); setDestination(next.selected_destination ?? 0); setStart(next.selected_origin ?? 0);
      }
    } catch (e) { if (generation.current === id && !request.signal.aborted) setError(String(e).replace(/^Error: /, '')); }
    finally { if (generation.current === id) setBusy(false); }
  }
  useEffect(() => {
    if (receipt && receipt !== view?.receipt && enabled) void load(signal => api<MapView>(`/maps/${receipt}`, { signal }));
  }, [receipt, enabled]);
  useEffect(() => {
    if (!enabled || !flatMap || !container.current) return;
    const instance = L.map(container.current, { zoomControl: false, zoomAnimation: !reduced, fadeAnimation: !reduced }).setView(initialCenter.current, 11);
    map.current = instance;
    L.control.zoom({ position: 'bottomright' }).addTo(instance);
    const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, minZoom: 2, keepBuffer: 0, updateWhenIdle: true,
      referrerPolicy: 'strict-origin-when-cross-origin',
      attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a>',
    }).addTo(instance);
    tiles.on('tileerror', () => setError('Map tiles are unavailable. Place coordinates and routes remain available; try again later.'));
    layers.current = L.layerGroup().addTo(instance);
    const resize = new ResizeObserver(() => instance.invalidateSize()); resize.observe(container.current);
    return () => { resize.disconnect(); instance.remove(); map.current = null; layers.current = null; };
  }, [enabled, reduced, flatMap]);
  useEffect(() => {
    const instance = map.current, group = layers.current;
    if (!instance || !group || !view) return;
    group.clearLayers();
    const places = view.selected_destination === null ? view.destinations : [view.destinations[view.selected_destination]];
    const bounds: L.LatLngTuple[] = [];
    for (const place of places) {
      const point: L.LatLngTuple = [place.lat, place.lon]; bounds.push(point);
      const label = document.createElement('span'); label.textContent = place.label;
      L.circleMarker(point, { radius: 7, color: '#69fff0', weight: 2, fillOpacity: .5 }).bindTooltip(label).addTo(group);
    }
    if (view.route) {
      const points: L.LatLngTuple[] = view.route.coordinates.map(([lon, lat]) => [lat, lon]);
      L.polyline(points, { color: '#26dfec', weight: 4, opacity: .95 }).addTo(group);
      bounds.push(...points);
      if (view.selected_origin !== null) {
        const origin = view.origins[view.selected_origin];
        L.circleMarker([origin.lat, origin.lon], { radius: 7, color: '#f4bf76' }).addTo(group);
      }
    }
    if (bounds.length > 1) instance.flyToBounds(bounds, { padding: [60, 60], maxZoom: 15, animate: !reduced, duration: 1.6 });
    else if (bounds[0]) instance.flyTo(bounds[0], 14, { animate: !reduced, duration: 1.6 });
  }, [view, enabled, reduced, flatMap]);
  return <section className="map-overlay" aria-label="Location and directions">
    <div ref={container} className="map-canvas" aria-label="Interactive OpenStreetMap" hidden={!flatMap} />
    {!flatMap ? <GeographicMap view={view} enabled={enabled} reduced={reduced} locating={busy || locating}
      center={initialCenter.current} fallback={() => setFlatMap(true)} /> : null}
    <div className="map-tools">
      <div className="map-heading"><h2>Places & directions</h2><button onClick={close}>Back to core</button></div>
      <p>Public map data · driving routes without live traffic · no GPS tracking</p>
      <button onClick={() => setFlatMap(value => !value)}>{flatMap ? "Switch to 3D map" : "Switch to 2D map"}</button>
      <form onSubmit={e => {
        e.preventDefault();
        if (locating) return;
        void load(async signal => {
          const result = await api<{ map_receipt: string }>('/information/lookup', {
            method: 'POST', body: JSON.stringify({ kind: directions ? 'directions' : 'map', query, origin }), signal,
          });
          return api<MapView>(`/maps/${result.map_receipt}`, { signal });
        });
      }}>
        <label>Place or destination<input value={query} maxLength={200} onChange={e => setQuery(e.target.value)} placeholder="e.g. Mactan Cebu International Airport" required /></label>
        <label className="map-route-choice"><input type="checkbox" checked={directions} onChange={e => setDirections(e.target.checked)} />Driving directions</label>
        {directions ? <label>Starting place<input value={origin} maxLength={200} onChange={e => setOrigin(e.target.value)} placeholder="Leave blank to review your saved city" /></label> : null}
        <button disabled={!enabled || busy || locating}>{busy ? 'Looking up…' : 'Find place'}</button>
      </form>
      {view && (!view.route || view.destinations.length > 1) ? <div className="map-selection">
        <label>Destination<select value={destination} onChange={e => setDestination(Number(e.target.value))}>
          {view.destinations.map((p, i) => <option value={i} key={i}>{p.label}</option>)}
        </select></label>
        {view.kind === 'directions' ? <label>Confirm starting point<select value={start} onChange={e => setStart(Number(e.target.value))}>
          {view.origins.map((p, i) => <option value={i} key={i}>{p.label}</option>)}
        </select></label> : null}
        <button disabled={busy || locating || !enabled || (view.kind === 'directions' && !view.origins.length)} onClick={() => void load(signal => api<MapView>('/maps/select', {
          method: 'POST', body: JSON.stringify({ receipt: view.receipt, destination, origin: start }), signal,
        }))}>{view.kind === 'directions' ? 'Confirm places & show route' : 'Zoom to selected place'}</button>
      </div> : null}
      {view?.route ? <p role="status">{(view.route.distance_m / 1000).toFixed(1)} km · about {Math.round(view.route.duration_s / 60)} min by car. OSRM estimate, not live traffic.</p> : null}
      {view?.selected_destination != null ? <p className="map-coordinates">{view.destinations[view.selected_destination].label}<br />{view.destinations[view.selected_destination].lat.toFixed(5)}, {view.destinations[view.selected_destination].lon.toFixed(5)}</p> : null}
      {failure || error ? <p role="alert">{failure || error}</p> : null}
    </div>
  </section>;
}
