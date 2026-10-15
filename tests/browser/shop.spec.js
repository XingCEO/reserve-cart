const {test,expect}=require('@playwright/test');

test('reserve, confirm payment, prepare and collect through both interfaces',async({page,browser})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');await expect(page.getByRole('heading',{name:'The everyday cup',exact:true})).toBeVisible();
  await page.screenshot({path:'docs/storefront.png',fullPage:true});
  const cup=page.locator('.product-card').filter({has:page.getByRole('heading',{name:'The everyday cup',exact:true})});
  await cup.getByRole('button',{name:'Add to bag'}).click();
  await page.getByRole('button',{name:/Bag 1/}).click();await page.getByRole('button',{name:'Reserve these objects'}).click();
  await page.getByLabel('Your name',{exact:true}).fill('Ada Example');await page.getByLabel('Email',{exact:true}).fill('ada@example.org');
  await page.getByLabel('Pickup note (optional)').fill('Saturday afternoon');await page.getByRole('button',{name:'Confirm reservation'}).click();
  await expect(page.getByRole('heading',{name:'A little something, held for you.'})).toBeVisible();
  const orderUrl=page.url();expect(orderUrl).toContain('#order=');
  await page.screenshot({path:'docs/reservation.png'});
  const adminContext=await browser.newContext();const admin=await adminContext.newPage();await admin.goto('http://127.0.0.1:5056/admin');
  await admin.getByLabel('Password',{exact:true}).fill('browser-test-password');await admin.getByRole('button',{name:'Sign in'}).click();
  await expect(admin.getByRole('heading',{name:'Today at the desk.'})).toBeVisible();
  const row=admin.locator('tr').filter({hasText:'ada@example.org'});
  await row.getByRole('button',{name:'Review order'}).click();await admin.getByRole('button',{name:'Record payment',exact:true}).click();
  await admin.getByLabel('Payment / refund reference').fill('CASH-DEMO-001');await admin.getByRole('button',{name:'Confirm action'}).click();
  await expect(row.locator('.status')).toHaveText('paid');
  await row.getByRole('button',{name:'Review order'}).click();await admin.getByRole('button',{name:'Mark ready',exact:true}).click();await admin.getByRole('button',{name:'Confirm action'}).click();
  await expect(row.locator('.status')).toHaveText('ready');await admin.screenshot({path:'docs/order-desk.png',fullPage:true});
  await page.getByRole('button',{name:'Refresh status'}).click();await expect(page.getByRole('dialog').locator('.status')).toHaveText('ready');
  await row.getByRole('button',{name:'Review order'}).click();await admin.getByRole('button',{name:'Mark collected',exact:true}).click();await admin.getByRole('button',{name:'Confirm action'}).click();
  await page.getByRole('button',{name:'Refresh status'}).click();await expect(page.getByRole('dialog').locator('.status')).toHaveText('collected');
  expect(errors).toEqual([]);await adminContext.close();
});

test('mobile cancellation releases a reservation and the layout fits',async({page})=>{
  await page.setViewportSize({width:390,height:844});await page.goto('/');
  const vase=page.locator('.product-card').filter({has:page.getByRole('heading',{name:'Stem vase',exact:true})});
  await vase.getByRole('button',{name:'Add to bag'}).click();await page.getByRole('button',{name:/Bag 1/}).click();
  await page.getByRole('button',{name:'Reserve these objects'}).click();await page.getByLabel('Your name',{exact:true}).fill('Mobile Example');await page.getByLabel('Email',{exact:true}).fill('mobile@example.org');await page.getByRole('button',{name:'Confirm reservation'}).click();
  await expect(page.getByRole('heading',{name:'A little something, held for you.'})).toBeVisible();await page.getByRole('button',{name:'Cancel reservation'}).click();
  await expect(page.getByRole('dialog').locator('.status')).toHaveText('cancelled');await page.getByRole('button',{name:'Close dialog'}).click();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:'docs/mobile.png',fullPage:true});
});
