import React, { useState } from 'react';

export default function LocationFields({form, change, field, busy, useSample, notice, sampleLabel='Try the Mumbai → Nashik sample'}) {
  const [gpsError, setGpsError] = useState(''), [locating, setLocating] = useState(false);
  function locate() {
    setGpsError('');
    if (!navigator.geolocation) {setGpsError('GPS is unavailable. Enter coordinates or use the sample route.'); return;}
    setLocating(true);
    navigator.geolocation.getCurrentPosition(p => {
      change({farm_latitude:p.coords.latitude.toFixed(6), farm_longitude:p.coords.longitude.toFixed(6), farm_name:'My farm (GPS)'});
      setLocating(false);
    }, () => {setGpsError('Could not read your location. Allow location access, enter coordinates, or use the sample route.'); setLocating(false);}, {enableHighAccuracy:true, timeout:15000, maximumAge:60000});
  }
  return <fieldset disabled={busy || locating}><legend><span>02</span> From your farm</legend>
    <p className="small muted">Enter the pickup point or use your current GPS location if you are at the farm.</p>
    <div className="location-actions"><button type="button" className="secondary-button" onClick={locate}>{locating?'Finding your location…':'Use my current location'}</button><button type="button" className="secondary-button" onClick={useSample}>{sampleLabel}</button></div>
    {gpsError&&<p role="alert" className="field-error">{gpsError}</p>}
    <div className="fields">{field('farm_name','Farm / pickup name',null,{placeholder:'Your village or farm',maxLength:120})}{field('farm_latitude','Pickup latitude',null,{type:'number',min:-90,max:90,step:'any',required:true,placeholder:'e.g. 19.1236'})}{field('farm_longitude','Pickup longitude',null,{type:'number',min:-180,max:180,step:'any',required:true,placeholder:'e.g. 72.8361'})}</div>
    {form.farm_name?.includes('SPIT')&&<p className="notice">Sample route: SPIT college in Mumbai stands in for the pickup point. This is not an actual farm.</p>}
    <p className="small muted">{notice} For custom locations, coordinates are sent to the routing provider when you calculate. GPS requires browser location permission.</p>
  </fieldset>;
}
