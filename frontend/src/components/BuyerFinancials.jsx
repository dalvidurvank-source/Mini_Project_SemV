import React from 'react';
import { money } from '../utils/format';

export default function BuyerFinancials({buyer:b}) {
  const f=b.financial;
  if(!f)return null;
  const priced=f.gross_sale_inr!==null;
  return <section className="buyer-financials" aria-label="Buyer financial comparison">
    <div className="rank-line">{f.rankable&&<span className={`rank-badge ${f.is_best?'rank-best':''}`}>{f.is_best?'Best estimated return':`Rank ${f.rank}`} · {f.sale_scope==='full_harvest'?'full harvest':`${f.sale_quantity_kg} kg partial sale`}</span>}{!f.rankable&&<span className="unranked-badge">Not financially ranked</span>}</div>
    <p className="small ranking-reason">{f.ranking_reason}</p>
    <dl className="buyer-metrics"><div><dt>{f.offer_label}</dt><dd>{f.price_inr_per_kg===null?'Price not available':`${money(f.price_inr_per_kg)} / kg`}</dd></div><div><dt>Buyer purchase capacity</dt><dd>{f.buyer_capacity_kg===null?'Not provided':`${f.buyer_capacity_kg.toLocaleString('en-IN')} kg`}</dd></div>
      <div><dt>{f.acceptance_status==='unknown'?'Proposed quantity (unconfirmed)':'Planned sale quantity'}</dt><dd>{f.sale_quantity_kg.toLocaleString('en-IN')} kg</dd></div><div><dt>Remaining unsold harvest</dt><dd>{f.unsold_quantity_kg===null?'Not confirmed':`${f.unsold_quantity_kg.toLocaleString('en-IN')} kg`}</dd></div>
      <div><dt>Estimated gross sale value</dt><dd>{priced?money(f.gross_sale_inr):'Unavailable'}</dd></div><div><dt>Known additional selling charges</dt><dd>{priced?money(f.other_selling_charges_inr):'Unavailable'}</dd></div>
    </dl>
    {priced&&<div className={`buyer-net ${f.net_return_inr<0?'buyer-loss':''}`}><span>{f.net_return_inr<0?'Estimated loss for this sale':'Estimated net return for this sale'}</span><strong>{money(f.net_return_inr)}</strong><span>{money(f.net_per_sellable_kg)} per planned sold kg</span></div>}
    {f.status!=='available'&&<p className="notice small">{f.reason}{!f.can_prepare_draft&&' Selection is unavailable for this quantity or offer.'}</p>}
    {f.sale_scope==='partial'&&f.acceptance_status==='accepted'&&<p className="notice small">Partial sale only. {f.unsold_quantity_kg} kg remains unsold and has no assumed resale value. Compare this result only with offers for {f.sale_quantity_kg} kg.</p>}
    <details><summary>Financial breakdown and assumptions</summary>
      {f.minimum_quantity_kg!==null&&<p className="small">Minimum accepted quantity: {f.minimum_quantity_kg} kg. {f.offer_source&&`Offer source: ${f.offer_source}. `}{f.valid_until&&`Quote valid until ${new Date(f.valid_until).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})} IST.`}</p>}
      {priced&&<dl className="breakdown"><div><dt>{f.sale_quantity_kg} kg × {money(f.price_inr_per_kg)}</dt><dd>{money(f.gross_sale_inr)}</dd></div><div><dt>Route-derived transport expense</dt><dd>− {money(f.transport_cost_inr)}</dd></div>{f.charge_breakdown.map((c,i)=><div key={i}><dt>{c.label}{c.type==='percent_of_gross'?` (${c.value}% of gross)`:c.type==='per_kg'?` (${money(c.value)}/kg)`:''}</dt><dd>− {money(c.amount_inr)}</dd></div>)}<div className="total"><dt>Estimated net return</dt><dd>{money(f.net_return_inr)}</dd></div></dl>}
      <p className="small">Only buyers selling the same quantity are compared. A higher price can offset a longer journey; distance is not the ranking score. Unranked route costs, if shown, apply to {f.transport_quantity_kg} kg.</p>
      <ul className="small muted">{f.assumptions.map(a=><li key={a}>{a}</li>)}</ul><p className="small muted">Estimates are not guaranteed. Demo prices are illustrative; no historical or forecast mandi price is presented as a buyer offer.</p>
    </details>
  </section>;
}
