import React, { useEffect, useRef, useState } from 'react';
import { request } from '../api/client';
import { money } from '../utils/format';
import LocationFields from './LocationFields';
import ShelfLifeStatus from './ShelfLifeStatus';
import BuyerFinancials from './BuyerFinancials';

const STORAGE = 'agrolink.harvest-draft.v1';
const draftKeys = ['crop','quantity','unit','harvest_date','harvest_time','selling_date','pickup_at','produce_condition',
  'farm_name','farm_latitude','farm_longitude','vehicle_type','vehicle_capacity_kg','fuel_efficiency_km_per_litre',
  'fuel_price_inr_per_litre','empty_return_factor','loading_inr','unloading_inr','tolls_inr','allow_partial_sales'];

export default function BuyerMarketplace({catalog,form,change,field,useSample,busy,onBusy}) {
  const [response,setResponse] = useState(null), [error,setError] = useState(''), [saved,setSaved] = useState(false);
  const [selection,setSelection] = useState(null), [ack,setAck] = useState({}), [clock,setClock] = useState(Date.now());
  const [storageMessage,setStorageMessage] = useState(''), [hasDraft,setHasDraft] = useState(false);
  const active = useRef(null), lock = useRef(false), inputKey = JSON.stringify(form);
  useEffect(()=>{
    setResponse(null);setSelection(null);setAck({});setSaved(false);setError('');
    active.current?.abort();
  },[inputKey]);
  useEffect(()=>{
    try {setHasDraft(!!localStorage.getItem(STORAGE));} catch {setStorageMessage('Browser storage is unavailable; you can still check buyers.');}
    const timer=setInterval(()=>setClock(Date.now()),15000);
    const focus=()=>setClock(Date.now()); window.addEventListener('focus',focus);
    return ()=>{clearInterval(timer);window.removeEventListener('focus',focus);active.current?.abort();};
  },[]);
  function persist() {
    try {
      const values=Object.fromEntries(draftKeys.filter(k=>form[k]!==undefined).map(k=>[k,form[k]]));
      localStorage.setItem(STORAGE,JSON.stringify({version:1,saved_at:new Date().toISOString(),values}));
      setHasDraft(true);setSaved(true);setStorageMessage('Harvest draft saved in this browser. It has not been published.');
    } catch {setStorageMessage('Could not save to this browser. Buyer checks still work.');}
  }
  function restore() {
    try {
      const draft=JSON.parse(localStorage.getItem(STORAGE));
      if(draft?.version!==1||!draft.values||typeof draft.values!=='object') throw new Error();
      change(Object.fromEntries(draftKeys.filter(k=>draft.values[k]!==undefined).map(k=>[k,draft.values[k]])));
      setStorageMessage('Saved harvest restored. Check its dates and refresh buyers.');
    } catch {setStorageMessage('The saved draft could not be restored. Enter the harvest again.');}
  }
  function clearDraft() {
    try {localStorage.removeItem(STORAGE);setHasDraft(false);setSaved(false);setStorageMessage('Saved harvest draft removed from this browser.');}
    catch {setStorageMessage('Browser storage could not be cleared.');}
  }
  async function findBuyers(e) {
    e.preventDefault(); if(lock.current)return;
    lock.current=true;onBusy(true);setError('');setResponse(null);setSelection(null);setAck({});persist();
    const controller=new AbortController();active.current=controller;
    try {const r=await request('/buyer-suggestions',{body:form,signal:controller.signal});setResponse(r);setClock(Date.now());}
    catch(e) {if(!controller.signal.aborted)setError(e.message);}
    finally {lock.current=false;onBusy(false);}
  }
  async function select(buyer) {
    if(lock.current)return;
    lock.current=true;onBusy(true);setError('');
    const controller=new AbortController();active.current=controller;
    try {
      const r=await request('/buyer-selection',{body:{...form,buyer_id:buyer.id,acknowledge_warning:ack[buyer.id]===true},signal:controller.signal});
      setSelection(r);
    } catch(e) {if(!controller.signal.aborted){setError(e.message);setResponse(null);}}
    finally {lock.current=false;onBusy(false);}
  }
  function expirySample() {
    useSample();
    const local = new Date(Date.now()-38*3600000+330*60000).toISOString();
    change({harvest_date:local.slice(0,10),harvest_time:local.slice(11,16),selling_date:catalog.listing_date,
            pickup_at:'',produce_condition:'firm_ripe',quantity:'500',unit:'kg',vehicle_capacity_kg:1000});
  }
  if(!catalog)return <p role="status">Loading harvest and delivery settings…</p>;
  const stale=response&&clock-Date.parse(response.evaluated_at)>response.refresh_after_seconds*1000;
  return <section className="marketplace" id="buyer-panel" role="tabpanel" aria-labelledby="buyers-tab">
    <div className="marketplace-heading"><div><span className="eyebrow">MY HARVEST & BUYERS</span><h1>A buyer your harvest<br/>can reach in time.</h1><p>Compare what you could receive after delivery and selling costs, then prepare a sale draft.</p></div><span className="demo-tag">Demo buyers · farmer preview</span></div>
    <div className="notice">These sample destinations demonstrate matching and spoilage checks; no sale is published or sent. Use Accounts & marketplace for saved account listings and buyer-submitted offers.</div>
    <div className="marketplace-layout"><form onSubmit={findBuyers} aria-busy={busy}>
      <fieldset disabled={busy}><legend>Your harvest listing</legend><div className="fields">
        {field('crop','Crop',catalog.crops)}{field('quantity','Quantity available',null,{type:'number',min:0.01,step:'any',required:true})}{field('unit','Quantity unit',['kg','quintal'])}
        {field('harvest_date','Harvest date',null,{type:'date',max:catalog.listing_date,required:true})}{field('harvest_time','Harvest time (IST, optional)',null,{type:'time'})}
        {field('produce_condition','Crop condition',catalog.shelf_life_policy.conditions.map(c=>({value:c.id,label:c.label})))}
        {field('selling_date','Earliest pickup date',null,{type:'date',min:catalog.listing_date,required:true})}
        {field('pickup_at','Planned pickup (IST, optional)',null,{type:'datetime-local'})}
      </div><label className="checkbox"><input type="checkbox" checked={form.allow_partial_sales===true} onChange={e=>change({allow_partial_sales:e.target.checked})}/><span>Allow partial sales when a buyer cannot take my entire harvest.</span></label><p className="small muted">Partial offers are compared separately by quantity; any remainder stays unsold. Leave pickup time blank for immediate pickup on the selected day. A harvest without a time is conservatively counted from midnight. Delivery checks use actual harvest dates, independently of historical forecasts.</p></fieldset>
      <LocationFields form={form} change={change} field={field} busy={busy} useSample={useSample} notice={catalog.logistics.notice}/>
      <fieldset disabled={busy}><legend>Vehicle and delivery assumptions</legend><div className="fields">{field('vehicle_capacity_kg','Vehicle capacity (kg)',null,{type:'number',min:1,step:'any',required:true})}{field('empty_return_factor','Empty-return factor (0–1)',null,{type:'number',min:0,max:1,step:0.1,required:true})}</div><p className="small muted">One vehicle makes sequential trips. The last load must still arrive in time. Other cost assumptions carry over from the calculator.</p><details><summary>Delivery-life planning policy</summary><p>{catalog.shelf_life_policy.notice}</p><ul>{catalog.shelf_life_policy.conditions.map(c=><li key={c.id}>{c.label}: {c.hours} hours from harvest.</li>)}</ul><p>Each trip allows {catalog.shelf_life_policy.handling_hours} hours for handling and reserves a {catalog.shelf_life_policy.safety_margin_hours}-hour safety margin. At most {catalog.shelf_life_policy.warning_slack_hours} hours of buffer triggers a warning.</p></details></fieldset>
      <div className="location-actions"><button type="button" className="secondary-button" disabled={busy} onClick={expirySample}>Try a near-expiry harvest</button>{hasDraft&&<><button type="button" className="secondary-button" disabled={busy} onClick={restore}>Restore saved harvest</button><button type="button" className="secondary-button" disabled={busy} onClick={clearDraft}>Delete saved draft</button></>}</div>
      {storageMessage&&<p className="small" role="status">{storageMessage}</p>}
      <button className="button submit" disabled={busy} type="submit">{busy?'Checking road routes and delivery windows…':'Save harvest & find buyers'}</button>
    </form><div className="buyer-results" aria-live="polite">
      <article className="harvest-card"><span className="eyebrow">YOUR HARVEST</span><h2>{form.crop} · {form.quantity||'—'} {form.unit}</h2><p>Harvested {form.harvest_date||'date needed'}{form.harvest_time?` at ${form.harvest_time} IST`:''}</p><p>{form.farm_name||'Add a pickup location'} · {saved?'Saved locally':'Unsaved changes / draft'}</p></article>
      {error&&<div className="error" role="alert">{error}<p>Recheck your details and refresh buyers before selecting again.</p></div>}
      {!response&&!busy&&<p>Save the harvest to compare eligible buyers by estimated net return. Missing offers stay visible but unranked. Buyers that cannot accept the quantity or meet the delivery window cannot be selected.</p>}
      {response&&<><p className="small muted">{response.notice}</p><p className="small">{response.ranking_policy}</p>{stale&&<p className="notice">Delivery checks are over a minute old. Refresh buyers before selecting.</p>}
        <div className="buyer-cards">{response.buyers.map(b=>{const s=b.shelf_life, selectable=b.selection_allowed;return <article className={`buyer-card buyer-${s.status} ${b.financial?.is_best?'buyer-best':''}`} key={b.id} data-testid={`buyer-${b.id}`}><span className="demo-tag">{b.demo?'Demo buyer':'Buyer · verification not established'}</span><h3>{b.name}</h3><p className="small muted">{b.description}</p><BuyerFinancials buyer={b}/><ShelfLifeStatus assessment={s}/>
          {b.transport&&<dl className="buyer-metrics"><div><dt>Road distance</dt><dd>{b.transport.route_plan.distance_km.toFixed(1)} km</dd></div><div><dt>One-way drive</dt><dd>{b.transport.route_plan.duration_minutes.toFixed(0)} min</dd></div><div><dt>{b.financial?.acceptance_status==='rejected'?'Transport scenario (sale not accepted)':'Batch transport'}</dt><dd>{money(b.transport.total_trip_cost_inr)}</dd></div><div><dt>Vehicle trips</dt><dd>{b.transport.trips}</dd></div></dl>}
          {s.requires_acknowledgment&&selectable&&<label className="checkbox"><input type="checkbox" disabled={busy||stale} checked={ack[b.id]||false} onChange={e=>setAck(a=>({...a,[b.id]:e.target.checked}))}/><span>I understand the limited delivery window and will confirm crop condition and pickup timing.</span></label>}
          <button className="button" type="button" disabled={busy||stale||!selectable||(s.requires_acknowledgment&&!ack[b.id])} onClick={()=>select(b)}>{!selectable?'Selling unavailable':b.financial?.status==='available'?'Prepare sale draft':'Prepare unpriced enquiry'}</button>
        </article>})}</div></>}
      {selection&&<div className="selection-confirmation" role="status"><h3>{selection.financial_mode==='unpriced_enquiry'?'Unpriced enquiry draft prepared':'Sale draft prepared'}</h3><p>{selection.buyer.name}</p>{selection.buyer.financial?.net_return_inr!=null&&<p>Rechecked estimated net return: {money(selection.buyer.financial.net_return_inr)} for {selection.buyer.financial.sale_quantity_kg} kg. Remaining unsold: {selection.buyer.financial.unsold_quantity_kg} kg.</p>}<p>{selection.notice}</p></div>}
    </div></div>
  </section>;
}
