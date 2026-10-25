import React, { useEffect, useState } from 'react';
import { request } from '../api/client';
import FarmerDashboard from './FarmerDashboard';
import BuyerDashboard from './BuyerDashboard';
import OrderWorkspace from './OrderWorkspace';
import { fields } from './WorkspaceFields';

export default function AccountWorkspace({catalog,calculatorHarvest}) {
  const [user,setUser]=useState(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[settings,setSettings]=useState(null),[revision,setRevision]=useState(0);
  useEffect(()=>{request('/auth/me').then(r=>setUser(r.user)).catch(e=>setError(e.message)).finally(()=>setLoading(false));},[]);
  useEffect(()=>{if(user)request('/app/config').then(setSettings).catch(e=>setError(e.message));else setSettings(null);},[user]);
  async function logout(){try{await request('/auth/logout',{body:{}});setUser(null);setError('');}catch(e){setError(e.message);}}
  if(loading)return <p role="status">Checking your account…</p>;
  return <section className="account-workspace" id="account-panel" role="tabpanel" aria-labelledby="account-tab">
    <div className="workspace-top"><div><span className="eyebrow">AGROLINK MARKETPLACE</span><h1>{user?`${user.role==='farmer'?'Farmer':'Buyer'} workspace`:'Your harvest. Your account.'}</h1><p>{user?`Signed in as ${user.name} · ${user.email}`:'Create an account to manage real harvest listings and buyer offers.'}</p></div>{user&&<button className="secondary-button" onClick={logout}>Sign out</button>}</div>
    {error&&<p className="error" role="alert">{error}</p>}
    {!user?<AuthForm onAuth={setUser}/>:<><p className="notice">Listings, quotes and orders are saved on this server. Accounts and grades are self-reported, not independently verified. Enquiry previews are non-binding. Explicit proposals become binding in the application when the buyer accepts and stock is reserved. No payments are processed.</p>{user.role==='farmer'?<FarmerDashboard catalog={settings||catalog} calculatorHarvest={calculatorHarvest} onExpired={()=>setUser(null)} revision={revision} onOrder={()=>setRevision(r=>r+1)}/>:<BuyerDashboard onExpired={()=>setUser(null)} revision={revision}/>}<OrderWorkspace key={user.id} user={user} revision={revision} onChanged={()=>setRevision(r=>r+1)} onExpired={()=>setUser(null)}/></>}
  </section>;
}

function AuthForm({onAuth}) {
  const [mode,setMode]=useState('login'),[form,setForm]=useState({name:'',email:'',password:'',role:'farmer'}),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const field=fields(form,setForm);
  async function submit(e){e.preventDefault();setBusy(true);setError('');try{const r=await request(`/auth/${mode}`,{body:form});onAuth(r.user);setForm(f=>({...f,password:''}));}catch(e){setError(e.message);}finally{setBusy(false);}}
  return <div className="auth-card"><div className="location-actions"><button className="secondary-button" type="button" onClick={()=>{setMode('login');setError('');}}>Sign in</button><button className="secondary-button" type="button" onClick={()=>{setMode('register');setError('');}}>Create account</button></div><h2>{mode==='register'?'Create your account':'Welcome back'}</h2><form onSubmit={submit}><fieldset disabled={busy}><div className="fields">{mode==='register'&&field('name','Your name / business name',null,{required:true,minLength:2,maxLength:100,autoComplete:'name'})}{field('email','Email address',null,{type:'email',required:true,autoComplete:'email'})}{field('password','Password',null,{type:'password',minLength:12,maxLength:128,required:true,autoComplete:mode==='login'?'current-password':'new-password'})}{mode==='register'&&field('role','Account role',[{value:'farmer',label:'Farmer / seller'},{value:'buyer',label:'Buyer'}])}</div></fieldset>{mode==='register'&&<p className="small muted">Use at least 12 characters. Choose your role carefully; it cannot be changed through the application.</p>}{error&&<p className="error" role="alert">{error}</p>}<button className="button submit" disabled={busy}>{busy?'Please wait…':mode==='register'?'Create account & continue':'Sign in to marketplace'}</button></form></div>;
}
