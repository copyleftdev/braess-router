const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const out=path.join(__dirname,'../.impeccable/review');fs.mkdirSync(out,{recursive:true});
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const results=[];
try {
for(const [name,width] of [['desktop',1440],['mobile',390]]){
 const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:4176');await page.locator('.linked-finding').waitFor();await page.evaluate(()=>document.fonts.ready);
 assert.equal(await page.locator('.task-row').count(),4);assert.equal(await page.locator('.linked-finding blockquote').textContent(),'meeting');
 await page.getByRole('button',{name:'Start',exact:true}).click();assert.equal(await page.locator('.linked-finding').count(),0);
 const replay=await (await page.request.get('http://127.0.0.1:4176/replay.json')).json();
 const validation=replay.events.find(e=>e.kind==='review_validated'),duration=replay.events.at(-1).elapsed_ns;
 async function seek(n){await page.locator('#seek').evaluate((el,value)=>{el.value=String(value);el.dispatchEvent(new Event('input',{bubbles:true}))},n);}
 await seek(Math.max(0,Math.floor(validation.elapsed_ns/duration*1000)-1));assert.equal(await page.locator('.linked-finding').count(),0);
 await seek(Math.ceil(validation.elapsed_ns/duration*1000));assert.equal(await page.locator('.linked-finding').count(),1);
 await seek(1000);
 for(const i of [1,2,3]){await page.locator('.task-row').nth(i).click();assert.equal(await page.locator('.linked-finding').count(),0);}
 await page.locator('.task-row').first().click();assert.equal(await page.locator('.linked-finding').count(),1);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.deepEqual(errors,[]);
 await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(out,`linked-${name}.png`),fullPage:true});
 results.push({name,clock_gate:'passed',task_selection:'passed',errors,overflow:false});await page.close();
}
for(const variant of ['run','task','review_hash','timestamp','live_copy']){
 const page=await browser.newPage();const links=await(await page.request.get('http://127.0.0.1:4176/review-links.json')).json();
 if(variant==='run')links.run_id='other-run';
 if(variant==='task')links.links[0].task_id='a'.repeat(64);
 if(variant==='review_hash')links.links[0].review_sha256='a'.repeat(64);
 if(variant==='timestamp')links.links[0].finding_visibility_after_elapsed_ns=0;
 if(variant==='live_copy'){
  links.scope='live';links.links.forEach(l=>l.scope='live');
  const replay=await(await page.request.get('http://127.0.0.1:4176/replay.json')).json();replay.run.scope='live';
  await page.route('**/replay.json',r=>r.fulfill({contentType:'application/json',body:JSON.stringify(replay)}));
 }
 await page.route('**/review-links.json',r=>r.fulfill({contentType:'application/json',body:JSON.stringify(links)}));
 await page.goto('http://127.0.0.1:4176');
 if(variant==='live_copy'){
  await page.locator('.linked-finding').waitFor();assert.equal(await page.locator('#scope-label').textContent(),'Private recording / live providers');
  assert.ok(!(await page.locator('#score-note').textContent()).includes('synthetic'));
 }else{
  await page.waitForFunction(()=>document.getElementById('findings-status').textContent.includes('could not be verified'));
  assert.equal(await page.locator('.linked-finding').count(),0);
 }
 results.push({variant,passed:true,scope:'UI-only intercepted fixture'});await page.close();
}
fs.writeFileSync(path.join(out,'linked-browser.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
