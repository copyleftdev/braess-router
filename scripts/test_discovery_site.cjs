const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const origin=process.env.BRAESS_SITE_URL || 'http://127.0.0.1:4190/braess-router/';
fs.mkdirSync('.impeccable/review',{recursive:true});
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
for(const [name,width] of [['desktop',1440],['mobile',390]]){
 const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r.url()));page.on('response',r=>{if(r.status()>=400)errors.push(`${r.status()} ${r.url()}`)});
 await page.goto(origin);await page.evaluate(()=>document.fonts.ready);
 await page.locator('#discovery').scrollIntoViewIfNeeded();
 await page.screenshot({path:`.impeccable/review/showcase-home-${name}.png`});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.getByRole('link',{name:'Explore the discovery replay'}).click();await page.locator('.task-row').first().waitFor();await page.evaluate(()=>document.fonts.ready);
 assert.equal(await page.locator('.task-row').count(),4);assert.equal(await page.locator('#completed').textContent(),'2');assert.equal(await page.locator('#uncertain').textContent(),'1');assert.equal(await page.locator('#deferred').textContent(),'1');
 await page.screenshot({path:`.impeccable/review/showcase-intro-${name}.png`});
 await page.locator('.instrument').evaluate(e=>e.scrollIntoView({block:'start'}));await page.screenshot({path:`.impeccable/review/showcase-flow-${name}.png`});
 const opts=await page.locator('#flow-task option').evaluateAll(ns=>ns.map(n=>n.value));
 await page.locator('#flow-task').selectOption(opts[1]);assert.match(await page.locator('#branch-outcome').textContent(),/uncertain/i);
 await page.locator('#flow-task').selectOption(opts[3]);assert.match(await page.locator('#branch-outcome').textContent(),/Deferred before dispatch/);
 await page.getByRole('button',{name:'Start',exact:true}).click();assert.equal(await page.locator('#branch-choice').textContent(),'Not observed yet');
 await page.getByRole('button',{name:'Play replay',exact:true}).click();await page.waitForTimeout(250);await page.getByRole('button',{name:'Pause replay',exact:true}).click();
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.deepEqual(errors,[]);assert.ok(requests.every(u=>new URL(u).origin===new URL(origin).origin));console.log(`${name}: four tasks, outcomes, reset, playback, subpath, no remote calls, no overflow passed`);await page.close();
}}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
