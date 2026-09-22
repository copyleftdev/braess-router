// Render the public four-task showcase using existing speech alignment. No TTS calls.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {execFileSync}=require('node:child_process');
const assert=require('node:assert/strict');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const root=path.resolve(__dirname,'..');
const sourceFiles=['index.html','style.css','app.js','replay.json'];
const run=async()=>{
 const source=path.resolve(process.argv[2]||''),destination=path.resolve(process.argv[3]||'');
 if(process.argv.length!==4)throw Error('Usage: node demo/render_narrated_film.cjs NARRATION_DIRECTORY NEW_FILM_DIRECTORY');
 const origin=new URL(process.env.BRAESS_FILM_URL||'http://127.0.0.1:4190/braess-router/discovery/index.html');
 if(origin.protocol!=='http:'||origin.hostname!=='127.0.0.1')throw Error('Loopback preview required');
 const scenes=JSON.parse(fs.readFileSync(path.join(source,'scenes.json')));
 assert.equal(scenes.length,7);assert.equal(scenes[0].start_seconds,0);
 for(const [i,s] of scenes.entries()){assert.equal(s.index,i);assert.ok(s.end_seconds>s.start_seconds);assert.ok(s.end_seconds-s.start_seconds<60);if(i)assert.equal(s.start_seconds,scenes[i-1].end_seconds);}
 const recording=JSON.parse(fs.readFileSync(path.join(root,'site/discovery/replay.json')));
 assert.equal(recording.run.scope,'synthetic');assert.equal(recording.presentation.profile,'discovery');
 fs.mkdirSync(destination,{mode:0o700});
 const snapshots=Object.fromEntries(sourceFiles.map(n=>[n,sha(fs.readFileSync(path.join(root,'site/discovery',n)))]));
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const captures=[];
 try{
 for(const s of scenes){
  const dir=path.join(destination,`scene-${s.index+1}`);fs.mkdirSync(dir);
  const context=await browser.newContext({viewport:{width:1920,height:1080},recordVideo:{dir,size:{width:1920,height:1080}},reducedMotion:'reduce'});
  try{
   const page=await context.newPage(),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/*',r=>new URL(r.request().url()).origin===origin.origin?r.continue():r.abort());
   await page.goto(origin.href);await page.waitForFunction(()=>!document.querySelector('#play').disabled);await page.evaluate(()=>document.fonts.ready);
   for(const name of sourceFiles){const response=await page.request.get(new URL(name,origin).href);assert.equal(response.status(),200);assert.equal(sha(await response.body()),snapshots[name]);}
   assert.equal(await page.locator('.task-row').count(),4);
   assert.equal(await page.locator('#completed').textContent(),'2');assert.equal(await page.locator('#uncertain').textContent(),'1');assert.equal(await page.locator('#deferred').textContent(),'1');
   const opts=await page.locator('#flow-task option').evaluateAll(ns=>ns.map(n=>n.value));
   if(s.index===0){await page.evaluate(()=>scrollTo(0,0));}
   else if(s.index===1){await page.locator('.instrument').evaluate(e=>e.scrollIntoView({block:'start'}));}
   else if(s.index===2){await page.locator('#flow-task').selectOption(opts[0]);await page.locator('.review').evaluate(e=>e.scrollIntoView({block:'start'}));assert.match(await page.locator('#selected-description').textContent(),/quote and coordinates matched the source/i);}
   else if(s.index===3){await page.locator('#flow-task').selectOption(opts[1]);await page.locator('.review').evaluate(e=>e.scrollIntoView({block:'start'}));assert.match(await page.locator('#selected-description').textContent(),/failed validation/);}
   else if(s.index===4){await page.locator('#flow-task').selectOption(opts[2]);await page.locator('.instrument').evaluate(e=>e.scrollIntoView({block:'start'}));assert.match(await page.locator('#branch-outcome').textContent(),/fallback/i);}
   else if(s.index===5){await page.locator('#flow-task').selectOption(opts[3]);await page.locator('.review').evaluate(e=>e.scrollIntoView({block:'start'}));assert.match(await page.locator('#decision-summary').textContent(),/before a routing decision/);}
   else {await page.locator('.controls').evaluate(e=>e.scrollIntoView({block:'start'}));}
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.screenshot({path:path.join(destination,`scene-${s.index+1}.png`)});
   const duration=s.end_seconds-s.start_seconds;
   if(s.index===1){
    await page.getByRole('button',{name:'Start',exact:true}).click();await page.locator('#speed').selectOption('0.01');await page.getByRole('button',{name:'Play replay',exact:true}).click();
   }
   await page.waitForTimeout(duration*1000+400);
   assert.deepEqual(errors,[]);
   const video=page.video();await context.close();const raw=await video.path();
   const probe=JSON.parse(execFileSync('ffprobe',['-v','error','-show_entries','format=duration','-of','json',raw]));
   const trim=Math.max(0,Number(probe.format.duration)-duration);
   const clip=path.join(destination,`clip-${s.index+1}.mp4`);
   execFileSync('ffmpeg',['-nostdin','-v','error','-n','-ss',String(trim),'-i',raw,'-t',String(duration),'-an','-vf','fps=25','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p',clip]);
   captures.push({scene:s.index+1,start:s.start_seconds,end:s.end_seconds,source_video_sha256:sha(fs.readFileSync(raw)),clip_sha256:sha(fs.readFileSync(clip))});
   console.log(`Captured scene ${s.index+1}/7 (${duration.toFixed(2)}s)`);
  }finally{await context.close();}
 }
 }finally{await browser.close();}
 const concat=path.join(destination,'clips.txt');fs.writeFileSync(concat,scenes.map(s=>`file 'clip-${s.index+1}.mp4'`).join('\n')+'\n');
 const film=path.join(destination,'discovery-narrated.mp4');
 execFileSync('ffmpeg',['-nostdin','-v','error','-n','-f','concat','-safe','1','-i',concat,'-i',path.join(source,'narration.mp3'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-af','apad,loudnorm=I=-16:TP=-1.5:LRA=11','-c:a','aac','-b:a','192k','-t',String(scenes.at(-1).end_seconds),'-movflags','+faststart',film]);
 const manifest={scope:'public synthetic discovery; ElevenLabs narration',source_hashes:snapshots,audio_sha256:sha(fs.readFileSync(path.join(source,'narration.mp3'))),scenes:captures,film_sha256:sha(fs.readFileSync(film)),routing_provider_calls:0,speech_generation_calls:0};
 fs.writeFileSync(path.join(destination,'capture.json'),JSON.stringify(manifest,null,2)+'\n');console.log(film);
};run().catch(e=>{console.error(e.message);process.exitCode=1;});
