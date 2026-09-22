const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.join(__dirname,'..'),out=path.join(root,'.impeccable/review');
const replay=JSON.parse(fs.readFileSync(path.join(root,'artifacts/discovery-policy-v2/replay.json')));
const metrics=JSON.parse(fs.readFileSync(path.join(root,'artifacts/discovery-policy-v2/route-metrics-v2.json')));
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const results=[];
try{for(const [name,width] of [['desktop',1440],['mobile',390]]){
 const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/replay.json',r=>r.fulfill({json:replay}));
 await page.route('**/review-links.json',r=>r.fulfill({status:404,body:''}));
 await page.route('**/evidence/manifest.json',r=>r.fulfill({status:404,body:''}));
 await page.goto('http://127.0.0.1:4180');await page.locator('.comparison-row').first().waitFor();await page.evaluate(()=>document.fonts.ready);
 for(const cohort of metrics.by_route){
  const row=page.locator('.comparison-row').filter({has:page.locator(`h3:text-is("${cohort.route.replaceAll('_',' ')}")`)});
  assert.equal(await row.count(),1);
  const values=await row.locator('dd').evaluateAll(es=>es.map(e=>e.firstChild.textContent));
  assert.deepEqual(values,[String(cohort.tasks),cohort.timing.observer_request_ms.p50.toFixed(2)+' ms',
    ...['decision_transport_ns','handler_transport_ns'].map(k=>cohort.timing[k].p50===null?'Unknown':(cohort.timing[k].p50/1e6).toFixed(2)+' ms')]);
 }
 assert.ok((await page.locator('#comparison-unrouted').textContent()).startsWith('1 visible task has'));
 await page.getByRole('button',{name:'Start',exact:true}).click();
 assert.equal(await page.locator('.comparison-row').count(),0);
 assert.ok((await page.locator('#route-comparison').textContent()).includes('No returned routes'));
 await page.locator('#seek').evaluate(e=>{e.value='500';e.dispatchEvent(new Event('input',{bubbles:true}))});
 const time=replay.events.at(-1).elapsed_ns*.5;
 const routes=new Set(replay.events.filter(e=>e.elapsed_ns<=time&&e.kind==='response_received').map(e=>e.data.route));
 assert.deepEqual(new Set(await page.locator('.comparison-row').evaluateAll(es=>es.map(e=>e.dataset.route))),routes);
 await page.locator('#seek').evaluate(e=>{e.value='1000';e.dispatchEvent(new Event('input',{bubbles:true}))});
 assert.equal(await page.locator('.comparison-row').count(),metrics.by_route.length);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(out,`route-comparison-${name}.png`),fullPage:true});
 await page.locator('.route-comparison').evaluate(e=>e.scrollIntoView({block:'start',behavior:'instant'}));
 await page.screenshot({path:path.join(out,`route-comparison-detail-${name}.png`)});
 assert.deepEqual(errors,[]);results.push({name,python_metrics_parity:true,rewind_clears:true,partial_clock_routes:true,overflow:false,errors});await page.close();
}fs.writeFileSync(path.join(out,'route-comparison-browser.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
