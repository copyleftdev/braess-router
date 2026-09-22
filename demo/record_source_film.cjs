// Private source-navigation capture. Records existing evidence; never invokes a provider.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {execFileSync}=require('child_process');
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const root=path.resolve(__dirname,'..'),origin=process.env.BRAESS_REPLAY_URL||'http://127.0.0.1:4180';
const imageInput=process.argv[3]==='--image-input';
if(process.argv[3]&&!imageInput)throw Error('Unknown capture mode');
const preview=new URL(origin);
if(preview.protocol!=='http:'||preview.hostname!=='127.0.0.1'||preview.origin!==origin)throw Error('Capture requires a loopback HTTP origin');
const sourceFiles=['demo/web/index.html','demo/web/style.css','demo/web/app.js','demo/web/inspector.css','demo/web/inspector.js',
 'demo/serve.py','demo/private_replay.py','demo/review_link.py','demo/vision_link.py','demo/record_source_film.cjs',
 'site/assets/archivo-400.woff2','site/assets/archivo-600.woff2','site/assets/mark.svg'];
const sourceHashes=()=>Object.fromEntries(sourceFiles.map(name=>[name,hash(fs.readFileSync(path.join(root,name)))]));
(async()=>{
 if(!process.argv[2])throw Error('Usage: node demo/record_source_film.cjs NEW_OUTPUT_DIRECTORY');
 const destination=path.resolve(process.argv[2]);fs.mkdirSync(destination,{mode:0o700});
 const sources=sourceHashes(),assets={},steps=[],errors=[];
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});let context;
 try{
  context=await browser.newContext({viewport:{width:1920,height:1080},recordVideo:{dir:destination,size:{width:1920,height:1080}},reducedMotion:'reduce'});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
  async function captureAsset(name){
   const response=await page.request.get(origin+'/'+name);if(!response.ok())throw Error('Capture asset unavailable');
   const raw=await response.body();assets[name]=hash(raw);return raw;
  }
  for(const name of ['index.html','style.css','app.js','inspector.css','inspector.js',
    'assets/archivo-400.woff2','assets/archivo-600.woff2','assets/mark.svg'])await captureAsset(name);
  const recording=JSON.parse(await captureAsset('replay.json')),links=JSON.parse(await captureAsset(imageInput?'image-link.json':'review-links.json'));
  const evidence=JSON.parse(await captureAsset('evidence/manifest.json'));
  const association=imageInput?links:links.links?.[0],findings=association?.review?.findings;
  if(recording.run.scope!=='synthetic'||!recording.sealed||recording.presentation.profile!==(imageInput?'private_execution':'private_review')||links.run_id!==recording.run.run_id||association?.inspector_manifest_sha256!==assets['evidence/manifest.json'])throw Error('Expected verified synthetic source recording');
  if(imageInput){
   const event=recording.events.find(e=>e.task_id===association.task_id&&e.kind==='response_received');
   if(association.association!=='verified_image_input_receipt'||association.pages.length!==2||association.response_event_sha256!==event?.sha256||association.reference_sha256!==event?.data.generation_input_evidence?.reference_sha256)throw Error('Expected two submitted scan pages');
  }else if(links.links.length!==1||findings.length!==1||findings[0].location.image_regions.length<1)throw Error('Expected mapped source finding');
  for(const name of ['evidence/text.txt','evidence/words.json',...evidence.pages.map((p,i)=>`evidence/page-${i+1}.png`)])await captureAsset(name);
  await page.goto(origin);await page.locator('.inspect-source').first().waitFor();await page.waitForFunction(()=>{const button=document.querySelector('.inspect-source');return button&&!button.disabled;});await page.evaluate(()=>document.fonts.ready);
  if(await page.locator('.task-row').count()!==1)throw Error('Unexpected source task count');
  const start=performance.now();
  const mark=async name=>steps.push({name,capture_elapsed_ms:performance.now()-start,
   visible_recorded_time:await page.locator('#time').textContent(),selected_document:await page.locator('#selected-title').textContent()});
  await mark('overview: scripted providers, actual local routing');await page.waitForTimeout(2500);
  await page.getByRole('button',{name:'Start',exact:true}).click();
  if(await page.locator('.inspect-source').count())throw Error('Future finding exposed');
  await page.locator('#speed').selectOption('0.01');await mark('recorded request at 0.01x');
  await page.getByRole('button',{name:'Play replay',exact:true}).click();
  await page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('End of recording'),{},{timeout:15000});
  await page.waitForTimeout(1500);
  await page.locator('.route-comparison').evaluate(e=>e.scrollIntoView({block:'start',behavior:'instant'}));
  await mark('visible route comparison and observation coverage');await page.waitForTimeout(4000);
  await page.locator('.review').evaluate(e=>e.scrollIntoView({block:'start',behavior:'instant'}));
  await mark(imageInput?'decision metadata and image-input receipt':'decision metadata and source-validated result');await page.waitForTimeout(3500);
  if(imageInput){
   await page.locator('#submitted-pages').evaluate(e=>e.scrollIntoView({block:'center',behavior:'instant'}));
   await mark('image receipt and submitted page controls');await page.waitForTimeout(3500);
   for(const selected of association.pages){
    await page.getByRole('button',{name:'Inspect submitted page '+selected.page,exact:true}).click();
    await page.locator('#source-image').evaluate(async image=>{await image.decode();await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));});
    if(await page.locator('#source-image').evaluate(image=>image.naturalHeight)!==selected.height||await page.locator('.finding-box').count())throw Error('Submitted page mismatch');
    await mark('submitted page '+selected.page+': exact input pixels, no understanding claim');await page.waitForTimeout(5500);
   }
   await page.locator('#source-zoom').selectOption('native');
   await mark('native pixel view of submitted input');await page.waitForTimeout(3500);
  }else{
   await page.locator('#linked-findings').evaluate(e=>e.scrollIntoView({block:'center',behavior:'instant'}));
   await mark('provisional quote and exact source range');await page.waitForTimeout(3500);
   await page.locator('.inspect-source').click();
   if(await page.locator('.finding-box').count()!==findings[0].location.image_regions.length)throw Error('Missing image regions');
   await mark('finding opens matching source page');await page.waitForTimeout(4500);
   await page.locator('.source-controls').evaluate(e=>e.scrollIntoView({block:'start',behavior:'instant'}));
   await mark('scan regions and corresponding transcript');await page.waitForTimeout(5500);
   await page.locator('#source-zoom').selectOption('native');
   await mark('source-pixel view, whole-word OCR geometry');await page.waitForTimeout(4500);
  }
  await page.locator('#source-zoom').selectOption('fit');
  await page.getByRole('button',{name:'Start',exact:true}).click();
  if(await page.locator('.finding-box').count()||await page.locator('#source-selection').isVisible())throw Error('Finding persists before validation');
  await page.locator('#source-heading').evaluate(e=>e.scrollIntoView({block:'start',behavior:'instant'}));
  await mark('rewind clears the source association');await page.waitForTimeout(2500);
  await page.locator('#seek').evaluate(e=>{e.value='1000';e.dispatchEvent(new Event('input',{bubbles:true}))});
  await page.evaluate(()=>scrollTo({top:0,behavior:'instant'}));
  await mark('close: recorded scope, cost unknown');await page.waitForTimeout(2500);
  if(errors.length||await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Capture browser failure');
  const video=page.video();await context.close();context=null;
  const webm=path.join(destination,'source-replay.webm');await video.saveAs(webm);
  const original=await video.path();if(original!==webm)fs.unlinkSync(original);
  if(JSON.stringify(sourceHashes())!==JSON.stringify(sources))throw Error('Renderer changed during capture');
  // Re-read server bytes with a separate request context after recording stops.
  const requests=await browser.newContext();
  try{for(const [name,expected] of Object.entries(assets)){
   const response=await requests.request.get(origin+'/'+name);if(!response.ok()||hash(await response.body())!==expected)throw Error('Served evidence changed during capture');
  }}finally{await requests.close();}
  const mp4=path.join(destination,'source-replay.mp4');
  execFileSync('ffmpeg',['-nostdin','-v','error','-n','-i',webm,'-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',mp4]);
  const probe=JSON.parse(execFileSync('ffprobe',['-v','error','-show_entries','format=duration:stream=codec_name,width,height,nb_frames','-of','json',mp4],{encoding:'utf8'}));
  if(probe.streams.length!==1||probe.streams[0].width!==1920||probe.streams[0].height!==1080||Number(probe.format.duration)<25)throw Error('Invalid film dimensions or duration');
  fs.writeFileSync(path.join(destination,'capture.json'),JSON.stringify({schema_version:1,
   scope:imageInput?'private image-input film draft; real local routing with scripted providers':'private OCR source-navigation film draft; real local routing with scripted providers',
   run_id:recording.run.run_id,task_id:association.task_id,document_id:association.document_id,
   source_hashes:sources,served_asset_hashes:assets,steps,probe,
   preview_origin:origin,
   timing:'Scene elapsed time begins after page readiness, excludes loading pre-roll and is not exact video PTS. Observer time and gateway offsets remain separate.',
   external_provider_calls:0,contains_private_source_content:true,publication_approved:false,
   semantic_accuracy:'not_evaluated',artifacts:{'source-replay.webm':hash(fs.readFileSync(webm)),'source-replay.mp4':hash(fs.readFileSync(mp4))}},null,2)+'\n',{flag:'wx',mode:0o600});
  console.log(JSON.stringify({passed:true,output:destination,duration_seconds:Number(probe.format.duration),external_provider_calls:0}));
 }finally{if(context)await context.close();await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1});
