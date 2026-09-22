const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const origin=process.env.BRAESS_REPLAY_URL||'http://127.0.0.1:4180';
const out=path.join(__dirname,'../.impeccable/review');fs.mkdirSync(out,{recursive:true});
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const results=[];
try{
for(const [name,width] of [['desktop',1440],['mobile',390]]){
 const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(origin);await page.locator('.inspect-source').waitFor();await page.evaluate(()=>document.fonts.ready);
 await page.locator('.inspect-source').click();
 assert.equal(await page.locator('.finding-box').count(),5);
 assert.ok((await page.locator('#source-context').textContent()).includes('Synthetic reviewer finding'));
 const marked=(await page.locator('#source-transcript mark').allTextContents()).join(' ');
 assert.equal(marked,'the US multinational company Enron');
 assert.equal(await page.locator('#source-selection').isVisible(),true);
 await page.locator('#source-zoom').selectOption('native');
 assert.equal(await page.locator('.finding-box').count(),5);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.locator('#source-zoom').selectOption('fit');
 const links=await(await page.request.get(origin+'/review-links.json')).json();const association=links.links[0],finding=association.review.findings[0];
 const boxes=await page.locator('.finding-box').evaluateAll(nodes=>nodes.map(n=>['x','y','width','height'].map(k=>Number(n.getAttribute(k)))));
 assert.deepEqual(boxes,finding.location.image_regions.map(r=>r.box));
 for(const variant of ['source','box','task']){
  const a=JSON.parse(JSON.stringify(association)),f=JSON.parse(JSON.stringify(finding));
  if(variant==='source')a.source_sha256='0'.repeat(64);
  if(variant==='task')a.task_id='0'.repeat(64);
  if(variant==='box')f.location.image_regions[0].box[0]+=1;
  assert.equal(await page.evaluate(({a,f})=>window.braessSource.show(a,f,1),{a,f}),false);
 }
 await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(out,`source-navigation-${name}.png`),fullPage:true});
 await page.getByRole('button',{name:'Start',exact:true}).click();
 assert.equal(await page.locator('.finding-box').count(),0);assert.equal(await page.locator('#source-selection').isVisible(),false);
 assert.equal(await page.locator('.inspect-source').count(),0);
 await page.locator('#seek').evaluate(el=>{el.value='1000';el.dispatchEvent(new Event('input',{bubbles:true}))});
 await page.locator('.inspect-source').click();await page.locator('#source-page').selectOption('1');
 assert.equal(await page.locator('.finding-box').count(),0);assert.equal(await page.locator('#source-selection').isVisible(),false);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.deepEqual(errors,[]);
 results.push({name,exact_boxes:true,quote:marked,reset_clears:true,page_change_clears:true,tampered_associations_rejected:true,overflow:false,errors});await page.close();
}
fs.writeFileSync(path.join(out,'source-navigation-browser.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
