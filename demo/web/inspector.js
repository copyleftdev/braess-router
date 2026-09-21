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
    const m = await response.json();
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
    let current = [], pageIndex = 0;
    const wordText = w => characters.slice(w.start_character,w.end_character).join('');
    function chooseWord() {
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
    function zoom() { $('source-sheet').style.width = $('source-zoom').value === 'native' ? `${m.pages[pageIndex].width}px` : '100%'; }
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
    $('source-page').addEventListener('change',choosePage);
    $('source-word').addEventListener('change',chooseWord);
    $('source-zoom').addEventListener('change',zoom);
    $('source-overlay').addEventListener('click', () => {
      const show = $('source-overlay').getAttribute('aria-pressed') !== 'true';
      $('source-overlay').setAttribute('aria-pressed',String(show));$('source-boxes').style.visibility = show ? 'visible' : 'hidden';
    });
    $('source-content').hidden = false; choosePage();
    $('source-status').textContent = `${m.pages.length} pages · ${words.length} located words · asset hashes verified. Transcription accuracy has not been established.`;
  } catch (_) {
    panel.hidden = false; $('source-content').hidden = true;
    urls.forEach(url => URL.revokeObjectURL(url)); urls=[];
    $('source-status').textContent = 'Source evidence could not be verified. Rebuild the evidence bundle and restart the private server.';
  }
})();
