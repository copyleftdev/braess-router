'use strict';
(async () => {
  const $ = id => document.getElementById(id);
  const panel = $('source-inspector');
  let urls = [];
  const digest = async bytes => [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(x => x.toString(16).padStart(2, '0')).join('');
  try {
    const response = await fetch('/evidence/manifest.json');
    if (response.status === 404) return;
    panel.hidden = false;
    if (!response.ok) throw Error('manifest');
    const manifestBytes=await response.arrayBuffer();
    const manifestSha256=await digest(manifestBytes);
    const m=JSON.parse(new TextDecoder().decode(manifestBytes));
    if (m.schema_version !== 1 || !m.complete || m.publication_approved !== false || m.coordinate_unit !== 'source_page_pixels' || !Array.isArray(m.pages) || m.pages.length < 1 || m.pages.length > 32) throw Error('manifest');
    const asset = async (entry, name) => {
      if (entry.file !== name || !/^[a-f0-9]{64}$/.test(entry.sha256)) throw Error('asset');
      const r = await fetch('/evidence/' + name);
      if (!r.ok) throw Error('asset');
      const bytes = await r.arrayBuffer();
      if (await digest(bytes) !== entry.sha256) throw Error('hash');
      return bytes;
    };
    const text = new TextDecoder('utf-8', {fatal:true}).decode(await asset(m.text, 'text.txt'));
    const words = JSON.parse(new TextDecoder().decode(await asset(m.words, 'words.json')));
    // Python offsets are Unicode code points, not JavaScript UTF-16 code units.
    const characters = Array.from(text);
    if (!Array.isArray(words) || words.length > 100000 || words.length !== m.words.count) throw Error('words');
    let end = -1;
    for (const w of words) {
      const p = m.pages[w.page - 1];
      if (!p || !Number.isInteger(w.page) || !Number.isInteger(w.start_character) || !Number.isInteger(w.end_character) || w.start_character !== end + 1 || w.end_character <= w.start_character || w.end_character > characters.length || (end >= 0 && characters[end] !== ' ') || !Array.isArray(w.box) || w.box.length !== 4 || !w.box.every(n => Number.isInteger(n) && n >= 0) || w.box[0]+w.box[2]>p.width || w.box[1]+w.box[3]>p.height || !Number.isFinite(w.confidence) || w.confidence<0 || w.confidence>100) throw Error('word geometry');
      end = w.end_character;
    }
    if ((words.length && end !== characters.length) || (!words.length && characters.length)) throw Error('text coverage');
    for (const [i,p] of m.pages.entries()) {
      if (p.page !== i+1 || !Number.isInteger(p.width) || !Number.isInteger(p.height) || p.width<=0 || p.height<=0 || p.width*p.height>16000000) throw Error('page');
      const bytes = await asset(p, `page-${i+1}.png`);
      const url = URL.createObjectURL(new Blob([bytes], {type:'image/png'})); urls.push(url);
      const image = new Image(); image.src = url; await image.decode();
      if (image.naturalWidth !== p.width || image.naturalHeight !== p.height) throw Error('decoded geometry');
      $('source-page').add(new Option(`${i+1} of ${m.pages.length}`, String(i)));
    }
    const sourceImage = document.createElement('img'); sourceImage.id = 'source-image';
    $('source-image-slot').replaceWith(sourceImage);
    let current = [], pageIndex = 0, selection=null, replay=null;
    const selectionNote=$('source-selection');
    function clearFinding(){
      selection=null; selectionNote.hidden=true;
      document.querySelectorAll('.finding-box').forEach(node=>node.remove());
      $('source-context').textContent='Private OCR inspection. No finding-to-task association is selected.';
    }
    const wordText = w => characters.slice(w.start_character,w.end_character).join('');
    function chooseWord() {
      clearFinding();
      const selected = current[Number($('source-word').value)];
      $('source-box').style.display = selected ? '' : 'none';
      $('source-transcript').replaceChildren();
      for (const w of current) {
        const span = document.createElement(w === selected ? 'mark' : 'span');
        span.textContent = wordText(w);
        $('source-transcript').append(span, document.createTextNode(' '));
      }
      if (selected) {
        ['x','y','width','height'].forEach((k,i) => $('source-box').setAttribute(k, selected.box[i]));
        $('source-word-detail').textContent = `OCR confidence ${selected.confidence.toFixed(1)} / 100 · source pixels ${selected.box.join(', ')}`;
        const mark = $('source-transcript').querySelector('mark');
        const transcript = $('source-transcript');
        transcript.scrollTop += mark.getBoundingClientRect().top - transcript.getBoundingClientRect().top - 40;
        const viewport = document.querySelector('.source-viewport');
        const scale = $('source-sheet').clientWidth / m.pages[pageIndex].width;
        viewport.scrollTo({left:Math.max(0, (selected.box[0]+selected.box[2]/2)*scale-viewport.clientWidth/2), top:Math.max(0, (selected.box[1]+selected.box[3]/2)*scale-viewport.clientHeight/2)});
      } else {
        $('source-word-detail').textContent = 'No recognized words on this page.';
      }
    }
    function zoom() {
      $('source-sheet').style.width = $('source-zoom').value === 'native' ? `${m.pages[pageIndex].width}px` : '100%';
      const box=document.querySelector('.finding-box');
      if(box){const viewport=document.querySelector('.source-viewport'),scale=$('source-sheet').clientWidth/m.pages[pageIndex].width;
        viewport.scrollTo({left:Math.max(0,Number(box.getAttribute('x'))*scale-viewport.clientWidth/2),top:Math.max(0,Number(box.getAttribute('y'))*scale-viewport.clientHeight/3)});}
    }
    function choosePage() {
      pageIndex = Number($('source-page').value);
      const p = m.pages[pageIndex];
      $('source-image').src = urls[pageIndex];
      $('source-image').alt = `Original document scan, page ${pageIndex+1}. OCR transcript is alongside.`;
      $('source-boxes').setAttribute('viewBox', `0 0 ${p.width} ${p.height}`);
      $('source-dimensions').textContent = `${p.width} × ${p.height} source pixels`;
      current = words.filter(w => w.page === pageIndex+1);
      $('source-word').replaceChildren();
      current.forEach((w,i) => $('source-word').add(new Option(`${i+1}. ${wordText(w)}`, String(i))));
      $('source-word').disabled = current.length === 0;
      chooseWord(); zoom();
      document.querySelector('.source-viewport').scrollTo(0,0);
    }
    for (const [label,value] of [['Document',m.document_id],['Native source SHA-256',m.native_source_sha256],['OCR text SHA-256',m.source_sha256],['OCR mapping SHA-256',m.ocr_mapping_sha256],['Decoder',`${m.decoder.name} ${m.decoder.version}`]]) {
      const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;$('source-provenance').append(dt,dd);
    }
    function resetFinding(){if(selection){clearFinding();chooseWord();}}
    function setReplay(context){
      replay=context;
      if(selection && (context.run_id!==selection.run_id || context.task_id!==selection.task_id || context.review_sha256!==selection.review_sha256 || context.elapsed_ns<selection.visible_after))resetFinding();
    }
    function show(association,finding,page){
      if(!replay || replay.run_id!==association.run_id || replay.task_id!==association.task_id || replay.review_sha256!==association.review_sha256 || replay.elapsed_ns<association.finding_visibility_after_elapsed_ns || association.inspector_manifest_sha256!==manifestSha256 || association.document_id!==m.document_id || association.source_sha256!==m.source_sha256 || association.native_source_sha256!==m.native_source_sha256 || association.ocr_mapping_sha256!==m.ocr_mapping_sha256 || !Number.isInteger(page) || !m.pages[page-1])return false;
      if(!Number.isInteger(finding.start)||!Number.isInteger(finding.end)||finding.start<0||finding.end<=finding.start||finding.end>characters.length||characters.slice(finding.start,finding.end).join('')!==finding.quote)return false;
      const matched=words.filter(w=>w.start_character<finding.end&&w.end_character>finding.start),regions=finding.location?.image_regions;
      if(!Array.isArray(regions)||regions.length!==matched.length||regions.some((r,i)=>r.page!==matched[i].page||r.start_character!==matched[i].start_character||r.end_character!==matched[i].end_character||r.ocr_confidence!==matched[i].confidence||JSON.stringify(r.box)!==JSON.stringify(matched[i].box)))return false;
      const onPage=matched.filter(w=>w.page===page);if(!onPage.length)return false;
      $('source-page').value=String(page-1);choosePage();
      selection={run_id:association.run_id,task_id:association.task_id,review_sha256:association.review_sha256,visible_after:association.finding_visibility_after_elapsed_ns};
      $('source-box').style.display='none';$('source-boxes').style.visibility='visible';$('source-overlay').setAttribute('aria-pressed','true');
      for(const w of onPage){
        const box=document.createElementNS('http://www.w3.org/2000/svg','rect');box.classList.add('finding-box');
        ['x','y','width','height'].forEach((key,i)=>box.setAttribute(key,w.box[i]));$('source-boxes').append(box);
      }
      $('source-transcript').replaceChildren();
      for(const w of current){
        // Partial-word findings highlight only quoted characters in text; image
        // boxes retain OCR word granularity and are labeled as such.
        const start=Math.max(w.start_character,finding.start),end=Math.min(w.end_character,finding.end);
        if(start<end){
          const before=characters.slice(w.start_character,start).join(''),after=characters.slice(end,w.end_character).join('');
          const mark=document.createElement('mark');mark.textContent=characters.slice(start,end).join('');
          $('source-transcript').append(before,mark,after,' ');
        }else $('source-transcript').append(wordText(w),' ');
      }
      $('source-word').value=String(current.indexOf(onPage[0]));
      $('source-word-detail').textContent=`${onPage.length} OCR word boxes on this page. Image locations use whole-word geometry.`;
      $('source-context').textContent=`Linked to selected task ${association.document_id}. ${association.scope==='synthetic'?'Synthetic reviewer finding.':'Provisional reviewer finding.'}`;
      selectionNote.textContent=`Finding ${finding.id} · page ${page} · source characters ${finding.start}–${finding.end}. Not a redaction.`;selectionNote.hidden=false;
      panel.scrollIntoView({block:'start',behavior:'instant'});
      $('source-page').focus({preventScroll:true});
      const viewport=document.querySelector('.source-viewport'),scale=$('source-sheet').clientWidth/m.pages[page-1].width;
      viewport.scrollTo({left:Math.max(0,onPage[0].box[0]*scale-viewport.clientWidth/2),top:Math.max(0,onPage[0].box[1]*scale-viewport.clientHeight/3)});
      const mark=$('source-transcript').querySelector('mark'),transcript=$('source-transcript');
      transcript.scrollTop+=mark.getBoundingClientRect().top-transcript.getBoundingClientRect().top-40;
      return true;
    }
    window.braessSource=Object.freeze({manifestSha256,setReplay,show});
    $('source-page').addEventListener('change',choosePage);
    $('source-word').addEventListener('change',chooseWord);
    $('source-zoom').addEventListener('change',zoom);
    $('source-overlay').addEventListener('click', () => {
      const show = $('source-overlay').getAttribute('aria-pressed') !== 'true';
      $('source-overlay').setAttribute('aria-pressed',String(show));$('source-boxes').style.visibility = show ? 'visible' : 'hidden';
    });
    $('source-content').hidden = false; choosePage();
    window.dispatchEvent(new Event('braess-source-ready'));
    $('source-status').textContent = `${m.pages.length} pages · ${words.length} located words · asset hashes verified. Transcription accuracy has not been established.`;
  } catch (_) {
    panel.hidden = false; $('source-content').hidden = true;
    urls.forEach(url => URL.revokeObjectURL(url)); urls=[];
    $('source-status').textContent = 'Source evidence could not be verified. Rebuild the evidence bundle and restart the private server.';
  }
})();
