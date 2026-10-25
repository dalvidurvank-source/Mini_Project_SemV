import React from 'react';

export const deliveryLabels = {eligible:'Within delivery window',warning:'Limited delivery window',blocked:'Selling unavailable',unavailable:'Route unavailable'};

export default function ShelfLifeStatus({assessment:s,compact=false}) {
  return <div className={`shelf-status shelf-${s.status}`}>
    <strong>{deliveryLabels[s.status]}</strong><p>{s.reason}</p>
    {s.planning_budget_hours!==undefined&&<>
      <p className="small">Delivery buffer after safety margin: <strong>{s.slack_hours.toFixed(1)} hours</strong></p>
      {!compact&&<details><summary>How delivery eligibility is checked</summary>
        <dl className="breakdown"><div><dt>Crop condition</dt><dd>{s.condition_label}</dd></div><div><dt>Planning window from harvest</dt><dd>{s.planning_budget_hours} h</dd></div><div><dt>Age since harvest</dt><dd>{s.harvest_age_hours.toFixed(1)} h</dd></div><div><dt>Waiting for pickup</dt><dd>{s.waiting_hours.toFixed(1)} h</dd></div><div><dt>Earlier vehicle trips</dt><dd>{s.prior_trips_hours.toFixed(1)} h</dd></div><div><dt>Final outbound journey</dt><dd>{s.road_travel_hours.toFixed(1)} h</dd></div><div><dt>Final-trip handling</dt><dd>{s.handling_hours} h</dd></div><div><dt>Safety margin</dt><dd>{s.safety_margin_hours} h</dd></div></dl>
        <p className="small">Estimated last delivery: {new Date(s.estimated_last_delivery_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})} IST.</p>
        {s.date_only_harvest&&<p className="small">Harvest time was not entered, so age is counted from midnight on the harvest date.</p>}
        <p className="small muted">{s.notice}</p>
      </details>}
    </>}
  </div>;
}
