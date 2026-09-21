const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const origin=process.env.BRAESS_REPLAY_URL||'http://127.0.0.1:4183',out=path.join(__dirname,'../.impeccable/review');
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const results=[];
try{for(const [name,width] of [['desktop',1440],['mobile',390]]){
 const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(origin);await page.waitForFunction(()=>window.braessSource&&document.querySelectorAll('#submitted-actions button').length===2);
 await page.evaluate(()=>document.fonts.ready);
 const link=await(await page.request.get(origin+'/image-link.json')).json();
 assert.equal(await page.locator('#submitted-actions button').count(),2);
 await page.locator('#submitted-pages').evaluate(e=>e.scrollIntoView({block:'center',behavior:'instant'}));
 await page.screenshot({path:path.join(out,`submitted-pages-${name}.png`)});
 for(const number of [1,2]){
  await page.getByRole('button',{name:'Inspect submitted page '+number,exact:true}).click();
  await page.locator('#source-image').evaluate(async image=>{await image.decode();await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));});
  assert.equal(await page.locator('#source-page').inputValue(),String(number-1));
  assert.equal(await page.locator('#source-image').evaluate(image=>image.naturalHeight),link.pages[number-1].height);
  assert.ok((await page.locator('#source-selection').textContent()).includes('Submitted page '+number));
  assert.ok((await page.locator('#source-context').textContent()).includes('model understanding is not established'));
  assert.equal(await page.locator('.finding-box').count(),0);
  assert.equal(await page.locator('#source-transcript mark').count(),0);
 }
 await page.screenshot({path:path.join(out,`submitted-source-${name}.png`)});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.locator('#source-page').selectOption('0');assert.equal(await page.locator('#source-selection').isVisible(),false);
 await page.getByRole('button',{name:'Inspect submitted page 2',exact:true}).click();
 await page.getByRole('button',{name:'Start',exact:true}).click();
 assert.equal(await page.locator('#submitted-actions button').count(),0);
 assert.equal(await page.locator('#source-selection').isVisible(),false);
 const rejected=await page.evaluate(a=>window.braessSource.showInput(a,1),link);assert.equal(rejected,false);
 const invalid={...link,reference_sha256:'0'.repeat(64)};
 await page.route('**/image-link.json',r=>r.fulfill({json:invalid}));await page.reload();
 await page.waitForFunction(()=>document.getElementById('submitted-status').textContent.includes('could not be verified'));
 assert.equal(await page.locator('#submitted-actions button').count(),0);
 assert.deepEqual(errors,[]);results.push({name,pages_navigable:true,rewind_clears:true,manual_page_clears:true,invalid_association_rejected:true,overflow:false,errors});await page.close();
}fs.writeFileSync(path.join(out,'submitted-pages-browser.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
