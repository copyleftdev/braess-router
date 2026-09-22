#!/usr/bin/env python3
"""Local TIFF/image OCR with character-to-page-box mapping; no model calls."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from corpus import private_write


def parse_tsv(wire, expected_pages):
    if len(wire)>16*1024*1024:raise ValueError('OCR output too large')
    rows=list(csv.DictReader(io.StringIO(wire.decode('utf-8')),delimiter='\t',quoting=csv.QUOTE_NONE))
    pages={}
    for row in rows:
        if row['level']=='1':
            page=int(row['page_num']);width=int(row['width']);height=int(row['height'])
            if page in pages or width<=0 or height<=0:raise ValueError('invalid page geometry')
            pages[page]={'width':width,'height':height}
    if set(pages)!=set(range(1,expected_pages+1)):raise ValueError('OCR page coverage mismatch')
    words=[];pieces=[];offset=0
    for row in rows:
        if row['level']!='5' or not row.get('text','').strip():continue
        text=row['text'];page=int(row['page_num']);x,y,w,h=[int(row[k]) for k in ('left','top','width','height')]
        if page not in pages or min(x,y,w,h)<0 or x+w>pages[page]['width'] or y+h>pages[page]['height']:
            raise ValueError('word outside page')
        confidence=float(row['conf'])
        if not 0<=confidence<=100:raise ValueError('invalid OCR confidence')
        if pieces:pieces.append(' ');offset+=1
        start=offset;pieces.append(text);offset+=len(text)
        words.append({'start_character':start,'end_character':offset,'page':page,
                      'box':[x,y,w,h],'confidence':confidence})
    return ''.join(pieces),{'pages':pages,'words':words,'normalization':'ocr-tsv-word-join-v1'}


def extract(source, output, *, expected_sha256, expected_pages):
    source,output=Path(source),Path(output)
    if type(expected_pages) is not int or not 1<=expected_pages<=32:raise ValueError('invalid page bound')
    if source.is_symlink() or source.stat().st_size>8*1024*1024 or hashlib.sha256(source.read_bytes()).hexdigest()!=expected_sha256:
        raise ValueError('source image mismatch')
    executable=shutil.which('tesseract')
    if executable is None:raise ValueError('Tesseract is required')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    prefix=output/'ocr'
    env={k:v for k,v in os.environ.items() if k not in ('OPENROUTER_API_KEY','TYPESAFE_API_KEY','API_KEY')}
    env['OMP_THREAD_LIMIT']='1'
    command=[sys.executable,str(Path(__file__).resolve()),'--worker',executable,str(source.resolve()),str(prefix.resolve())]
    result=subprocess.run(command,env=env,capture_output=True,timeout=45)
    if result.returncode!=0:raise ValueError('OCR failed or exceeded resource limits')
    tsv=prefix.with_suffix('.tsv')
    if tsv.stat().st_size>16*1024*1024:raise ValueError('OCR output limit')
    wire=tsv.read_bytes();text,mapping=parse_tsv(wire,expected_pages)
    version=subprocess.run([executable,'--version'],capture_output=True,text=True,timeout=3).stdout.splitlines()[0]
    private_write(output/'text.txt',text.encode())
    report={'schema_version':1,'source_sha256':expected_sha256,'text_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'tsv_sha256':hashlib.sha256(wire).hexdigest(),'engine':version,'language':'eng','page_segmentation_mode':3,
            'semantic_review_performed':False,'provider_calls':0,'empty_pages':[p for p in mapping['pages'] if not any(w['page']==p for w in mapping['words'])],**mapping}
    private_write(output/'mapping.json',json.dumps(report,indent=2).encode()+b'\n')
    return report


if __name__=='__main__':
    if len(sys.argv)==5 and sys.argv[1]=='--worker':
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024))
        resource.setrlimit(resource.RLIMIT_CPU,(30,30))
        resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024*1024,16*1024*1024))
        os.umask(0o077)
        os.execv(sys.argv[2],[sys.argv[2],sys.argv[3],sys.argv[4],'-l','eng','--psm','3','tsv'])
    else:
        p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('--sha256',required=True);p.add_argument('--pages',required=True,type=int)
        a=p.parse_args();r=extract(a.source,a.output,expected_sha256=a.sha256,expected_pages=a.pages)
        print(json.dumps({'pages':len(r['pages']),'words':len(r['words']),'empty_pages':r['empty_pages'],'provider_calls':0}))
