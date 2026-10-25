import { test, expect } from '@playwright/test';

async function openBuyers(page) {
  await page.goto('/');
  await page.getByRole('tab',{name:'My harvest & buyers'}).click();
  await expect(page.getByRole('button',{name:'Try a near-expiry harvest'})).toBeVisible();
}

async function nearExpiry(page) {
  await openBuyers(page);
  await page.getByRole('button',{name:'Try a near-expiry harvest'}).click();
  await page.getByRole('button',{name:'Save harvest & find buyers'}).click();
  await expect(page.getByTestId('buyer-demo-nasik-yard')).toBeVisible();
}

test('near-expiry lot warns for a nearer buyer and blocks the distant buyer',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await nearExpiry(page);
  const near=page.getByTestId('buyer-demo-nasik-yard'), far=page.getByTestId('buyer-demo-sambhajinagar');
  await expect(near.getByText('Limited delivery window',{exact:true})).toBeVisible();
  await expect(far.getByRole('button',{name:'Selling unavailable'})).toBeDisabled();
  await expect(near.getByRole('button',{name:'Prepare sale draft'})).toBeDisabled();
  await near.getByRole('checkbox').check();
  await expect(near.getByRole('button',{name:'Prepare sale draft'})).toBeEnabled();
  await near.getByRole('button',{name:'Prepare sale draft'}).click();
  await expect(page.getByRole('heading',{name:'Sale draft prepared'})).toBeVisible();
  await expect(page.getByText(/No order was placed or sent/)).toBeVisible();
  const values=await page.evaluate(()=>JSON.parse(localStorage.getItem('agrolink.harvest-draft.v1')).values);
  expect(values.quantity).toBe('500');
  expect(errors).toEqual([]);
  await page.locator('#buyer-panel').screenshot({path:'test-results/buyers-desktop.png'});
});

test('direct API requests cannot select an ineligible buyer',async({page})=>{
  await nearExpiry(page);
  const values=await page.evaluate(()=>JSON.parse(localStorage.getItem('agrolink.harvest-draft.v1')).values);
  const response=await page.request.post('/api/buyer-selection',{data:{...values,buyer_id:'demo-sambhajinagar',acknowledge_warning:true,can_select:true,shelf_life_hours:10000}});
  expect(response.status()).toBe(422);
  expect((await response.json()).message).toContain('Selling unavailable');
});

test('editing a harvest invalidates suggestions and saved drafts can be restored',async({page})=>{
  await nearExpiry(page);
  await page.getByLabel('Quantity available').fill('750');
  await expect(page.getByTestId('buyer-demo-nasik-yard')).toHaveCount(0);
  await page.getByRole('tab',{name:'Price calculator'}).click();
  await page.getByRole('tab',{name:'My harvest & buyers'}).click();
  await page.getByRole('button',{name:'Restore saved harvest'}).click();
  await expect(page.getByLabel('Quantity available')).toHaveValue('500');
  await page.getByRole('button',{name:'Delete saved draft'}).click();
  const saved=await page.evaluate(()=>localStorage.getItem('agrolink.harvest-draft.v1'));
  expect(saved).toBeNull();
});

test('stale checks require refresh before selecting a buyer',async({page})=>{
  await page.clock.install();
  await nearExpiry(page);
  await page.clock.fastForward(75000);
  await expect(page.getByText(/Delivery checks are over a minute old/)).toBeVisible();
  await expect(page.getByTestId('buyer-demo-nasik-yard').getByRole('button',{name:'Prepare sale draft'})).toBeDisabled();
});

test('damaged crop disables every buyer and mobile layout fits',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await openBuyers(page);
  await page.getByRole('button',{name:'Try a near-expiry harvest'}).click();
  await page.getByLabel('Crop condition').selectOption('damaged');
  await page.getByRole('button',{name:'Save harvest & find buyers'}).click();
  await expect(page.getByRole('button',{name:'Selling unavailable'})).toHaveCount(3);
  for(const button of await page.getByRole('button',{name:'Selling unavailable'}).all())await expect(button).toBeDisabled();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  await page.getByTestId('buyer-demo-nasik-yard').screenshot({path:'test-results/buyer-mobile.png'});
});
