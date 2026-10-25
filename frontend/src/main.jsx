import React, { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { request } from './api/client';
import { money } from './utils/format';
const MarketPriceChart = lazy(() => import('./components/MarketPriceChart'));
import LocationFields from './components/LocationFields';
import RouteSummary from './components/RouteSummary';
import ShelfLifeStatus from './components/ShelfLifeStatus';
const BuyerMarketplace = lazy(() => import('./components/BuyerMarketplace'));
const AccountWorkspace = lazy(() => import('./components/AccountWorkspace'));
import './styles.css';

function App() {
  const [catalog, setCatalog] = useState(null), [form, setForm] = useState({crop:'Tomato', quantity:'', unit:'kg', harvest_date:'', harvest_time:'', produce_condition:'firm_ripe', pickup_at:'', selling_date:'', farm_name:'', farm_latitude:'', farm_longitude:'', destination_latitude:'', destination_longitude:''});
  const [tab,setTab] = useState('calculator');
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [result, setResult] = useState(null), [retry, setRetry] = useState(0);
  const lock = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    setError('');
    request('/listing-defaults', {signal:controller.signal}).then(data => {
      setCatalog(data);
      const pin = data.logistics.market_pins.find(p=>['state','district','market'].every(k=>p[k]===data.default_market[k]));
      setForm(f => ({...data.logistics.vehicle,...f, ...data.default_market, harvest_date:f.harvest_date || data.listing_date,
                     selling_date:f.selling_date || data.listing_date, destination_latitude:pin?.latitude ?? '', destination_longitude:pin?.longitude ?? ''}));
    }).catch(e => {if (e.name !== 'AbortError') setError(e.message);});
    return () => controller.abort();
  }, [retry]);
  function change(key, value) {
    setForm(f => {
      const next = {...f, [key]:value};
      if (['state','district','market'].includes(key)) {
        const keys = ['state','district','market','variety'];
        const index = keys.indexOf(key);
        const match = catalog.markets.find(m => keys.slice(0,index+1).every(k => m[k] === next[k]));
        if (match) Object.assign(next, match);
        const pin = catalog.logistics.market_pins.find(p=>['state','district','market'].every(k=>p[k]===next[k]));
        next.destination_latitude = pin?.latitude ?? '';
        next.destination_longitude = pin?.longitude ?? '';
      }
      return next;
    });
    setResult(null); setError('');
  }
  function changeMany(values) {setForm(f=>({...f,...values})); setResult(null); setError('');}
  function useSample() {
    const f = catalog.logistics.demo_farm, m = catalog.markets.find(m=>m.state==='Maharashtra'&&m.market==='Nasik'&&m.variety==='Other');
    const pin = catalog.logistics.market_pins.find(p=>p.market==='Nasik');
    changeMany({...m, farm_name:'SPIT Mumbai (sample pickup)', farm_latitude:f.latitude, farm_longitude:f.longitude,
                destination_latitude:pin.latitude, destination_longitude:pin.longitude, quantity:form.quantity || '500'});
  }
  function options(key) {
    const keys = ['state','district','market','variety'];
    const before = keys.slice(0,keys.indexOf(key));
    return [...new Set(catalog.markets.filter(m => before.every(k => m[k] === form[k])).map(m => m[key]))].sort();
  }
  function field(key, label, choices, extra={}) {
    return <div className="field"><label htmlFor={key}>{label}</label>{choices ? <select id={key} value={form[key] || ''} onChange={e=>change(key,e.target.value)}>{choices.map(v=><option key={v.value??v} value={v.value??v}>{v.label??v}</option>)}</select> : <input id={key} value={form[key]} onChange={e=>change(key,e.target.value)} {...extra}/>}</div>;
  }
  async function submit(e) {
    e.preventDefault(); if(lock.current) return;
    lock.current=true; setBusy(true); setError(''); setResult(null);
    try {
      const response = await request('/listing-estimate', {body:form});
      setResult(response);
      setTimeout(()=>document.getElementById('recommendation')?.focus(),100);
    } catch(e) {setError(e.message);} finally {lock.current=false; setBusy(false);}
  }
  return <><a className="skip-link" href={tab==='calculator'?'#calculator':tab==='account'?'#account-panel':'#buyer-panel'}>{tab==='calculator'?'Skip to calculator':tab==='account'?'Skip to account workspace':'Skip to harvest and buyers'}</a>
    <header className="header"><a href="#" className="brand">Agro<span>Link</span></a><nav><a href="#how-it-works" onClick={()=>setTab('calculator')}>How it works</a><a className="nav-cta" href="#calculator" onClick={()=>setTab('calculator')}>Price my harvest ↗</a></nav></header>
    <div className="farmer-tabs" role="tablist" aria-label="Farmer workspace">{[['calculator','Price calculator'],['buyers','My harvest & buyers'],['account','Accounts & marketplace']].map(([id,label],index,items)=><button key={id} id={`${id}-tab`} role="tab" aria-selected={tab===id} aria-controls={id==='buyers'?'buyer-panel':`${id}-panel`} tabIndex={tab===id?0:-1} disabled={busy} onClick={()=>setTab(id)} onKeyDown={e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();const next=items[(index+(e.key==='ArrowRight'?1:items.length-1))%items.length][0];setTab(next);document.getElementById(`${next}-tab`)?.focus();}}}>{label}</button>)}</div>
    <main>{tab==='calculator'?<div id="calculator-panel" role="tabpanel" aria-labelledby="calculator-tab"><section className="hero"><div className="hero-copy"><span className="eyebrow">A FAIRER STARTING POINT FOR FARMERS</span><h1>A price for<br/>your <em>harvest.</em></h1><p className="hero-description">Tell us what you are selling, where it grew and where you want to sell. We will find a route and estimate your return.</p><p className="scope-note">Project demo: historical tomato data is loaded automatically. Estimates are labelled with the period the data supports.</p><a className="button" href="#calculator">Price my harvest ↗</a></div><div className="harvest-art" aria-hidden="true"><div className="art-label">ROOTED IN DATA.<br/>GROWN FOR YOU.</div><div className="sun"/><div className="furrow f1"/><div className="furrow f2"/><div className="furrow f3"/><div className="art-bottom">From the mandi.<br/><strong>To your next harvest.</strong></div></div></section>
    <section id="how-it-works" className="steps-section"><h2>Your harvest. Three simple steps.</h2><div className="steps">{[['01','Tell us about your crop','Add your harvest, pickup point and selling market.'],['02','Get a price estimate','Road routing estimates transport; market history feeds the forecast.'],['03','See what you could receive','Review the market estimate and your return after transport.']].map(([n,h,p])=><article key={n}><span className="step-number">{n}</span><h3>{h}</h3><p>{p}</p></article>)}</div></section>
    <section id="calculator" className="calculator-section"><div className="calculator-intro"><span className="eyebrow">PRICE MY HARVEST</span><h2>What are you<br/>selling today?</h2><p>Tomato market history is selected for you. Your market starts at Nasik, with a saved destination pin. Change it to match where you sell.</p><div className="factor-list"><h3>What goes into the estimate?</h3><p>Historical prices and arrival volumes, automatically evaluated VAR and baseline models, and route-based transport costs.</p><p>Supply/demand is managed by the engine when evidence is available. Quality premiums are not calibrated.</p></div></div>
    <div className="calculator-body">{!catalog ? <div role="status"><p>{error || 'Loading tomato markets…'}</p>{error&&<button onClick={()=>setRetry(r=>r+1)}>Retry connection</button>}</div> : <form onSubmit={submit} aria-busy={busy}>
      <p className="small muted">Listing date: {catalog.listing_date} · Tomato dataset selected automatically</p>
      <fieldset disabled={busy}><legend><span>01</span> Your harvest</legend><div className="fields">{field('crop','Crop',catalog.crops)}{field('quantity','Quantity available',null,{type:'number',min:'0.01',step:'any',required:true,placeholder:'e.g. 500'})}{field('unit','Quantity unit',['kg','quintal'])}{field('harvest_date','Harvest date',null,{type:'date',max:catalog.listing_date,required:true})}{field('selling_date','Expected selling date',null,{type:'date',min:catalog.listing_date,required:true})}{field('produce_condition','Crop condition',catalog.shelf_life_policy.conditions.map(c=>({value:c.id,label:c.label})))}</div></fieldset>
      <fieldset disabled={busy}><details><summary>Optional harvest and pickup times</summary><div className="fields">{field('harvest_time','Harvest time (IST, optional)',null,{type:'time'})}{field('pickup_at','Planned pickup (IST, optional)',null,{type:'datetime-local'})}</div><p className="small muted">Without a harvest time we count from midnight. Without a pickup time we use immediate pickup today, or the start of a future selling day.</p></details></fieldset>
      <LocationFields form={form} change={changeMany} field={field} busy={busy} useSample={useSample} notice={catalog.logistics.notice}/>
      <fieldset disabled={busy}><legend><span>03</span> Where will you sell?</legend><div className="fields">{['state','district','market','variety'].map(k=><React.Fragment key={k}>{field(k,k==='market'?'Mandi market':k[0].toUpperCase()+k.slice(1),options(k))}</React.Fragment>)}</div><p className="small muted">The selected market supplies the price forecast. Confirm that the destination coordinates below are the entrance where you will sell. Saved pins are available for Nasik; enter coordinates for other markets.</p><div className="fields">{field('destination_latitude','Selling destination latitude',null,{type:'number',min:-90,max:90,step:'any',required:true})}{field('destination_longitude','Selling destination longitude',null,{type:'number',min:-180,max:180,step:'any',required:true})}</div></fieldset>
      <fieldset disabled={busy}><legend><span>04</span> Transport calculated for you</legend><p className="small muted">We find a road route and estimate fuel and handling costs. The default small goods vehicle carries up to {form.vehicle_capacity_kg} kg per trip. Larger loads automatically use additional trips.</p>
      <details><summary>Adjust vehicle and cost assumptions</summary><p className="small muted">{catalog.logistics.fuel_notice} Loading, unloading and tolls are per trip. An empty-return factor of 1 budgets the full return distance; 0 budgets outbound travel only.</p><div className="fields">{field('vehicle_capacity_kg','Vehicle capacity (kg)',null,{type:'number',min:1,step:'any',required:true})}{field('fuel_efficiency_km_per_litre','Vehicle mileage (km/l)',null,{type:'number',min:0.1,step:'any',required:true})}{field('fuel_price_inr_per_litre','Fuel price (₹/litre)',null,{type:'number',min:0,step:'any',required:true})}{field('empty_return_factor','Empty-return factor (0–1)',null,{type:'number',min:0,max:1,step:0.1,required:true})}{field('loading_inr','Loading per trip (₹)',null,{type:'number',min:0,step:'any',required:true})}{field('unloading_inr','Unloading per trip (₹)',null,{type:'number',min:0,step:'any',required:true})}{field('tolls_inr','Tolls per trip, including return (₹)',null,{type:'number',min:0,step:'any',required:true})}</div></details></fieldset>
      <p className="notice">Demo data ends in 2024. The result shows a historical model estimate, not a verified price for today.</p>
      {error&&<div className="error" role="alert">{error}</div>}<button className="button submit" type="submit" disabled={busy}>{busy?'Finding your route and calculating returns…':'Calculate route & return ↗'}</button><p className="small muted">DSR is handled automatically from backend supply/demand evidence. Without verified demand it remains neutral. The first route and forecast can take a minute. Your entries stay here if calculation fails.</p>
    </form>}</div></section>
    {result&&<ListingResult result={result}/>}</div>:<Suspense fallback={<p>Loading your harvest workspace…</p>}>{tab==='account'?<AccountWorkspace catalog={catalog} calculatorHarvest={form}/>:<BuyerMarketplace catalog={catalog} form={form} change={changeMany} field={field} useSample={useSample} busy={busy} onBusy={setBusy}/>}</Suspense>}</main><footer><a href="#" className="brand">AgroLink</a><p>Better information. More informed decisions.</p></footer></>;
}
function ListingResult({result:r}) {
  const b = r.breakdown, l = r.listing, e = r.economics, balance = r.market_balance;
  return <section id="recommendation" className="result" tabIndex="-1" aria-labelledby="result-title"><span className="eyebrow">{l.demo?'HISTORICAL DEMO ESTIMATE':'YOUR LISTING ESTIMATE'}</span><h2 id="result-title">Your harvest, priced transparently.</h2><p>{r.crop} · {r.market}, {r.state} · {r.quantity_kg} kg · Listing {l.date}</p><p className="notice" role="status">{l.notice}</p>
    <div className="price-banner"><span>Estimated return after transport · INR/kg</span><div className="price-range">{money(e.net_inr_per_kg)} <span>/ kg</span></div><p>Estimated batch return: <strong>{money(e.net_revenue_inr)}</strong></p><p>Market reference before adjustments: <strong>{money(b.base)} / kg</strong></p><small>Requested sale: {l.selling_date} · Model target: {l.target_month} · Latest observation: {r.context.latest_observation}</small></div>
    {e.net_revenue_inr<0&&<p className="notice" role="alert">Transport costs exceed estimated sale proceeds. This journey produces an estimated loss before production costs.</p>}
    <ShelfLifeStatus assessment={r.shelf_life}/>
    <RouteSummary transport={r.transport}/>
    <h3>How we calculated your return</h3><dl className="breakdown"><div><dt>Forecast market reference</dt><dd>{money(b.base)} / kg</dd></div><div><dt>Engine supply / demand adjustment</dt><dd>× {b.demand_supply_multiplier.toFixed(3)}</dd></div><div><dt>Estimated sale proceeds</dt><dd>{money(e.gross_revenue_inr)}</dd></div><div><dt>Calculated transport cost</dt><dd>− {money(e.transport_cost_inr)}</dd></div><div className="total"><dt>Estimated net batch return</dt><dd>{money(e.net_revenue_inr)}</dd></div></dl><p className="small muted">Return = forecast × engine adjustment × quantity − transport. This is the amount left after transport; production costs are not included. Net return can be negative.</p>
    <div className="balance-status"><h3>Supply and demand, handled automatically</h3><p><strong>{balance.status==='available'?'Matched evidence available':'No demand adjustment applied'}</strong> · {balance.reason}</p>{balance.status==='available'&&<p>Supply {balance.supply_kg.toLocaleString('en-IN')} kg / demand {balance.demand_kg.toLocaleString('en-IN')} kg = {balance.ratio.toFixed(3)}. Source: {balance.source}. Period: {balance.period}.</p>}</div>
    <details className="quality-panel"><summary>Forecast evidence and limitations</summary><p>Selected model: {r.forecast.name}{r.forecast.lag ? ` · lag ${r.forecast.lag}` : ''}. VAR candidates use monthly prices and arrivals; automatic backtesting may select a simpler baseline.</p><p>Training through {r.forecast.origin} · Target {l.target_month} · Final holdout MAE {money(r.forecast.metrics.MAE/100)} / kg; RMSE {money(r.forecast.metrics.RMSE/100)} / kg.</p><p>Quality and location factors: × 1.00. Crop arrivals are supply observations; they are not treated as measured demand.</p><ul>{[...new Set(r.warnings)].map(w=><li key={w}>{w}</li>)}</ul><Suspense fallback={<p>Loading market chart...</p>}><MarketPriceChart context={r.context} forecast={r.forecast}/></Suspense></details><p className="small muted">This calculator does not publish or save a crop listing. Estimates do not guarantee a sale price.</p></section>;
}
createRoot(document.getElementById('root')).render(<App/>);
