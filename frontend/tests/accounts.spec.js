import { test, expect } from '@playwright/test';

const password='AgroLink!Account2026';
const email=prefix=>`${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}@example.test`;

async function open(page){await page.goto('/');await page.getByRole('tab',{name:'Accounts & marketplace'}).click();await expect(page.getByRole('button',{name:'Create account',exact:true})).toBeVisible();}
async function register(page,role,address){await open(page);await page.getByRole('button',{name:'Create account',exact:true}).click();await page.getByLabel('Your name / business name').fill(role==='farmer'?'Pilot Farmer':'Pilot Buyer');await page.getByLabel('Email address').fill(address);await page.getByLabel('Password',{exact:true}).fill(password);await page.getByLabel('Account role').selectOption(role);await page.getByRole('button',{name:'Create account & continue'}).click();await expect(page.getByRole('heading',{name:role==='farmer'?'Farmer workspace':'Buyer workspace',exact:true})).toBeVisible();}

test('mutual order agreement reserves quantity and persists delivery outcomes',async({page,browser})=>{
  await register(page,'farmer',email('order-farmer'));
  const buyerContext=await browser.newContext();const buyer=await buyerContext.newPage();
  async function post(p,path,data){const me=await(await p.request.get('/api/auth/me')).json();const r=await p.request.post(path,{headers:{'X-Agrolink-Client':'1','X-CSRF-Token':me.csrf},data});expect(r.ok()).toBeTruthy();return r.json();}
  try{
    await register(buyer,'buyer',email('order-buyer'));
    const day=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata'}).format(new Date());
    const listing=await post(page,'/api/app/listings',{title:'Order lifecycle tomatoes',crop:'Tomato',quantity:500,unit:'kg',variety:'Other',grade:'A',harvest_date:day,selling_date:day,produce_condition:'firm_ripe',farm_name:'Pilot pickup',farm_latitude:19.1236,farm_longitude:72.8361,status:'published',allow_partial_sales:true});
    await post(buyer,'/api/app/offers',{title:'Order lifecycle quote',listing_id:listing.id,crop:'Tomato',price_inr_per_kg:'25.50',max_quantity_kg:300,min_quantity_kg:100,accepted_grade:'A',accepted_variety:'Any',destination_name:'Nashik yard',destination_latitude:20.015063587300105,destination_longitude:73.79766078270252,valid_until:new Date(Date.now()+4*3600000).toISOString(),delivery_deadline:new Date(Date.now()+12*3600000).toISOString(),partial_sales_supported:true,selling_charges:[{label:'Sorting',type:'fixed',value:50}]});
    await page.getByRole('button',{name:'Refresh listings',exact:true}).click();
    const lot=page.getByTestId(`live-listing-${listing.id}`);
    await lot.getByRole('button',{name:'Compare live buyer offers'}).click();
    const comparison=page.locator('.live-comparison');
    const warning=comparison.getByLabel('I understand the limited delivery window.');
    if(await warning.count())await warning.check();
    await comparison.getByRole('button',{name:'Prepare non-binding enquiry'}).click();
    await comparison.getByLabel('I agree to propose these saved terms to this buyer. Acceptance will reserve this quantity.').check();
    await comparison.getByRole('button',{name:'Send order proposal'}).click();
    await expect(page.getByText('Order proposal saved. Awaiting buyer acceptance; no stock is reserved yet.')).toBeVisible();
    const order=(await(await page.request.get('/api/app/orders')).json()).orders[0];
    const farmerOrder=page.getByTestId(`order-${order.id}`),buyerOrder=buyer.getByTestId(`order-${order.id}`);
    await expect(lot.getByText(/Available: 500/)).toBeVisible();
    await buyer.getByRole('button',{name:'Refresh orders',exact:true}).click();
    await buyerOrder.getByLabel(/I agree to the saved quantity/).check();
    await buyerOrder.getByRole('button',{name:'Accept & reserve quantity',exact:true}).click();
    await expect(buyerOrder.locator('.demo-tag')).toContainText('accepted');
    await expect(buyer.getByText('Remaining shared purchase budget: 0 kg.')).toBeVisible();
    await page.getByRole('button',{name:'Refresh orders',exact:true}).click();
    await page.getByRole('button',{name:'Refresh listings',exact:true}).click();
    await expect(lot.getByText(/Available: 200/)).toBeVisible();
    await farmerOrder.getByRole('button',{name:'Mark ready for pickup'}).click();
    await buyer.getByRole('button',{name:'Refresh orders',exact:true}).click();
    await buyerOrder.getByLabel(/I confirm collection/).check();
    await buyerOrder.getByRole('button',{name:'Confirm collection',exact:true}).click();
    await buyerOrder.getByLabel('Actual accepted weight (kg)').fill('290');
    await buyerOrder.getByLabel('Actual accepted grade').selectOption('B');
    await buyerOrder.getByLabel('Delivery notes / rejection reasons').fill('10 kg rejected: damaged in transit');
    await buyerOrder.getByRole('button',{name:'Record delivery',exact:true}).click();
    await expect(buyerOrder.locator('.demo-tag')).toContainText('delivered');
    await page.getByRole('button',{name:'Refresh orders',exact:true}).click();
    await farmerOrder.getByLabel('I acknowledge the recorded delivery weight and grade.').check();
    await farmerOrder.getByRole('button',{name:'Complete order',exact:true}).click();
    await expect(farmerOrder.locator('.demo-tag')).toContainText('completed');
    await page.reload();await page.getByRole('tab',{name:'Accounts & marketplace'}).click();
    await expect(farmerOrder.getByText(/Buyer recorded 290 kg accepted, grade B/)).toBeVisible();
    await expect(farmerOrder.getByText(/300 kg/).first()).toBeVisible();
    await page.setViewportSize({width:390,height:844});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
    const persisted=await(await page.request.get('/api/app/orders/'+order.id)).json();
    expect(persisted.events.map(e=>e.status)).toEqual(['proposed','accepted','ready','collected','delivered','completed']);
    expect(persisted.terms.quantity_kg).toBe('300');expect(persisted.actuals.accepted_weight_kg).toBe('290');
  }finally{await buyerContext.close();}
});

test('farmer listings persist across reload and login, with photo and live buyer quote',async({page,browser})=>{
  const farmerEmail=email('farmer');await register(page,'farmer',farmerEmail);
  const title=`Pilot tomato harvest ${Date.now()}`;
  await page.getByLabel('Listing title').fill(title);
  await page.getByLabel('Harvest quantity',{exact:true}).fill('500');
  await page.getByLabel('Farm / pickup name').fill('Pilot test pickup');
  await page.getByLabel('Pickup latitude').fill('19.1236');await page.getByLabel('Pickup longitude').fill('72.8361');
  await page.getByLabel('Listing visibility').selectOption('published');
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64');
  await page.getByLabel('Harvest photos (up to 3, 2 MB each)').setInputFiles({name:'harvest.png',mimeType:'image/png',buffer:png});
  await page.getByRole('button',{name:'Save harvest to account'}).click();
  await expect(page.getByText('Harvest saved to your account.',{exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
  await page.reload();await page.getByRole('tab',{name:'Accounts & marketplace'}).click();
  await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
  const listingId=await page.getByRole('heading',{name:title,exact:true}).locator('..').getAttribute('data-testid');
  const buyerContext=await browser.newContext();const buyer=await buyerContext.newPage();
  try {
    await register(buyer,'buyer',email('buyer'));
    await expect(buyer.getByRole('heading',{name:title,exact:true})).toBeVisible();
    await buyer.getByRole('heading',{name:title,exact:true}).locator('..').getByRole('button',{name:'Make offer for this harvest'}).click();
    await buyer.getByLabel('Offered price (INR/kg)').fill('25');await buyer.getByLabel('Maximum purchase quantity (kg)').fill('1000');
    await buyer.getByLabel('Delivery location name').fill('Nashik pilot test yard');await buyer.getByLabel('Delivery latitude').fill('20.015063587300105');await buyer.getByLabel('Delivery longitude').fill('73.79766078270252');
    await buyer.getByRole('button',{name:'Save buyer offer'}).click();
    await expect(buyer.getByText('Buyer offer saved. Farmers with matching harvests can compare its terms.',{exact:true})).toBeVisible();
    const card=page.getByTestId(listingId);
    await card.getByRole('button',{name:'Compare live buyer offers'}).click();
    const comparison=page.locator('.live-comparison');
    await expect(comparison.getByText('₹25.00 / kg',{exact:true})).toBeVisible();
    await expect(comparison.getByText('Actual buyer offer',{exact:true})).toBeVisible();
    await comparison.getByRole('button',{name:'Prepare non-binding enquiry'}).click();
    await expect(page.getByText(/Enquiry prepared, not an order/)).toBeVisible();
    await comparison.screenshot({path:'test-results/live-comparison.png'});
    await buyer.getByRole('button',{name:'Withdraw offer'}).click();
    await card.getByRole('button',{name:'Compare live buyer offers'}).click();
    await expect(comparison.getByText(/No active buyer quotes match/)).toBeVisible();
  } finally {await buyerContext.close();}
  await page.getByRole('button',{name:'Sign out',exact:true}).click();
  await page.getByLabel('Email address').fill(farmerEmail);await page.getByLabel('Password',{exact:true}).fill(password);await page.getByRole('button',{name:'Sign in to marketplace'}).click();
  await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
});

test('role UI and direct API enforce farmer/buyer permissions and CSRF',async({page})=>{
  await register(page,'buyer',email('rbac'));
  await expect(page.getByRole('button',{name:'Save harvest to account'})).toHaveCount(0);
  const me=await (await page.request.get('/api/auth/me')).json();
  const forbidden=await page.request.post('/api/app/listings',{headers:{'X-Agrolink-Client':'1','X-CSRF-Token':me.csrf},data:{title:'forged',role:'farmer'}});
  expect(forbidden.status()).toBe(403);
  const csrf=await page.request.post('/api/app/offers',{headers:{'X-Agrolink-Client':'1'},data:{}});
  expect(csrf.status()).toBe(403);
  expect((await (await page.request.get('/api/auth/me')).json()).user.role).toBe('buyer');
  await page.getByRole('button',{name:'Sign out',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Welcome back',exact:true})).toBeVisible();
  expect((await page.request.get('/api/app/offers')).status()).toBe(401);
});

test('multiple farmer drafts and archived lots remain private on mobile',async({page})=>{
  await page.setViewportSize({width:390,height:844});await register(page,'farmer',email('mobile'));
  for(const title of ['Private lot one','Private lot two']) {
    await page.getByRole('button',{name:'New harvest',exact:true}).click();
    await page.getByLabel('Listing title').fill(title);await page.getByLabel('Harvest quantity',{exact:true}).fill('100');
    await page.getByLabel('Pickup latitude').fill('19.1236');await page.getByLabel('Pickup longitude').fill('72.8361');
    await page.getByRole('button',{name:'Save harvest to account'}).click();await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
  }
  const card=page.getByRole('heading',{name:'Private lot one',exact:true}).locator('..');
  await card.getByRole('button',{name:'Archive harvest'}).click();
  await expect(card.getByText(/archived/)).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  await page.locator('#account-panel').screenshot({path:'test-results/account-mobile.png'});
});
