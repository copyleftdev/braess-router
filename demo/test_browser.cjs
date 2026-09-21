const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs=require('fs');const path=require('path');const out=path.join(__dirname,'../.impeccable/review/');fs.mkdirSync(out,{recursive:true});
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const results=[];
for(const [name,width] of [['desktop',1440],['mobile',390]]){
 const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:4174');await page.getByRole('button',{name:'Play replay',exact:true}).waitFor();await page.waitForFunction(()=>!document.getElementById('play').disabled);await page.evaluate(()=>document.fonts.ready);
 if(await page.locator('#completed').textContent()!=='4')throw Error('Final completed count');
 if(await page.locator('#uncertain').textContent()!=='2')throw Error('Final uncertain count');
 await page.screenshot({path:out+'discovery-'+name+'.png',fullPage:true});
 await page.getByRole('button',{name:'Start',exact:true}).click();if(await page.locator('#completed').textContent()!=='0')throw Error('Start count');
 await page.locator('#seek').evaluate(e=>{e.value='500';e.dispatchEvent(new Event('input',{bubbles:true}))});if(await page.locator('#seek').inputValue()!=='500')throw Error('Seek failed');
 await page.locator('#seek').evaluate(e=>{e.value='1000';e.dispatchEvent(new Event('input',{bubbles:true}))});
 await page.locator('.task-row').last().click();if(await page.locator('#selected-state').textContent()!=='Uncertain')throw Error('Task inspect failed');
 await page.getByRole('button',{name:'Play replay',exact:true}).click();await page.getByRole('button',{name:'Pause replay',exact:true}).click();
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 results.push({name,errors,overflow,controls:'passed',font:await page.evaluate(()=>document.fonts.check('400 16px Archivo'))});
 await page.close();
}
const errorPage=await browser.newPage();await errorPage.route('**/replay.json',r=>r.fulfill({status:404,body:'missing'}));await errorPage.goto('http://127.0.0.1:4174');await errorPage.getByText('Recording unavailable',{exact:true}).waitFor();results.push({errorState:true,disabled:await errorPage.locator('#play').isDisabled()});
const probe=await errorPage.request.get('http://127.0.0.1:4174/../docs/DOGFOOD.md');if(probe.status()!==404)throw Error('Private asset leaked');
fs.writeFileSync(out+'discovery-browser.json',JSON.stringify(results,null,2));console.log(results);await browser.close();})().catch(e=>{console.error(e);process.exit(1)});
