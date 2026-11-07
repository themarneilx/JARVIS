import { useEffect, useRef, useState } from 'react';
import { Map, NavigationControl, LngLatBounds, setWorkerUrl, setWorkerCount, type GeoJSONSource, type StyleSpecification } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { MapView } from '../panels/MapPanel';
setWorkerUrl(workerUrl);
setWorkerCount(2);

const style: StyleSpecification = {
  version: 8,
  glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
  sources: { geography: { type: 'vector', url: 'https://tiles.openfreemap.org/planet' } },
  layers: [
    { id: 'background', type: 'background', paint: { 'background-color': '#030d22' } },
    { id: 'water', type: 'fill', source: 'geography', 'source-layer': 'water', paint: { 'fill-color': '#061e36' } },
    { id: 'waterways', type: 'line', source: 'geography', 'source-layer': 'waterway', paint: { 'line-color': '#14526a', 'line-width': .6 } },
    { id: 'boundaries', type: 'line', source: 'geography', 'source-layer': 'boundary', paint: { 'line-color': '#217cac', 'line-width': .7, 'line-opacity': .7 } },
    { id: 'roads-glow', type: 'line', source: 'geography', 'source-layer': 'transportation', paint: { 'line-color': '#1262d1', 'line-width': ['interpolate', ['linear'], ['zoom'], 3, .4, 15, 4], 'line-blur': 2, 'line-opacity': .6 } },
    { id: 'roads', type: 'line', source: 'geography', 'source-layer': 'transportation', paint: { 'line-color': '#279ccc', 'line-width': ['interpolate', ['linear'], ['zoom'], 3, .2, 15, 1.1], 'line-opacity': .85 } },
    { id: 'buildings', type: 'fill-extrusion', source: 'geography', 'source-layer': 'building', minzoom: 14,
      paint: { 'fill-extrusion-color': '#146779', 'fill-extrusion-height': ['coalesce', ['get', 'render_height'], 0], 'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0], 'fill-extrusion-opacity': .65 } },
    { id: 'place-labels', type: 'symbol', source: 'geography', 'source-layer': 'place', layout: { 'text-field': ['coalesce', ['get', 'name:en'], ['get', 'name']], 'text-font': ['Noto Sans Regular'], 'text-size': ['interpolate', ['linear'], ['zoom'], 2, 10, 14, 13], 'text-max-width': 8 }, paint: { 'text-color': '#a4e7ed', 'text-halo-color': '#041125', 'text-halo-width': 1.5 } },
  ],
};

export default function GeographicMap({ view, enabled, reduced, locating, center, fallback }: {
  view: MapView | null; enabled: boolean; reduced: boolean; locating: boolean;
  center: [number, number]; fallback: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const map = useRef<Map | null>(null);
  const [ready, setReady] = useState(false);
  const [visible, setVisible] = useState(!document.hidden);
  const [error, setError] = useState('');
  useEffect(() => {
    const visibility = () => { setVisible(!document.hidden); if (document.hidden) map.current?.stop(); };
    document.addEventListener('visibilitychange', visibility);
    return () => document.removeEventListener('visibilitychange', visibility);
  }, []);
  useEffect(() => {
    if (!enabled || !host.current) return;
    let instance: Map;
    try {
      instance = new Map({ container: host.current, style, center: [center[1], center[0]], zoom: 5,
        pitch: reduced ? 0 : 44, bearing: reduced ? 0 : -10, maxPitch: 65,
        pixelRatio: 1, maxTileCacheSize: 80, attributionControl: { compact: false },
        transformRequest: url => {
          const target = new URL(url, location.href);
          if (target.origin !== 'https://tiles.openfreemap.org' && target.origin !== location.origin)
            throw new Error('Unexpected map resource host');
          return { url: target.href, credentials: 'same-origin' };
        },
      });
    } catch { fallback(); return; }
    map.current = instance;
    instance.addControl(new NavigationControl({ visualizePitch: true }), 'bottom-right');
    instance.on('error', () => setError('Some 3D map data could not load. You can switch to the 2D map.'));
    instance.on('load', () => {
      instance.addSource('destinations', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      instance.addSource('route', { type: 'geojson', lineMetrics: true, data: { type: 'FeatureCollection', features: [] } });
      instance.addLayer({ id: 'route-glow', type: 'line', source: 'route', paint: { 'line-color': '#25dfee', 'line-width': 11, 'line-blur': 7, 'line-opacity': .55 } });
      instance.addLayer({ id: 'route-line', type: 'line', source: 'route', paint: { 'line-color': '#67fff1', 'line-width': 3 } });
      instance.addLayer({ id: 'targets', type: 'circle', source: 'destinations', paint: { 'circle-radius': 7, 'circle-color': '#66fff1', 'circle-stroke-color': '#041629', 'circle-stroke-width': 3 } });
      setReady(true);
    });
    instance.getCanvas().addEventListener('webglcontextlost', fallback, { once: true });
    const resize = new ResizeObserver(() => {
      if (!host.current) return;
      const { width, height } = host.current.getBoundingClientRect();
      instance.setPixelRatio(Math.max(.25, Math.min(1.25, devicePixelRatio || 1, Math.sqrt(1_600_000 / Math.max(1, width * height)))));
      instance.resize();
    }); resize.observe(host.current!);
    return () => { resize.disconnect(); instance.remove(); map.current = null; setReady(false); };
  }, [enabled]);
  useEffect(() => {
    const instance = map.current;
    if (!ready || !instance || !visible) return;
    if (!view) {
      for (const id of ['destinations', 'route']) (instance.getSource(id) as GeoJSONSource).setData({ type: 'FeatureCollection', features: [] });
      return;
    }
    const targets = view.selected_destination === null ? view.destinations : [view.destinations[view.selected_destination]];
    (instance.getSource('destinations') as GeoJSONSource).setData({ type: 'FeatureCollection', features: targets.map(place => ({ type: 'Feature', properties: { name: place.label }, geometry: { type: 'Point', coordinates: [place.lon, place.lat] } })) });
    (instance.getSource('route') as GeoJSONSource).setData({ type: 'FeatureCollection', features: view.route ? [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: view.route.coordinates } }] : [] });
    const bounds = new LngLatBounds();
    for (const place of targets) bounds.extend([place.lon, place.lat]);
    for (const point of view.route?.coordinates ?? []) bounds.extend(point);
    if (!bounds.isEmpty()) instance.fitBounds(bounds, {
      padding: { top: 100, bottom: 120, left: innerWidth > 800 ? 400 : 35, right: 80 },
      maxZoom: targets.length === 1 && !view.route ? 15.5 : 14,
      pitch: reduced ? 0 : instance.getPitch() > 51 ? 47 : 55,
      bearing: reduced ? 0 : instance.getBearing() + 8,
      duration: reduced || document.hidden ? 0 : 6500,
      easing: t => t * t * (3 - 2 * t),
    });
  }, [view, ready, reduced, visible]);
  useEffect(() => {
    const instance = map.current;
    if (ready && instance && locating && visible && !reduced)
      instance.easeTo({ pitch: 46, bearing: instance.getBearing() + 8, duration: 5000,
        easing: t => t * t * (3 - 2 * t) });
  }, [locating, ready, visible, reduced]);
  return <>
    <div ref={host} className="geographic-map" data-testid="geographic-map" aria-label="Interactive 3D geographic map" />
    {locating ? <div className={`locating-overlay ${reduced || !visible ? 'still' : ''}`} role="status">
      <div className="locating-reticle"><i/><i/><i/></div><span>LOCATING REQUESTED PLACE</span><small>Waiting for a verified location</small>
    </div> : null}
    {error ? <p className="map-render-error" role="alert">{error} <button onClick={fallback}>Use 2D map</button></p> : null}
  </>;
}
