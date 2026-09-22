const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const origin='http://127.0.0.1:4182',out=path.join(__dirname,'../.impeccable/review');
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const results=[];
try{for(const [name,width] of [['desktop',1440],['mobile',390]]){
 const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(origin);await page.locator('.task-row').waitFor();await page.evaluate(()=>document.fonts.ready);
 const data=await(await page.request.get(origin+'/replay.json')).json();
 const input=data.events.find(e=>e.kind==='response_received').data.generation_input_evidence;
 const fact=()=>page.locator('#facts dt').filter({hasText:'Reviewer input'}).locator('xpath=following-sibling::dd[1]');
 assert.equal(await fact().textContent(),'Text + 1 image (receipt)');
 await page.locator('.evidence details summary').click();
 const provenance=await page.locator('#provenance').textContent();
 assert.ok(provenance.includes(input.reference_sha256));assert.ok(provenance.includes(input.image_sha256[0]));
 assert.ok(provenance.includes('image understanding is not established'));
 assert.equal(await page.locator('#linked-findings').isVisible(),false);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(out,`image-input-${name}.png`),fullPage:true});
 await page.locator('.evidence').evaluate(e=>e.scrollIntoView({block:'start',behavior:'instant'}));
 await page.screenshot({path:path.join(out,`image-input-detail-${name}.png`)});
 await page.getByRole('button',{name:'Start',exact:true}).click();
 assert.equal(await fact().textContent(),'Not reported');
 assert.ok(!(await page.locator('#provenance').textContent()).includes(input.reference_sha256));
 const legacy=structuredClone(data);delete legacy.events.find(e=>e.kind==='response_received').data.generation_input_evidence;
 await page.route('**/replay.json',r=>r.fulfill({json:legacy}));await page.reload();await page.locator('.task-row').waitFor();
 assert.equal(await fact().textContent(),'Not reported');
 for(const evidence of [{...input,prompt:'private'}, {...input,image_sha256:[]}, {...input,image_sha256:['bad']}, {...input,image_sha256:Array(9).fill(input.image_sha256[0])}]){
  const invalid=structuredClone(data);invalid.events.find(e=>e.kind==='response_received').data.generation_input_evidence=evidence;
  await page.unroute('**/replay.json');await page.route('**/replay.json',r=>r.fulfill({json:invalid}));await page.reload();
  await page.waitForFunction(()=>document.getElementById('scope-label').textContent==='Recording unavailable');
  assert.equal(await page.locator('.task-row').count(),0);
 }
 assert.deepEqual(errors,[]);results.push({name,receipt_hashes_visible:true,rewind_clears:true,legacy_unknown:true,invalid_receipts_rejected:true,overflow:false,errors});await page.close();
}fs.writeFileSync(path.join(out,'image-input-browser.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
