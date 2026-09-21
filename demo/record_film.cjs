// Capture the actual replay UI. This is a synthetic-run film draft, not a live run.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs');
const path=require('path');
const crypto=require('crypto');
const {execFileSync}=require('child_process');
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const root=path.resolve(__dirname,'..');
const files=['demo/web/index.html','demo/web/style.css','demo/web/app.js','demo/web/replay.json',
  'site/assets/archivo-400.woff2','site/assets/archivo-600.woff2','site/assets/mark.svg','demo/record_film.cjs'];
function sources(){return Object.fromEntries(files.map(name=>[name,hash(fs.readFileSync(path.join(root,name)))]));}

(async()=>{
  const output=process.argv[2];
  if(!output)throw Error('Usage: node demo/record_film.cjs NEW_OUTPUT_DIRECTORY');
  const destination=path.resolve(output);
  fs.mkdirSync(destination,{mode:0o700}); // Refuse overwriting any existing capture.
  const sourceHashes=sources();
  const recording=JSON.parse(fs.readFileSync(path.join(__dirname,'web/replay.json'),'utf8'));
  if(recording.run.scope!=='synthetic'||recording.presentation.profile!=='fleet'||!recording.sealed)
    throw Error('Capture requires the reviewed synthetic fleet replay');
  const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  let context;
  const steps=[],started=performance.now(),errors=[];
  const mark=name=>steps.push({name,capture_elapsed_ms:performance.now()-started});
  try{
    context=await browser.newContext({viewport:{width:1440,height:1100},
      recordVideo:{dir:destination,size:{width:1440,height:1100}},reducedMotion:'reduce'});
    const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
    // Fetches stay on the explicit loopback preview. No provider endpoint is used.
    await page.route('**/*',async route=>{
      if(new URL(route.request().url()).origin!=='http://127.0.0.1:4174')return route.abort();
      return route.continue();
    });
    await page.goto('http://127.0.0.1:4174');
    await page.waitForFunction(()=>!document.getElementById('play').disabled);
    await page.evaluate(()=>document.fonts.ready);
    const served=await page.request.get('http://127.0.0.1:4174/replay.json');
    if(hash(await served.body())!==sourceHashes['demo/web/replay.json'])throw Error('Served recording differs from source');
    mark('overview: actual execution, synthetic providers');await page.waitForTimeout(2500);
    await page.getByRole('button',{name:'Start',exact:true}).click();
    await page.locator('#speed').selectOption('0.01');
    mark('recorded traffic at 0.01x');
    await page.getByRole('button',{name:'Play replay',exact:true}).click();
    await page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('End of recording'),{},{timeout:15000});
    if(await page.locator('#completed').textContent()!=='1'||await page.locator('#uncertain').textContent()!=='1'||await page.locator('#deferred').textContent()!=='1')throw Error('Unexpected fleet outcomes');
    await page.waitForTimeout(1500);
    await page.locator('.review').evaluate(node=>node.scrollIntoView({block:'start',behavior:'instant'}));
    mark('accepted evidence and measured routing decision');await page.waitForTimeout(5500);
    await page.locator('.task-row').nth(1).click();
    if(!(await page.locator('#selected-description').textContent()).includes('failed validation'))throw Error('Rejected evidence scene missing');
    mark('rejected quote remains uncertain');await page.waitForTimeout(4000);
    await page.locator('.task-row').nth(2).click();
    if(!(await page.locator('#decision-summary').textContent()).includes('before a routing decision'))throw Error('Budget scene missing');
    mark('budget deferral before dispatch');await page.waitForTimeout(3500);
    await page.locator('.task-row').first().click();
    await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
    mark('close: recorded scope and outcomes');await page.waitForTimeout(2000);
    if(errors.length)throw Error('Browser capture error');
    await context.close();context=null;
    const webm=path.join(destination,'replay.webm');
    await page.video().saveAs(webm);
    const original=await page.video().path();if(original!==webm)fs.unlinkSync(original);
    if(JSON.stringify(sources())!==JSON.stringify(sourceHashes))throw Error('Renderer changed during capture');
    const mp4=path.join(destination,'replay.mp4');
    execFileSync('ffmpeg',['-nostdin','-v','error','-n','-i',webm,'-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',mp4]);
    const probe=JSON.parse(execFileSync('ffprobe',['-v','error','-show_entries','format=duration:stream=codec_name,width,height,nb_frames','-of','json',mp4],{encoding:'utf8'}));
    if(probe.streams.length!==1||probe.streams[0].width!==1440||probe.streams[0].height!==1100||Number(probe.format.duration)<20)throw Error('Invalid encoded film');
    const manifest={schema_version:1,scope:'synthetic fleet replay film draft',run_id:recording.run.run_id,
      source_hashes:sourceHashes,steps,probe,provider_calls:0,
      timing:'Capture wall time is separate from recorded observer and gateway clocks.',
      artifacts:{'replay.webm':hash(fs.readFileSync(webm)),'replay.mp4':hash(fs.readFileSync(mp4))},
      publication_approved:false,legal_accuracy:'not_established'};
    fs.writeFileSync(path.join(destination,'capture.json'),JSON.stringify(manifest,null,2)+'\n',{flag:'wx',mode:0o600});
    console.log(JSON.stringify({passed:true,output:destination,duration_seconds:Number(probe.format.duration),provider_calls:0}));
  }finally{if(context)await context.close();await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
