import React from 'react';
import MarketPriceChart from './MarketPriceChart';

export default function ForecastPreview({ result: r }) {
  const f = r.forecast, report = f.report;
  const native = n => new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(n);
  return <section id="recommendation" className="result" tabIndex="-1" aria-labelledby="preview-title">
    <span className="eyebrow">{r.mode==='historical'?'HISTORICAL FORECAST EVALUATION':'FORECAST'} · PRICE UNITS UNVERIFIED</span>
    <h2 id="preview-title">{r.mode==='historical'?'Forecast compared with recorded price':'Next reporting-session estimate'}</h2>
    <p>{r.crop} · {r.market} · {r.variety}</p>
    <div className="price-banner"><span>Forecast in original source units — currency/weight not confirmed</span><div className="price-range">{native(f.prediction_native)}</div><p>Origin: {f.origin} · Target: {f.forecast_date||'next reporting session; calendar date unknown'}</p>{r.actual&&<p>Separately recorded actual modal price: <strong>{native(r.actual.modal_price)}</strong></p>}<small>{r.mode==='historical'?'The target observation was excluded from training.':'One subsequent reporting session; this is not a guaranteed sale price.'}</small></div>
    <h3>Why this forecast?</h3><p>The {f.name} method was selected using only the earlier selection window. It was then evaluated against {report.evaluation.count} later, unseen targets. The final forecast uses {report.segment_sessions} observations in the latest usable segment. No arrivals, weather or demand inputs were invented.</p>
    <h3>Selection comparison</h3><p className="muted">MAE/RMSE below use unverified source price units. Selection errors choose the method; final errors independently describe the frozen winner.</p>
    <div className="table-scroll"><table><thead><tr><th>Candidate</th><th>Selection MAE</th><th>Selection RMSE</th></tr></thead><tbody>{Object.entries(report.selection).map(([name, v]) => <tr key={name}><td>{name}</td><td>{native(v.MAE)}</td><td>{native(v.RMSE)}</td></tr>)}</tbody></table></div>
    <dl className="metadata"><div><dt>Frozen winner</dt><dd>{f.name}</dd></div><div><dt>Final holdout targets</dt><dd>{report.evaluation.first_target}–{report.evaluation.last_target} ({report.evaluation.count})</dd></div><div><dt>Final MAE / RMSE</dt><dd>{native(f.metrics.MAE)} / {native(f.metrics.RMSE)}</dd></div><div><dt>Last-price baseline final MAE</dt><dd>{native(report.baseline_evaluation.MAE)}</dd></div></dl>
    <div className="quality-panel"><h3>Limits of this result</h3><ul>{r.warnings.map(w => <li key={w}>{w}</li>)}</ul><p>{r.context.source_files?`Source files: ${r.context.source_files.join(', ')}. `:''}Latest recorded observation: {r.context.latest_observation}.</p><p>No fair-price band, transport allocation, or proposed-price comparison is calculated until the source currency and weight unit are confirmed.</p></div>
    <MarketPriceChart context={r.context} forecast={f}/>
  </section>;
}
