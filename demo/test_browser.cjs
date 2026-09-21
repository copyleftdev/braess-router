const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs=require('fs');const path=require('path');const out=path.join(__dirname,'../.impeccable/review/');fs.mkdirSync(out,{recursive:true});
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const results=[];
for(const [name,width] of [['desktop',1440],['mobile',390]]){
 const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:4174');await page.getByRole('button',{name:'Play replay',exact:true}).waitFor();await page.waitForFunction(()=>!document.getElementById('play').disabled);await page.evaluate(()=>document.fonts.ready);
 if(await page.locator('#completed').textContent()!=='1')throw Error('Final completed count');
 if(await page.locator('#uncertain').textContent()!=='1')throw Error('Final uncertain count');
 if(await page.locator('#deferred').textContent()!=='1')throw Error('Final deferred count');
 if(!(await page.locator('#selected-description').textContent()).includes('matched the source'))throw Error('Validated evidence missing');
 if(await page.locator('#route-scores .score-row').count()!==4)throw Error('Route distribution missing');
 if(await page.locator('#route-scores [data-choice=true] .score-value').textContent()!=='97.0%')throw Error('Wrong chosen probability');
 if(!(await page.locator('#gate-scores').textContent()).includes('99.0% / 80.0% minimum'))throw Error('Threshold evidence missing');
 if(await page.locator('.timing-fill').count()!==2)throw Error('Stage timings missing');
 await page.screenshot({path:out+'discovery-'+name+'.png',fullPage:true});
 await page.getByRole('button',{name:'Start',exact:true}).click();if(await page.locator('#completed').textContent()!=='0')throw Error('Start count');
 if(await page.locator('#deferred').textContent()!=='0'||await page.locator('#uncertain').textContent()!=='0')throw Error('Future outcomes leaked');
 if((await page.locator('#provenance').textContent()).includes('Validated review SHA-256'))throw Error('Future review provenance leaked');
 if(await page.locator('#route-scores .score-row').count()||await page.locator('.timing-fill').count())throw Error('Future decision evidence leaked');
 await page.locator('#seek').evaluate(e=>{e.value='500';e.dispatchEvent(new Event('input',{bubbles:true}))});if(await page.locator('#seek').inputValue()!=='500')throw Error('Seek failed');
 await page.locator('#seek').evaluate(e=>{e.value='1000';e.dispatchEvent(new Event('input',{bubbles:true}))});
 await page.locator('.task-row').nth(1).click();if(await page.locator('#selected-state').textContent()!=='Uncertain')throw Error('Task inspect failed');
 if(!(await page.locator('#selected-description').textContent()).includes('failed validation'))throw Error('Rejected evidence missing');
 await page.locator('.task-row').last().click();if(await page.locator('#selected-state').textContent()!=='Deferred')throw Error('Deferred state missing');
 if(!(await page.locator('#selected-description').textContent()).includes('before dispatch'))throw Error('Deferral explanation missing');
 if(!(await page.locator('#decision-summary').textContent()).includes('before a routing decision')||await page.locator('.timing-fill').count())throw Error('Deferred task invented decision evidence');
 await page.getByRole('button',{name:'Play replay',exact:true}).click();await page.getByRole('button',{name:'Pause replay',exact:true}).click();
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 const font=await page.evaluate(()=>document.fonts.check('400 16px Archivo'));
 if(errors.length||overflow||!font)throw Error('Browser quality check failed: '+JSON.stringify({name,errors,overflow,font}));
 results.push({name,errors,overflow,controls:'passed',font});
 await page.close();
}
// UI-only variants exercise old/partial/malformed metadata. They are never exported
// as verified recordings and do not claim new backend observations.
for(const variant of ['legacy','partial','malformed']){
 const data=JSON.parse(fs.readFileSync(path.join(__dirname,'web/replay.json'),'utf8'));
 const task=data.events[0].task_id;
 const response=data.events.find(e=>e.task_id===task&&e.kind==='response_received');
 if(variant==='legacy')for(const e of data.events)delete e.data.routing_trace;
 if(variant==='partial'){
   response.data.routing_trace.handler_validated_ns=null;
   delete response.data.route;delete response.data.reason;response.data.http_status=502;
   data.events=data.events.filter(e=>!(e.task_id===task&&e.kind==='review_validated'));
   const terminal=data.events.find(e=>e.task_id===task&&e.kind==='task_completed');
   terminal.kind='task_uncertain';terminal.data={error:'gateway_did_not_confirm_completion'};
   data.events.forEach((e,i)=>e.seq=i+1);
 }
 if(variant==='malformed')response.data.routing_trace.decision.confidence=2;
 const page=await browser.newPage({viewport:{width:390,height:1000}});
 await page.route('**/replay.json',r=>r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)}));
 await page.goto('http://127.0.0.1:4174');
 if(variant==='malformed'){
   await page.getByText('Recording unavailable',{exact:true}).waitFor();
   if(!await page.locator('#play').isDisabled())throw Error('Malformed trace enabled playback');
 }else{
   await page.waitForFunction(()=>!document.getElementById('play').disabled);
   if(variant==='legacy'&&await page.locator('.timing-fill').count())throw Error('Legacy trace invented');
   if(variant==='partial'&&(!(await page.locator('#stage-times').textContent()).includes('Validation not observed')||await page.locator('.timing-fill').count()!==1))throw Error('Partial trace falsely completed');
 }
 results.push({traceVariant:variant,passed:true});await page.close();
}
const errorPage=await browser.newPage();await errorPage.route('**/replay.json',r=>r.fulfill({status:404,body:'missing'}));await errorPage.goto('http://127.0.0.1:4174');await errorPage.getByText('Recording unavailable',{exact:true}).waitFor();results.push({errorState:true,disabled:await errorPage.locator('#play').isDisabled()});
const probe=await errorPage.request.get('http://127.0.0.1:4174/../docs/DOGFOOD.md');if(probe.status()!==404)throw Error('Private asset leaked');
fs.writeFileSync(out+'discovery-browser.json',JSON.stringify(results,null,2));console.log(results);await browser.close();})().catch(e=>{console.error(e);process.exit(1)});
