import { test, expect } from '@playwright/test';

test.beforeEach(async ({page}) => {
  await page.goto('/');
  await expect(page.getByRole('button',{name:'Try the Mumbai → Nashik sample'})).toBeVisible();
});

test('sample locations run routing, transport and the real market forecast', async ({page}) => {
  test.setTimeout(240000);
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await expect(page.getByLabel('Regional supply')).toHaveCount(0);
  await expect(page.getByLabel('Regional demand')).toHaveCount(0);
  await expect(page.getByLabel('Data source')).toHaveCount(0);
  await page.getByRole('button',{name:'Try the Mumbai → Nashik sample'}).click();
  await expect(page.getByLabel('Quantity available')).toHaveValue('500');
  await page.getByRole('button',{name:'Calculate route & return'}).click();
  await expect(page.getByRole('heading',{name:'Your harvest, priced transparently.'})).toBeVisible({timeout:185000});
  await expect(page.getByText('HISTORICAL DEMO ESTIMATE',{exact:true})).toBeVisible();
  await expect(page.locator('.route-stats').getByText('172.2 km',{exact:true})).toBeVisible();
  await expect(page.getByText('No demand adjustment applied',{exact:true})).toBeVisible();
  await expect(page.getByText('Estimated net batch return',{exact:true})).toBeVisible();
  await page.getByText('Route and transport breakdown',{exact:true}).click();
  await expect(page.getByText('Return-distance allowance',{exact:true})).toBeVisible();
  await page.locator('#recommendation').screenshot({path:'test-results/listing-desktop.png'});
  expect(errors).toEqual([]);
});

test('failed requests preserve harvest, coordinates and quantity', async ({page}) => {
  await page.getByRole('button',{name:'Try the Mumbai → Nashik sample'}).click();
  await page.getByLabel('Quantity available').fill('750');
  await page.route('**/api/listing-estimate',route=>route.fulfill({status:422,contentType:'application/json',body:JSON.stringify({message:'Road routing temporarily unavailable'})}));
  await page.getByRole('button',{name:'Calculate route & return'}).click();
  await expect(page.getByRole('alert')).toContainText('Road routing temporarily unavailable');
  await expect(page.getByLabel('Quantity available')).toHaveValue('750');
  await expect(page.getByLabel('Pickup latitude')).toHaveValue('19.1236');
  await expect(page.getByRole('button',{name:'Calculate route & return'})).toBeEnabled();
});

test('market changes clear destination pins and mobile has no horizontal overflow', async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'Try the Mumbai → Nashik sample'}).click();
  await page.getByLabel('State',{exact:true}).selectOption('Karnataka');
  await expect(page.getByLabel('Selling destination latitude')).toHaveValue('');
  await expect(page.getByLabel('Selling destination longitude')).toHaveValue('');
  const overflow = await page.evaluate(()=>document.documentElement.scrollWidth > innerWidth);
  expect(overflow).toBe(false);
  await page.locator('#calculator').screenshot({path:'test-results/listing-mobile.png'});
});

test('GPS can populate the farm pickup point', async ({page,context}) => {
  await context.grantPermissions(['geolocation']);
  await context.setGeolocation({latitude:19.1236,longitude:72.8361});
  await page.getByRole('button',{name:'Use my current location'}).click();
  await expect(page.getByLabel('Pickup latitude')).toHaveValue('19.123600');
  await expect(page.getByLabel('Pickup longitude')).toHaveValue('72.836100');
  await expect(page.getByLabel('Farm / pickup name')).toHaveValue('My farm (GPS)');
});
