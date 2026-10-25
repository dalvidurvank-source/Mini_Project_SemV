import React from 'react';
import { money } from '../utils/format';

export default function RecordedPrice({ result:r }) {
  const a=r.actual, verified=r.context.units.configured;
  const show=n=>verified&&r.context.units.unit==='INR/quintal'?money(n/100):new Intl.NumberFormat('en-IN',{maximumFractionDigits:2}).format(n);
  return <section id="recommendation" className="result" tabIndex="-1" aria-labelledby="recorded-title">
    <span className="eyebrow">RECORDED MARKET DATA · NOT A FORECAST</span>
    <h2 id="recorded-title">Recorded tomato price</h2>
    <p>{r.context.source} · Observation date {a.date}</p>
    <div className="price-banner"><span>Recorded modal price · {verified?'INR per kilogram':'original source units'}</span><div className="price-range">{show(a.modal_price)}</div><p>Minimum {show(a.min_price)} · Maximum {show(a.max_price)}</p><small>Retrieved {a.retrieved_at||'timestamp unavailable'} · Grade {a.grade||'not supplied'}</small></div>
    <div className="quality-panel"><h3>Provenance and limits</h3><p>{a.provenance||`Source files: ${(a.source_files||[]).join(', ')}`}.</p><ul>{r.warnings.map(w=><li key={w}>{w}</li>)}</ul><p>No model, future estimate, fair-price band, or sale-price guarantee is attached to this observation.</p></div>
  </section>;
}
