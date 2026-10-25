import { test, expect } from '@playwright/test';

async function prepare(page,quantity='500',partial=false) {
  await page.goto('/');
  await page.getByRole('tab',{name:'My harvest & buyers'}).click();
  await page.getByRole('button',{name:'Try the Mumbai → Nashik sample'}).click();
  await page.getByLabel('Quantity available').fill(quantity);
  if(partial)await page.getByRole('checkbox',{name:/Allow partial sales/}).check();
  await page.getByRole('button',{name:'Save harvest & find buyers'}).click();
  await expect(page.getByTestId('buyer-demo-pimpalgaon')).toBeVisible();
}

test('farther demo offer ranks higher by net return and missing price stays unranked',async({page})=>{
  await prepare(page);
  await expect(page.locator('.buyer-card').first()).toHaveAttribute('data-testid','buyer-demo-pimpalgaon');
  const best=page.getByTestId('buyer-demo-pimpalgaon');
  await expect(best.locator('.rank-badge')).toContainText('Best estimated return');
  await expect(best.getByText('Illustrative demo offer',{exact:true})).toBeVisible();
  await expect(best.getByText('₹23.00 / kg',{exact:true})).toBeVisible();
  await best.getByText('Financial breakdown and assumptions',{exact:true}).click();
  await expect(best.getByText('Demo market service fee',{exact:true})).toBeVisible();
  const unpriced=page.getByTestId('buyer-demo-sambhajinagar');
  await expect(unpriced.getByText('Not financially ranked',{exact:true})).toBeVisible();
  await expect(unpriced.getByText('Price not available',{exact:true})).toBeVisible();
  await page.locator('#buyer-panel').screenshot({path:'test-results/buyer-ranking-desktop.png'});
});

test('capacity excludes a full sale until partial sales are explicitly enabled',async({page})=>{
  await prepare(page,'1500');
  const partial=page.getByTestId('buyer-demo-pimpalgaon');
  await expect(partial.getByRole('button',{name:'Selling unavailable'})).toBeDisabled();
  await page.getByRole('checkbox',{name:/Allow partial sales/}).check();
  await page.getByRole('button',{name:'Save harvest & find buyers'}).click();
  await expect(partial.locator('.rank-badge')).toContainText('1000 kg partial sale');
  await expect(partial.getByText('500 kg',{exact:true})).toBeVisible();
  await expect(partial.getByText(/Partial sale only/)).toBeVisible();
  await expect(page.getByTestId('buyer-demo-nasik-yard').locator('.rank-badge')).toContainText('full harvest');
  await partial.getByRole('button',{name:'Prepare sale draft'}).click();
  await expect(page.getByText(/Remaining unsold: 500 kg/)).toBeVisible();
});

test('manipulated request totals are ignored and selection shows recalculated terms',async({page})=>{
  await prepare(page);
  const values=await page.evaluate(()=>JSON.parse(localStorage.getItem('agrolink.harvest-draft.v1')).values);
  const r=await page.request.post('/api/buyer-selection',{data:{...values,buyer_id:'demo-pimpalgaon',
    price_inr_per_kg:999999,transport_cost:0,net_return_inr:999999,rank:1,dsr_multiplier:9}});
  expect(r.status()).toBe(200);
  const selected=await r.json(), f=selected.buyer.financial;
  expect(selected.status).toBe('draft_only');
  expect(f.price_inr_per_kg).toBe(23);
  expect(f.transport_cost_inr).toBeGreaterThan(0);
  expect(f.net_return_inr).toBeCloseTo(f.gross_sale_inr-f.transport_cost_inr-f.other_selling_charges_inr,2);
  expect(f.dsr_applied).toBe(false);
});

test('unpriced buyers prepare enquiries without invented financial returns',async({page})=>{
  await prepare(page);
  await page.getByTestId('buyer-demo-sambhajinagar').getByRole('button',{name:'Prepare unpriced enquiry'}).click();
  await expect(page.getByRole('heading',{name:'Unpriced enquiry draft prepared'})).toBeVisible();
  await expect(page.getByText(/An unpriced draft is an enquiry/)).toBeVisible();
});

test('financial cards fit on mobile',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await prepare(page);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  await page.getByTestId('buyer-demo-pimpalgaon').screenshot({path:'test-results/buyer-ranking-mobile.png'});
});
