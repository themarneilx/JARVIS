import { useEffect, useRef, useState } from 'react';
import { api } from '../services/api';

interface Article { title: string; url: string; published: string; publisher: string }
interface Reading { at: string; price: number }
interface InformationView {
  receipt: string; kind: 'news' | 'stocks'; provider: string; fetched_at: string;
  verified_summary: string; query?: string; results?: Article[];
  symbol?: string; price?: number; currency?: string; as_of?: string; url?: string; history?: Reading[];
}
function SourceLink({ url, children }: { url: string; children: React.ReactNode }) {
  return url.startsWith('https://') ? <a href={url} target="_blank" rel="noopener noreferrer">{children} ↗</a> : <span>{children}</span>;
}
export function PriceChart({ readings, currency }: { readings: Reading[]; currency: string }) {
  const valid = readings.filter(p => Number.isFinite(p.price) && Number.isFinite(Date.parse(p.at)));
  if (valid.length < 2) return <p className="chart-unavailable">Intraday chart unavailable: the provider returned fewer than two usable samples.</p>;
  const prices = valid.map(p => p.price), low = Math.min(...prices), high = Math.max(...prices);
  const start = Date.parse(valid[0].at), end = Date.parse(valid[valid.length - 1].at);
  const points = valid.map(p => `${40 + (Date.parse(p.at) - start) / Math.max(1, end - start) * 720},${210 - (p.price - low) / Math.max(.000001, high - low) * 170}`).join(' ');
  return <figure className="stock-chart">
    <svg viewBox="0 0 800 260" role="img" aria-label={`Reported intraday prices, ${low.toFixed(2)} to ${high.toFixed(2)} ${currency}`}>
      {[40, 125, 210].map(y => <line key={y} x1="40" y1={y} x2="760" y2={y} stroke="#193b4d" />)}
      <polyline points={points} fill="none" stroke="#4fe9df" strokeWidth="2.5" vectorEffect="non-scaling-stroke" />
      <text x="40" y="25" fill="#8ab6c6" fontSize="12">{high.toFixed(2)} {currency}</text>
      <text x="40" y="240" fill="#8ab6c6" fontSize="12">{low.toFixed(2)} {currency}</text>
    </svg>
    <figcaption>{valid.length} returned samples · {new Date(start).toLocaleString()} — {new Date(end).toLocaleString()}</figcaption>
  </figure>;
}
export default function InformationPanel({ receipt, changed, close }: { receipt: string | null; changed: (id: string) => void; close: () => void }) {
  const [view, setView] = useState<InformationView | null>(null);
  const [kind, setKind] = useState<'news' | 'stocks'>('news');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<number | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const request = useRef<AbortController | null>(null);
  const revision = useRef(0);
  async function load(get: (signal: AbortSignal) => Promise<InformationView>) {
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    const id = ++revision.current; setBusy(true); setError('');
    try {
      const next = await get(controller.signal);
      if (id === revision.current && !controller.signal.aborted) {
        setView(next); changed(next.receipt); setKind(next.kind); setSelected(null);
      }
    } catch (e) { if (id === revision.current && !controller.signal.aborted) setError(String(e).replace(/^Error: /, '')); }
    finally { if (id === revision.current) setBusy(false); }
  }
  useEffect(() => {
    if (receipt && receipt !== view?.receipt) void load(signal => api<InformationView>(`/information/views/${receipt}`, { signal }));
  }, [receipt]);
  useEffect(() => () => { revision.current++; request.current?.abort(); }, []);
  const article = selected !== null ? view?.results?.[selected] : null;
  return <section className="information-overlay" aria-label="News and markets">
    <header className="information-heading">
      <div><small>JARVIS / INFORMATION</small><h1>News & markets</h1></div>
      <button onClick={close}>Back to core</button>
    </header>
    <form className="information-search" onSubmit={e => {
      e.preventDefault();
      void load(async signal => {
        const result = await api<{ information_receipt: string }>('/information/lookup', {
          method: 'POST', signal, body: JSON.stringify(kind === 'stocks' ? { kind, symbol: query.trim().toUpperCase() } : { kind, query }),
        });
        return api<InformationView>(`/information/views/${result.information_receipt}`, { signal });
      });
    }}>
      <label className="sr-only" htmlFor="information-kind">Information category</label>
      <select id="information-kind" value={kind} onChange={e => setKind(e.target.value as 'news' | 'stocks')}><option value="news">News & articles</option><option value="stocks">Stocks</option></select>
      <label className="sr-only" htmlFor="information-query">Topic or stock ticker</label>
      <input id="information-query" value={query} maxLength={kind === 'stocks' ? 20 : 300} onChange={e => setQuery(e.target.value)} placeholder={kind === 'stocks' ? 'Ticker, e.g. NVDA' : 'Topic, e.g. Cebu technology'} required />
      <button disabled={busy || !query.trim()}>{busy ? 'Retrieving…' : 'Look up'}</button>
    </form>
    {error ? <p className="information-error" role="alert">{error}</p> : null}
    {!view ? <div className="information-empty"><h2>Reports with a source.</h2><p>Ask Jarvis for news, articles or a stock quote. Verified results open here automatically. You can also look up a topic or ticker above.</p><p>Internet permission is controlled in Settings. No background market polling.</p></div> : <>
      <div className="information-source"><span>{view.provider}</span><time>Retrieved {new Date(view.fetched_at).toLocaleString()}</time></div>
      {view.kind === 'news' ? <div className={`news-layout ${article ? 'article-selected' : ''}`}>
        <div className="news-list">{view.results?.map((item, i) => <article key={item.url} className="news-card">
          <div className="news-meta"><span>{item.publisher || 'Publisher not supplied'}</span><time>{item.published}</time></div>
          <button className="news-title" onClick={() => setSelected(i)}>{item.title}</button>
          <SourceLink url={item.url}>Read original article</SourceLink>
        </article>)}</div>
        {article ? <article className="article-detail"><button className="article-close" onClick={() => setSelected(null)}>Close article details</button>
          <small>{article.publisher}</small><h2>{article.title}</h2><p>{article.published}</p>
          <p>This feed supplies the headline and source link. The full article has not been retrieved or summarized.</p>
          <SourceLink url={article.url}>Read full article at source</SourceLink>
        </article> : null}
      </div> : <article className="stock-report">
        <div className="stock-heading"><div><small>REPORTED MARKET QUOTE</small><h2>{view.symbol}</h2></div><div className="stock-price">{view.price?.toLocaleString(undefined, { maximumFractionDigits: 4 })}<small>{view.currency}</small></div></div>
        <p>Last reported regular-market trade: {view.as_of ? new Date(view.as_of).toLocaleString() : 'Time unavailable'}. Prices may be delayed.</p>
        <PriceChart readings={view.history ?? []} currency={view.currency ?? ''} />
        {view.url ? <SourceLink url={view.url}>View market source</SourceLink> : null}
      </article>}
    </>}
  </section>;
}
