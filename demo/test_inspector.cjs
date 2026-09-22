const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const out=path.join(__dirname,'../.impeccable/review');fs.mkdirSync(out,{recursive:true});
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const results=[];
try {
for(const [name,width] of [['desktop',1440],['mobile',390]]) {
 const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:4175');await page.waitForFunction(()=>document.getElementById('source-status').textContent.includes('asset hashes verified'));
 await page.evaluate(()=>document.fonts.ready);
 assert.equal(await page.locator('#source-page option').count(),2);
 const first=await page.locator('#source-word option').count();assert.ok(first>0);
 await page.locator('#source-word').selectOption('5');
 assert.equal(await page.locator('#source-transcript mark').count(),1);
 const words=await (await page.request.get('http://127.0.0.1:4175/evidence/words.json')).json();
 const box=words.filter(w=>w.page===1)[5].box;
 for(const [i,key] of ['x','y','width','height'].entries())assert.equal(Number(await page.locator('#source-box').getAttribute(key)),box[i]);
 assert.ok((await page.locator('#source-word-detail').textContent()).includes('source pixels'));
 await page.locator('#source-page').selectOption('1');
 assert.ok((await page.locator('#source-dimensions').textContent()).includes('source pixels'));
 await page.locator('#source-overlay').click();assert.equal(await page.locator('#source-overlay').getAttribute('aria-pressed'),'false');
 await page.locator('#source-overlay').click();
 await page.locator('#source-zoom').selectOption('native');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.locator('#source-zoom').selectOption('fit');await page.locator('#source-page').selectOption('0');
 await page.locator('#source-word').selectOption('5');
 await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(out,`inspector-${name}.png`),fullPage:true});
 await page.locator('#source-inspector').scrollIntoViewIfNeeded();
 await page.screenshot({path:path.join(out,`inspector-detail-${name}.png`)});
 assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>document.fonts.check('400 16px Archivo')),true);
 for(const forbidden of ['source-document.json','../manifest.json','%2e%2e/manifest.json'])assert.equal((await page.request.get('http://127.0.0.1:4175/evidence/'+forbidden)).status(),404);
 results.push({name,errors,overflow:false,pages:2,controls:'passed'});await page.close();
}
for(const variant of ['corrupt','missing']) {
 const page=await browser.newPage();
 if(variant==='corrupt')await page.route('**/evidence/words.json',r=>r.fulfill({contentType:'application/json',body:'[]'}));
 else await page.route('**/evidence/manifest.json',r=>r.fulfill({status:404,body:''}));
 await page.goto('http://127.0.0.1:4175');
 if(variant==='corrupt') {await page.waitForFunction(()=>document.getElementById('source-status').textContent.includes('could not be verified'));assert.equal(await page.locator('#source-content').isVisible(),false);}
 else {await page.waitForLoadState('networkidle');assert.equal(await page.locator('#source-inspector').isVisible(),false);}
 results.push({variant,passed:true});await page.close();
}
{
 const page=await browser.newPage();
 const m=await (await page.request.get('http://127.0.0.1:4175/evidence/manifest.json')).json();
 const text='A 😀 café';const words=[{page:1,start_character:0,end_character:1,box:[1,1,10,10],confidence:90},{page:1,start_character:2,end_character:3,box:[20,1,10,10],confidence:80},{page:1,start_character:4,end_character:8,box:[40,1,20,10],confidence:70}];
 const crypto=require('crypto'),raw=JSON.stringify(words),hash=v=>crypto.createHash('sha256').update(v).digest('hex');
 m.pages=m.pages.slice(0,1);m.text.sha256=hash(text);m.words.sha256=hash(raw);m.words.count=3;
 await page.route('**/evidence/manifest.json',r=>r.fulfill({contentType:'application/json',body:JSON.stringify(m)}));
 await page.route('**/evidence/text.txt',r=>r.fulfill({contentType:'text/plain',body:text}));
 await page.route('**/evidence/words.json',r=>r.fulfill({contentType:'application/json',body:raw}));
 await page.goto('http://127.0.0.1:4175');await page.waitForFunction(()=>document.getElementById('source-status').textContent.includes('asset hashes verified'));
 await page.locator('#source-word').selectOption('1');assert.equal(await page.locator('#source-transcript mark').textContent(),'😀');
 await page.locator('#source-word').selectOption('2');assert.equal(await page.locator('#source-transcript mark').textContent(),'café');
 results.push({variant:'synthetic_unicode_offsets',passed:true});await page.close();
}
fs.writeFileSync(path.join(out,'inspector-browser.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
} finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
