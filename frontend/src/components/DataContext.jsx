import React from 'react';

export default function DataContext({ form, context, loading, error, errors, busy, change, retry }) {
  const po = form.source === 'price_only' || form.source === 'official';
  const e = context?.eligibility;
  return <div className="context-panel"><span className="eyebrow">AVAILABLE MARKET CONTEXT</span>
    {loading ? <p role="status">Reading observations and evaluating available models…</p> : context ? <>
      <p><strong>{form.market}</strong> · Latest observation {context.latest_observation}</p>
      <p>{po ? `${context.observed_sessions} reporting sessions` : `${context.observed_months} observed months`} · {context.stale ? 'Stale observations' : 'Recent observations'}</p>
      {po ? <>
        <p><strong>{e.status === 'eligible' ? 'Forecast evidence available' : 'Forecast unavailable'}</strong>{e.reason ? ` — ${e.reason}` : ''}</p>
        <p>Latest usable segment: {e.segment_sessions ?? 'unavailable'} sessions. {e.gap_info?.excluded_earlier_sessions ?? 0} earlier sessions excluded across long gaps. No missing dates are filled.</p>
        <p>Recorded mode returns an exact observation. Historical mode trains strictly before a recorded target. Future mode supports <strong>one subsequent reporting session</strong>; its calendar date is unknown.</p>
        {e.status === 'eligible' && <p>Selection winner: <strong>{e.selected_model}</strong> · Selection targets: {e.selection[e.selected_model].count} · Separate final holdout: {e.evaluation.count} targets ({e.evaluation.first_target}–{e.evaluation.last_target}).</p>}
        {context.source_files&&<p>Source files: {context.source_files.join(', ')}.</p>}
        {context.retrieval_timestamps&&<p>Retrieval timestamps: {context.retrieval_timestamps.join(', ')}.</p>}
        {!context.units.configured && <p className="notice">{context.units.reason} When the selected mode has enough observations, its forecast can be shown only in unverified source units; no INR conversion or fair-price recommendation will be shown.</p>}
        {context.units.configured && <p>Configured source unit: {context.units.unit}. Confirmation: {context.units.evidence}</p>}
      </> : <p>The existing model forecasts <strong>{context.forecast_month} only</strong>. Choose a selling date in that month for analysis. It cannot forecast a different selling month.</p>}
      {context.stale && (!po || form.mode === 'future') && <label className="checkbox"><input id="acknowledge_stale" type="checkbox" disabled={busy} checked={form.acknowledge_stale} onChange={ev => change('acknowledge_stale', ev.target.checked)} aria-invalid={!!errors.acknowledge_stale}/><span>{po ? `I understand this next-session projection starts from a ${context.age_days}-day-old observation and is not a current market-price forecast.` : 'I understand this is historical analysis, not a current price recommendation.'}</span></label>}
      {errors.acknowledge_stale && <p className="field-error">{errors.acknowledge_stale}</p>}
    </> : <p>Select a market and variety to review eligibility.</p>}
    {error && <div className="error" role="alert">{error}<button type="button" onClick={retry}>Retry history</button></div>}
    <p className="small muted">Weather unavailable — no live source is configured. Reliable live demand/supply inputs are unavailable.</p>
  </div>;
}
