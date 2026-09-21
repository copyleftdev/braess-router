'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const names = {task_queued:'Queued',request_started:'Request sent',response_received:'Response received',review_validated:'Evidence validated',task_completed:'Completed',task_uncertain:'Uncertain',task_deferred:'Deferred'};
  let bundle, tasks=[], lanes=[], selected, duration=1, clock=0, playing=false, lastFrame=0, raf=0;
  const canvas=$('flow'), ctx=canvas.getContext('2d');
  let width=1,height=1;
  const ms=n=>(n/1e6).toFixed(2)+' ms';
  function visible(task){return task.events.filter(e=>e.elapsed_ns<=clock);}
  function state(task){return visible(task).at(-1)?.kind || 'not_started';}
  function response(task){return visible(task).find(e=>e.kind==='response_received')?.data;}
  function routeOf(task){return state(task)==='task_uncertain'?'uncertain':state(task)==='task_deferred'?null:response(task)?.route;}
  function element(tag,text,className){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(className)e.className=className;return e;}
  function setPlaying(value){
    playing=value;$('play').textContent=value?'Pause replay':'Play replay';
    $('play').setAttribute('aria-pressed',String(value));lastFrame=0;
    if(value){if(clock>=duration)clock=0;raf=requestAnimationFrame(tick);}
    else {cancelAnimationFrame(raf);render();}
  }
  function tick(now){
    if(!playing)return;
    if(lastFrame)clock=Math.min(duration,clock+(now-lastFrame)*1e6*Number($('speed').value));
    lastFrame=now;render();
    if(clock>=duration){setPlaying(false);$('status').textContent='End of recording. Uncertain outcomes remain unresolved.';}
    else raf=requestAnimationFrame(tick);
  }
  function resize(){
    const box=canvas.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2);
    width=box.width;height=box.height;canvas.width=width*dpr;canvas.height=height*dpr;
    ctx.setTransform(dpr,0,0,dpr,0,0);draw();
  }
  function draw(){
    ctx.clearRect(0,0,width,height);
    if(!bundle)return;
    const cx=width*.43,cy=height*.47,r=width<500?43:70,end=width*(width<500?.71:.79);
    ctx.strokeStyle='#303030';ctx.lineWidth=1;
    function path(y){ctx.beginPath();ctx.moveTo(cx,cy);ctx.bezierCurveTo(cx+width*.17,cy,end-width*.1,y,end,y);ctx.stroke();}
    lanes.forEach((lane,i)=>{const y=height*(.12+i*.76/Math.max(1,lanes.length-1));path(y);ctx.beginPath();ctx.arc(end,y,3,0,Math.PI*2);ctx.stroke();});
    tasks.forEach((task,i)=>{
      const events=visible(task);if(!events.length)return;
      const y=height*(.19+i*.62/Math.max(1,tasks.length-1));
      ctx.strokeStyle=task.id===selected?'#777':'#242424';
      ctx.beginPath();ctx.moveTo(width*.10,y);ctx.bezierCurveTo(width*.24,y,cx-width*.12,cy,cx,cy);ctx.stroke();
      const route=routeOf(task),target=lanes.indexOf(route),started=events.find(e=>e.kind==='request_started');
      let x=width*.10,py=y;
      if(target>=0){x=end;py=height*(.12+target*.76/Math.max(1,lanes.length-1))+(i%3-1)*8;if(task.id===selected){ctx.strokeStyle='#aaa';path(py);}}
      else if(started){const completed=task.events.find(e=>e.kind==='response_received'||e.kind==='task_uncertain');const stop=completed?.elapsed_ns||duration;const t=Math.min(1,Math.max(0,(clock-started.elapsed_ns)/Math.max(1,stop-started.elapsed_ns)));x=width*.10+(cx-width*.10)*t;py=y+(cy-y)*t;}
      ctx.strokeStyle='#f5f5f2';ctx.fillStyle=task.id===selected?'#fff':'#bbb';ctx.beginPath();
      if(state(task)==='task_uncertain'){ctx.moveTo(x,py-5);ctx.lineTo(x+5,py);ctx.lineTo(x,py+5);ctx.lineTo(x-5,py);ctx.closePath();ctx.stroke();}
      else if(state(task)==='task_deferred'){ctx.rect(x-4,py-4,8,8);ctx.stroke();}
      else{ctx.arc(x,py,task.id===selected?4:2.5,0,Math.PI*2);ctx.fill();}
    });
    ctx.fillStyle='#080808';ctx.strokeStyle='#555';ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.fill();ctx.stroke();
    ctx.strokeStyle='#272727';ctx.beginPath();ctx.arc(cx,cy,r+6,0,Math.PI*2);ctx.stroke();
    for(let i=0;i<36;i++){const a=i*Math.PI/18;ctx.beginPath();ctx.moveTo(cx+Math.cos(a)*(r+12),cy+Math.sin(a)*(r+12));ctx.lineTo(cx+Math.cos(a)*(r+15),cy+Math.sin(a)*(r+15));ctx.stroke();}
  }
  function render(){
    if(!bundle)return;
    $('seek').value=String(Math.round(clock/duration*1000));$('time').textContent=ms(clock)+' / '+ms(duration);
    let completed=0,uncertain=0,pending=0,deferred=0;
    for(const task of tasks){
      const s=state(task),r=response(task),button=task.button;
      button.dataset.state=s;button.setAttribute('aria-pressed',String(task.id===selected));
      button.querySelector('small').textContent=(r?.route||(s==='task_deferred'?'Not dispatched':s==='task_uncertain'?'No route reported':'Awaiting route'))+' · '+(names[s]||'Not started');
      button.querySelector('.row-time').textContent=r?Number(r.elapsed_ms).toFixed(2)+' ms':'—';
      if(s==='task_completed')completed++;else if(s==='task_uncertain')uncertain++;else if(s==='task_deferred')deferred++;else if(s!=='not_started')pending++;
    }
    $('completed').textContent=completed;$('uncertain').textContent=uncertain;$('pending').textContent=pending;$('deferred').textContent=deferred;
    $('event-count').textContent=bundle.events.filter(e=>e.elapsed_ns<=clock).length+' / '+bundle.events.length+' events';
    inspect();draw();
  }
  function inspect(){
    const task=tasks.find(t=>t.id===selected);if(!task)return;
    const events=visible(task),r=response(task),s=state(task);
    const validation=events.find(e=>e.kind==='review_validated')?.data;
    const reservation=events.find(e=>e.kind==='request_started')?.data;
    const failure=events.find(e=>e.kind==='task_uncertain')?.data.error;
    $('selected-title').textContent=task.document;
    $('selected-state').textContent=names[s]||'Not started';
    $('selected-description').textContent=s==='task_deferred'?'The budget gate refused admission before dispatch. No provider request was made for this task.':failure==='review_validation_failed'?'A reviewer result returned, but its evidence failed validation. No finding was accepted; this task remains uncertain.':s==='task_uncertain'?'Completion was not confirmed. This task is retained as uncertain.':validation?'The finding’s quote and coordinates matched the source. This verifies the evidence link, not legal correctness.':r?.route==='fallback'?'Braess returned a local fallback. No handler completion is implied.':s==='task_completed'?'The gateway returned a handler result. This fixture does not measure legal-review accuracy.':'Only events up to the replay clock are shown.';
    const facts=[['Route',r?.route||'Not observed'],['Decision model',r?.decision_model||'Not reported'],['Policy',r?.policy_version||'Not reported'],['Handler index',r?.handler_index??'Not reported'],['Client duration',r?Number(r.elapsed_ms).toFixed(2)+' ms':'Not yet observed'],['Decision tokens',r?.decision_input_tokens!==undefined?r.decision_input_tokens+' in / '+(r.decision_output_tokens??'unknown')+' out':'Not reported'],['Generation model',r?.generation_model||'Not reported'],['Generation cost',r?.generation_cost_usd!==undefined?'$'+r.generation_cost_usd:'Not reported']];
    facts.push(['Source modality',events.find(e=>e.kind==='task_queued')?.data.modality||'Not observed'],
      ['Validated findings',validation?.finding_count??'None accepted yet'],
      ['Admission reservation',reservation?.budget_reserved_usd!==undefined?'$'+reservation.budget_reserved_usd+' (estimate)':'Not reserved'],
      ['Generation provider',r?.generation_provider||'Not reported'],
      ['Generation tokens',r?.generation_input_tokens!==undefined?r.generation_input_tokens+' in / '+(r.generation_output_tokens??'unknown')+' out':'Not reported'],
      ['Cost scope','Synthetic receipt; total cost unknown']);
    $('facts').replaceChildren(...facts.flatMap(([k,v])=>[element('dt',k),element('dd',String(v))]));
    $('sequence').replaceChildren(...events.map(e=>{const li=element('li');li.append(element('span',names[e.kind]),element('time',ms(e.elapsed_ns)));return li;}));
    $('provenance').textContent='Run '+bundle.run.run_id+' · Source '+task.id+' · Last visible event SHA-256 '+(events.at(-1)?.sha256||'not observed')+(validation?' · Validated review SHA-256 '+validation.review_sha256:'')+(reservation?.budget_attempt_id?' · Budget attempt '+reservation.budget_attempt_id:'');
  }
  function check(data){
    if(data?.run?.schema_version!==1||data.run.scope!=='synthetic'||data.sealed!==true||!Array.isArray(data.events)||!data.events.length||data.events.length>100000)throw Error('Unsupported recording');
    let last=-1;const ids=new Set();
    data.events.forEach((e,i)=>{if(!names[e.kind]||e.seq!==i+1||!Number.isSafeInteger(e.elapsed_ns)||e.elapsed_ns<last||typeof e.task_id!=='string'||!e.data||typeof e.data!=='object')throw Error('Invalid event sequence');last=e.elapsed_ns;ids.add(e.task_id);});
    if(ids.size>200)throw Error('This preview supports at most 200 tasks');
    return data;
  }
  async function load(){
    try{
      const result=await fetch('replay.json');if(!result.ok)throw Error('Recording unavailable');
      const body=await result.text();if(body.length>32*1024*1024)throw Error('Recording too large');
      bundle=check(JSON.parse(body));duration=Math.max(1,bundle.events.at(-1).elapsed_ns);clock=duration;
      for(const e of bundle.events){let task=tasks.find(t=>t.id===e.task_id);if(!task){task={id:e.task_id,document:e.data.document_id||e.task_id,events:[]};tasks.push(task);}task.events.push(e);}
      lanes=[...new Set(bundle.events.filter(e=>e.kind==='response_received'&&e.data.route).map(e=>e.data.route))];
      if(bundle.events.some(e=>e.kind==='task_uncertain'))lanes.push('uncertain');
      $('lanes').replaceChildren(...lanes.map((name,i)=>{const label=element('div',name==='uncertain'?'Uncertain':name[0].toUpperCase()+name.slice(1),'lane');label.style.top=(12+i*76/Math.max(1,lanes.length-1))+'%';label.append(element('span',name==='uncertain'?'Not confirmed':name==='fallback'?'Local response':'Returned route'));return label;}));
      for(const task of tasks){const button=element('button',undefined,'task-row');button.type='button';button.append(element('span',undefined,'signal'));const label=element('span',task.document);label.append(element('small',''));button.append(label,element('span','—','row-time'));button.addEventListener('click',()=>{selected=task.id;render();});task.button=button;$('tasks').append(button);}
      selected=tasks[0].id;
      $('scope').textContent=bundle.presentation.description;$('scope-label').textContent='Recorded execution / synthetic providers';
      $('run-id').textContent=bundle.run.run_id.slice(0,8)+' · '+new Date(bundle.run.created_at).toISOString().slice(0,10);
      $('task-total').textContent=tasks.length+' recorded fixtures';
      $('status').textContent='Paused at the end of the run. Play or scrub to inspect the observed sequence.';
      for(const id of ['play','reset','seek'])$(id).disabled=false;
      $('play').setAttribute('aria-pressed','false');render();resize();
    }catch(error){$('scope-label').textContent='Recording unavailable';$('scope').textContent='The recording could not be loaded.';$('status').textContent='Unable to load a supported recording. Restore replay.json from the verified exporter and reload.';}
  }
  $('play').addEventListener('click',()=>setPlaying(!playing));
  $('reset').addEventListener('click',()=>{setPlaying(false);clock=0;render();$('status').textContent='At the start. No task events have occurred.';});
  $('seek').addEventListener('input',()=>{const position=Number($('seek').value);setPlaying(false);clock=duration*position/1000;render();$('status').textContent='Paused at '+ms(clock)+'.';});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)setPlaying(false);});
  new ResizeObserver(resize).observe(canvas);load();
})();
