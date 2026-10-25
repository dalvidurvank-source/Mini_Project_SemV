import React from 'react';
import { apiUrl } from '../api/client';

export const localTime=(offset=0)=>new Date(Date.now()+330*60000+offset).toISOString().slice(0,16);
export const toInstant=s=>s.length===16?`${s}:00+05:30`:s;
export const timeField=s=>new Date(Date.parse(s)+330*60000).toISOString().slice(0,16);
export const fields=(form,setForm)=>(key,label,choices,extra={})=><div className="field"><label htmlFor={`live-${key}`}>{label}</label>{choices?<select id={`live-${key}`} value={form[key]??''} onChange={e=>setForm(f=>({...f,[key]:e.target.value}))}>{choices.map(c=><option key={c.value??c} value={c.value??c}>{c.label??c}</option>)}</select>:<input id={`live-${key}`} value={form[key]??''} onChange={e=>setForm(f=>({...f,[key]:e.target.value}))} {...extra}/>}</div>;

export function PhotoStrip({photos,onRemove}) {
  return <div className="photo-strip">{photos.map(p=><div key={p.id}><img src={apiUrl(`/app/photos/${p.id}`)} alt="Farmer-uploaded harvest"/>{onRemove&&<button type="button" className="secondary-button" onClick={()=>onRemove(p.id)}>Remove photo</button>}</div>)}</div>;
}
