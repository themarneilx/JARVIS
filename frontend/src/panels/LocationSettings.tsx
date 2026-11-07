import { useEffect, useState } from 'react';
import { api, post } from '../services/api';
import type { OnlineSettings, Place } from '../services/types';

export function LocationSettings({ changed }: { changed: () => void }) {
  const [settings,setSettings]=useState<OnlineSettings|null>(null);
  const [query,setQuery]=useState(''),[places,setPlaces]=useState<Place[]>([]);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  useEffect(()=>{
    let disposed=false;
    void api<OnlineSettings>('/information/settings').then(value=>{if(!disposed)setSettings(value);}).catch(e=>{if(!disposed)setError(String(e));});
    return ()=>{disposed=true;};
  },[]);
  async function save(value: OnlineSettings) {
    const previous=settings;
    setSettings(value);
    setBusy(true);setError('');setNotice('');
    try {
      setSettings(await post<OnlineSettings>('/information/settings',value));
      setNotice('Defaults saved on this computer.');changed();
    } catch(e){setSettings(previous);setError(e instanceof Error?e.message:'Defaults could not be saved.');}
    finally{setBusy(false);}
  }
  async function search() {
    setBusy(true);setError('');setNotice('');
    try {
      const result=await api<{results:Place[]}>('/information/cities?query='+encodeURIComponent(query));
      setPlaces(result.results);
      if(!result.results.length)setNotice('No matching cities. Try the town name without province or country.');
    } catch(e){setError(e instanceof Error?e.message:'City search failed.');}
    finally{setBusy(false);}
  }
  return <section className="panel location-settings">
    <div className="panel-title"><h2>Location & internet</h2></div>
    {!settings?<p role="status">Loading your defaults…</p>:<>
      <label className="check-label"><input type="checkbox" checked={settings.enabled} disabled={busy} onChange={e=>void save({...settings,enabled:e.target.checked})}/>Enable internet information lookups</label>
      <p className="muted">Inference stays local. Searches go to Hermes DDGS, news to Google News, weather to Open-Meteo, rates to Frankfurter quotes to Yahoo Finance, and maps/place searches/driving routes to OpenStreetMap and OSRM. Map tiles load directly in the browser while the map is open. These providers receive the query or city coordinates needed for your request.</p>
      <p>Saved city: <strong>{settings.location?`${settings.location.name}, ${settings.location.country}`:'Not set'}</strong></p>
      <form onSubmit={e=>{e.preventDefault();void search();}}>
        <label>Find city or town<input value={query} onChange={e=>setQuery(e.target.value)} maxLength={100} placeholder="City or town name" disabled={busy||!settings.enabled}/></label>
        <button disabled={busy||!settings.enabled||query.trim().length<2}>Search cities</button>
      </form>
      {places.length?<ul className="place-results">{places.map(place=><li key={place.id}><span>{place.name}, {place.country} · {place.timezone}</span><button disabled={busy} onClick={()=>{setPlaces([]);void save({...settings,location:place,timezone:place.timezone});}}>Use this city</button></li>)}</ul>:null}
      <form onSubmit={e=>{e.preventDefault();void save(settings);}}>
        <label>Default timezone<input list="known-timezones" value={settings.timezone} maxLength={80} onChange={e=>setSettings({...settings,timezone:e.target.value})} disabled={busy}/></label>
        <datalist id="known-timezones"><option value="Asia/Manila"/><option value="UTC"/><option value="Asia/Singapore"/><option value="America/New_York"/><option value="Europe/London"/></datalist>
        <div className="button-row"><button disabled={busy}>Save timezone</button><button type="button" disabled={busy||!settings.location} onClick={()=>void save({...settings,location:null})}>Clear saved city</button></div>
      </form>
      <p className="muted">A saved city supplies weather defaults; it does not track GPS. Weather is a model estimate, FX a dated daily reference, and stock trades may be delayed. Lookups run when requested, without background AI inference.</p>
    </>}
    {notice?<p role="status">{notice}</p>:null}
    {error?<p role="alert" className="warning">{error}</p>:null}
  </section>;
}
