import React from 'react';
import { money } from '../utils/format';

export default function RouteSummary({transport:t}) {
  const r = t.route_plan;
  return <section className="route-summary" aria-labelledby="route-title"><span className="eyebrow">YOUR JOURNEY TO MARKET</span><h3 id="route-title">{r.origin.name} → {r.destination.name}</h3>
    <div className="route-stats"><div><strong>{r.distance_km.toFixed(1)} km</strong><span>Road distance, one way</span></div><div><strong>{Math.round(r.duration_minutes)} min</strong><span>Estimated driving time, one way</span></div><div><strong>{money(t.total_trip_cost_inr)}</strong><span>Transport · {t.trips} {t.trips===1?'trip':'trips'}</span></div></div>
    <ol className="route-stops" aria-label="Selected route stops">{r.path.map((p,i)=><li key={p.id}><span>{i===0?r.origin.name:i===r.path.length-1?r.destination.name:p.id.replace(/^HUB_/,'').replaceAll('_',' ')}</span></li>)}</ol>
    <p className="small muted">Haversine direct distance: {r.straight_line_km.toFixed(1)} km. Transport uses road distance. Dijkstra selects the lowest travel time across the available road legs; each leg comes from OSRM’s fastest-driving routes.</p>
    <details><summary>Route and transport breakdown</summary><dl className="breakdown">{Object.entries(t.components_inr).map(([k,v])=><div key={k}><dt>{k[0].toUpperCase()+k.slice(1)}</dt><dd>{money(v)}</dd></div>)}<div><dt>Vehicle capacity</dt><dd>{t.vehicle.capacity_kg} kg</dd></div><div><dt>Fuel assumption</dt><dd>{money(t.fuel.price_inr_per_litre)} / litre · {t.fuel.efficiency_km_per_litre} km/l</dd></div><div><dt>Return-distance allowance</dt><dd>{(t.route.empty_return_factor*100).toFixed(0)}% of outbound distance</dd></div></dl><p className="small muted">Source: {r.provider}. Retrieved {new Date(r.retrieved_at).toLocaleString('en-IN')}. Fuel and handling charges are planning assumptions, not live quotes. Each trip uses the same route and per-trip charges.</p><div className="table-scroll"><table><thead><tr><th>Road leg</th><th>Distance</th><th>Time</th></tr></thead><tbody>{r.legs.map((leg,i)=><tr key={i}><td>{i+1}</td><td>{leg.distance_km.toFixed(1)} km</td><td>{leg.duration_minutes.toFixed(0)} min</td></tr>)}</tbody></table></div></details>
  </section>;
}
