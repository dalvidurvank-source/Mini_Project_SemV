import React from 'react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { money } from '../utils/format';
export default function MarketPriceChart({ context, forecast }) {
  if (!context?.history?.length) return null;
  const po = context.source_id === 'price_only' || context.source_id === 'official';
  const converted = !po || context.units.configured;
  const format = v => converted ? money(v) : new Intl.NumberFormat('en-IN', {maximumFractionDigits:2}).format(v);
  const shown = context.history.slice(po ? -90 : -36);
  const maxGap = po ? context.eligibility?.policy.max_gap_days ?? 7 : 40;
  const history = [];
  shown.forEach((p,i) => {
    const time = Date.parse(p.date);
    if (i && (time - Date.parse(shown[i-1].date))/86400000 > maxGap) history.push({time: time-1, date:'Gap - no observations', actual:null});
    history.push({time, date:p.date, actual:p.price});
  });
  const data = !po && forecast ? [...history.map((p,i) => i===history.length-1?{...p,prediction:p.actual}:p),{time:Date.parse(context.forecast_month+'-01'),date:context.forecast_month+'-01',prediction:forecast.base/100}] : history;
  const tick = t => new Date(t).toISOString().slice(0,po?10:7);
  return <section className="chart-section"><div className="section-top"><div><span className="eyebrow">THE MARKET IN CONTEXT</span><h3>Recorded prices, clearly shown.</h3></div><span className="unit-tag">{converted?'INR / kg':'Source units unverified'}</span></div>
    <p className="muted">{context.history.length} recorded {po?'reporting sessions':'months'} · {po?'Daily modal prices; latest 90 observations shown. Reporting dates have true calendar spacing.':'Arrival-weighted monthly modal price; latest 36 observations shown.'} Long gaps break the line; no observations are invented.</p>
    <div className="legend"><span>&#9679; Recorded observation</span>{forecast&&!po&&<span>&#9476; One-month forecast</span>}</div>
    <div className="chart" role="img" aria-label="Historical tomato prices on their actual observation dates. A table of the observations follows."><ResponsiveContainer width="100%" height={260}><LineChart data={data} margin={{top:10,right:20,bottom:10,left:0}}><CartesianGrid vertical={false} stroke="#e5e9e2"/><XAxis dataKey="time" type="number" scale="time" domain={['dataMin','dataMax']} tickFormatter={tick} minTickGap={45} tick={{fontSize:10}}/><YAxis tick={{fontSize:11}} width={45}/><Tooltip formatter={v=>format(v)} labelFormatter={v=>tick(v)}/><Line name="Recorded" type="linear" dataKey="actual" stroke="#24513b" strokeWidth={2} dot={{r:2}} connectNulls={false}/>{!po&&<Line name="Forecast" type="linear" dataKey="prediction" stroke="#a66b2f" strokeWidth={2} strokeDasharray="5 5" dot={{r:3}}/>}</LineChart></ResponsiveContainer></div>
    {po&&forecast&&<p className="notice"><strong>Forecast — next reporting session:</strong> {format(converted?forecast.base/100:forecast.prediction_native)} {converted?'INR/kg':'in unverified source units'}. Origin: {forecast.origin}. No calendar date is assigned, so the forecast is not plotted on the date axis.</p>}
    <details><summary>View price observations as a table</summary><div className="table-scroll"><table><thead><tr><th>Recorded date</th><th>{converted?'Recorded INR/kg':'Original source price'}</th><th>Source</th></tr></thead><tbody>{shown.map(p=><tr key={p.date}><td>{p.date}</td><td>{format(p.price)}</td><td>{p.source_files?.join(', ')||p.provenance||context.source}</td></tr>)}</tbody></table></div></details>
  </section>;
}
