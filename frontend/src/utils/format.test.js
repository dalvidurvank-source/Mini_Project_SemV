import assert from 'node:assert/strict';
import test from 'node:test';
import { comparePrice, validate, money } from './format.js';
const form = {crop:'Tomato',state:'Karnataka',district:'Davangere',market:'Davangere',variety:'Tomato',quality:'Unspecified',quantity:'500',unit:'kg',transport_cost:'800',harvest_date:'2024-03-01',selling_date:'2024-03-05'};
test('valid crop and batch details pass',()=>assert.deepEqual(validate(form),{}));
test('invalid quantities, negative costs and reversed dates fail',()=>{const e=validate({...form,quantity:'0',transport_cost:'-1',selling_date:'2024-02-01'}); assert.ok(e.quantity);assert.ok(e.transport_cost);assert.ok(e.selling_date);});
test('invalid units and non-finite numbers fail',()=>{assert.ok(validate({...form,unit:'tonnes'}).unit);assert.ok(validate({...form,quantity:'Infinity'}).quantity)});
test('comparison includes both boundaries',()=>{const p={min_price:10,max_price:20};assert.equal(comparePrice('9',p),'Below the recommended range');assert.equal(comparePrice('10',p),'Within the recommended range');assert.equal(comparePrice('20',p),'Within the recommended range');assert.equal(comparePrice('21',p),'Above the recommended range');assert.equal(comparePrice('',p),'');assert.equal(comparePrice('-1',p),'')});
test('currency formatting retains paise',()=>assert.match(money(7.4305),/7\.43/));
test('comparison matches displayed rounded INR/kg boundaries',()=>assert.equal(comparePrice('5.68',{min_price:5.6839,max_price:6.1839}),'Within the recommended range'));
test('price-only future sessions do not require a selling calendar date',()=>assert.deepEqual(validate({...form,source:'price_only',mode:'future',target_date:'',market_id:'172',method:'auto',selling_date:''}),{}));
test('recorded mode needs only market identity and an actual date',()=>assert.deepEqual(validate({...form,source:'price_only',mode:'recorded',target_date:'2025-09-10',market_id:'172',method:'auto',selling_date:'',quantity:'',harvest_date:'',quality:''}),{}));
test('price-only requests reject missing mode target or market ID',()=>{const e=validate({...form,source:'price_only',mode:'historical',target_date:'',market_id:'',method:'auto',selling_date:''}); assert.ok(e.target_date);assert.ok(e.market_id)});
test('impossible calendar dates are rejected before submission',()=>assert.ok(validate({...form,harvest_date:'2024-02-31'}).harvest_date));
test('unsupported forecast selection cannot bypass validation',()=>assert.ok(validate({...form,source:'price_only',mode:'future',target_date:'',market_id:'172',method:'SES',selling_date:''}).method));

