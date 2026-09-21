'use strict';
(() => {
  const data = window.BRAESS_TRAFFIC;
  const canvas = document.getElementById('traffic');
  const ctx = canvas.getContext('2d');
  const instrument = document.querySelector('.instrument');
  const play = document.getElementById('play-toggle');
  const tabs = [...document.querySelectorAll('[data-phase]')];
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const stories = [
    'Room to move. Accepted requests find their route; uncertain decisions return locally.',
    'Demand rises. Admission rejects excess work before dispatch, keeping the boundary intact.',
    'Pressure recedes. Accepted traffic resumes as concurrency returns to its starting level.'
  ];
  let phase = 0, paused = reduced.matches, visible = true, time = 8, previous = 0, frame = 0;
  let width = 0, height = 0, particles = [], serial = 0, nextSpawn = 0;
  const routeY = {general: .2, coding: .4, reasoning: .6};
  const hash = n => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
  const point = (x,y) => ({x:x*width,y:y*height});
  function curve(a,b,c,d,t) {
    const k=1-t; return {x:k*k*k*a.x+3*k*k*t*b.x+3*k*t*t*c.x+t*t*t*d.x,y:k*k*k*a.y+3*k*k*t*b.y+3*k*t*t*c.y+t*t*t*d.y};
  }
  function track(a,b,c,d,alpha=.15,dash=[]) {
    ctx.beginPath(); ctx.moveTo(a.x,a.y);ctx.bezierCurveTo(b.x,b.y,c.x,c.y,d.x,d.y);
    ctx.strokeStyle=`rgba(235,235,235,${alpha})`;ctx.lineWidth=.65;ctx.setLineDash(dash);ctx.stroke();ctx.setLineDash([]);
  }
  function trajectory(p,u) {
    const y=.16+hash(p.id)*.48;
    if(p.outcome==='rejected')return curve(point(-.02,y),point(.31,y),point(.29,.72),point(.15,.78),u);
    if(u<.48) return curve(point(-.02,y),point(.2,y),point(.27,.4),point(.44,.4),u/.48);
    if(p.outcome==='fallback')return curve(point(.44,.4),point(.44,.72),point(.48,.79),point(.61,.79),(u-.48)/.52);
    const dy=routeY[p.outcome]??.4;
    return curve(point(.44,.4),point(.59,.4),point(.62,dy),point(.8,dy),(u-.48)/.52);
  }
  function shape(x,y,kind,size,alpha) {
    ctx.save();ctx.translate(x,y);ctx.strokeStyle=`rgba(245,245,242,${alpha})`;ctx.fillStyle=ctx.strokeStyle;ctx.lineWidth=1;
    ctx.beginPath();
    if(kind==='coding')ctx.rect(-size,-size,size*2,size*2);
    else if(kind==='reasoning'){ctx.moveTo(0,-size*1.4);ctx.lineTo(size*1.2,size);ctx.lineTo(-size*1.2,size);ctx.closePath();}
    else if(kind==='rejected'){ctx.moveTo(-size,-size);ctx.lineTo(size,size);ctx.moveTo(size,-size);ctx.lineTo(-size,size);}
    else ctx.arc(0,0,size,0,Math.PI*2);
    if(kind==='fallback'||kind==='rejected')ctx.stroke();else ctx.fill();ctx.restore();
  }
  function spawn(at) {
    const samples=data.phases[phase].samples;
    const item=samples[serial%samples.length];
    particles.push({id:serial++,start:at,outcome:item.outcome,duration:item.outcome==='rejected'?2.6:5.4});
  }
  function reset() {
    particles=[];serial=0;nextSpawn=0;time=8;
    const gap=phase===1?.075:.19;
    for(let t=0;t<8;t+=gap)spawn(t);
    nextSpawn=8;draw();
  }
  function draw() {
    if(!ctx||!width)return;
    ctx.clearRect(0,0,width,height);
    const center=point(.44,.4), r= Math.min(width*(width<600?.115:.085),height*.215);
    for(let i=0;i<13;i++) {
      const y=.16+i*.04;
      track(point(0,y),point(.22,y),point(.27,.4),center,.10);
    }
    for(const [name,y] of Object.entries(routeY)){
      track(center,point(.59,.4),point(.62,y),point(.8,y),.28);
      const ep=point(.8,y);ctx.beginPath();ctx.arc(ep.x,ep.y,4,0,Math.PI*2);ctx.strokeStyle='#a4a4a4';ctx.lineWidth=1;ctx.stroke();
      // Pool stubs express endpoint selection, not measured per-endpoint traffic.
      track(point(.73,y),point(.76,y),point(.76,y+.055),point(.8,y+.055),.16,[2,4]);
      ctx.beginPath();ctx.arc(width*.8,height*(y+.055),2.5,0,Math.PI*2);ctx.strokeStyle='#555';ctx.stroke();
    }
    track(center,point(.44,.72),point(.48,.79),point(.61,.79),.2,[3,5]);
    if(phase===1)track(point(.15,.35),point(.3,.42),point(.29,.72),point(.15,.78),.18,[2,5]);
    particles=particles.filter(p=>time-p.start<p.duration);
    for(const p of particles){
      const u=(time-p.start)/p.duration;if(u<0||u>1)continue;
      const pos=trajectory(p,u), fade=Math.min(1,u*12,(1-u)*12);
      for(let j=5;j>=1;j--){const q=trajectory(p,Math.max(0,u-j*.006));shape(q.x,q.y,p.outcome,width<600?1:1.5,fade*(.12-j*.016));}
      shape(pos.x,pos.y,p.outcome,width<600?1.7:2.25,fade*.95);
    }
    // The aperture masks the path intersection, marking the decision boundary.
    ctx.beginPath();ctx.arc(center.x,center.y,r,0,Math.PI*2);ctx.fillStyle='#080808';ctx.fill();ctx.strokeStyle='#626262';ctx.lineWidth=.8;ctx.stroke();
    ctx.beginPath();ctx.arc(center.x,center.y,r+6,0,Math.PI*2);ctx.strokeStyle='#262626';ctx.stroke();
    for(let i=0;i<40;i++){const a=i/40*Math.PI*2;const len=i%5===0?6:2;ctx.beginPath();ctx.moveTo(center.x+Math.cos(a)*(r+12),center.y+Math.sin(a)*(r+12));ctx.lineTo(center.x+Math.cos(a)*(r+12+len),center.y+Math.sin(a)*(r+12+len));ctx.strokeStyle=i%5===0?'#6b6b6b':'#353535';ctx.stroke();}
    // A single orbit shares the traffic clock; it freezes with the replay.
    const a=time*.24;ctx.beginPath();ctx.arc(center.x,center.y,r+6,a,a+.24);ctx.strokeStyle='#ddd';ctx.lineWidth=1.3;ctx.stroke();
  }
  function tick(now){
    frame=0;
    if(paused||!visible||document.hidden){previous=0;return;}
    if(previous)time+=Math.min((now-previous)/1000,.06);previous=now;
    const gap=phase===1?.075:.19;
    while(nextSpawn<time){spawn(nextSpawn);nextSpawn+=gap;}
    draw();frame=requestAnimationFrame(tick);
  }
  function schedule(){if(frame)cancelAnimationFrame(frame);frame=0;previous=0;if(!paused&&visible&&!document.hidden)frame=requestAnimationFrame(tick);}
  function syncPlay(){
    play.setAttribute('aria-label',paused?'Play animation':'Pause animation');
    play.querySelector('span').textContent=paused?'Play':'Pause';
    play.querySelector('path').setAttribute('d',paused?'M6 4 15 10 6 16Z':'M7 5v10M13 5v10');
    instrument.dataset.playing=String(!paused);
  }
  function select(index){
    phase=index;
    tabs.forEach((t,i)=>t.setAttribute('aria-pressed',String(i===phase)));
    instrument.classList.toggle('pressure',phase===1);
    const p=data.phases[phase], out=p.outcomes;
    document.getElementById('phase-story').textContent=stories[phase];
    document.getElementById('phase-time').textContent=p.duration_seconds.toFixed(2)+'s captured';
    document.getElementById('count-routed').textContent=((out.general||0)+(out.coding||0)+(out.reasoning||0)).toLocaleString('en-US');
    document.getElementById('count-fallback').textContent=(out.fallback||0).toLocaleString('en-US');
    document.getElementById('count-rejected').textContent=(out.rejected||0).toLocaleString('en-US');
    reset();
  }
  tabs.forEach(t=>t.addEventListener('click',()=>select(Number(t.dataset.phase))));
  play.addEventListener('click',()=>{paused=!paused;syncPlay();schedule();});
  reduced.addEventListener('change',()=>{paused=reduced.matches;syncPlay();draw();schedule();});
  document.addEventListener('visibilitychange',schedule);
  new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;schedule();},{threshold:0}).observe(canvas);
  new ResizeObserver(()=>{
    width=canvas.clientWidth;height=canvas.clientHeight;const dpr=Math.min(devicePixelRatio||1,2);
    canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);draw();
  }).observe(canvas);
  select(0);syncPlay();schedule();
})();
