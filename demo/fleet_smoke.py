#!/usr/bin/env python3
"""Actual Braess + OpenRouter adapter + local fixtures + validated review artifacts."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from gateway_e2e import Fixtures, ROOT
from budget import Budget
from corpus import private_write
from prepare_review import prepare
from recording import canonical, digest
from fleet import run


def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));return s.getsockname()[1]


def smoke(output,binary):
    output.mkdir(parents=True,exist_ok=False)
    corpus=output/'corpus';(corpus/'objects').mkdir(parents=True)
    documents=[]
    for index,text in enumerate(['A meeting is planned.','An unreliable meeting note.','A third meeting.']):
        sha=digest(text.encode());private_write(corpus/'objects'/(sha+'.txt'),text.encode())
        documents.append({'document_id':f'3.{index}.A','family_id':f'3.{index}.A','source_sha256':sha})
    private_write(corpus/'manifest.json',canonical({'complete':True,'documents':documents}))
    private_write(output/'protocol.json',canonical({'id':'synthetic-meetings','version':'1','scope':'synthetic_protocol','production_request':'Identify mentions of a meeting.'}))
    prepare(corpus,output/'protocol.json',output/'prepared')
    requests=[]
    class Generation(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append({'authorization_present':'Authorization' in self.headers,'model':value['model'],'provider':value['provider']})
            source=json.loads(value['messages'][0]['content']);text=source['evidence_text'];start=text.index('meeting')
            report={'schema_version':1,'document_id':source['document_id'],'source_sha256':source['source_sha256'],
                    'responsiveness':'responsive','findings':[{'id':'issue1','kind':'issue_highlight','start':start,'end':start+7,
                    'quote':'fabricated' if 'unreliable' in text else 'meeting','note':'Synthetic fixture evidence.'}]}
            result={'id':'gen-fixture-'+str(len(requests)),'object':'chat.completion','model':value['model'],'provider':'Fixture',
                    'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(report)}}],
                    'usage':{'prompt_tokens':10,'completion_tokens':10,'total_tokens':20,'cost':0.000001}}
            wire=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Length',str(len(wire)))
            self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(wire)
    server=ThreadingHTTPServer(('127.0.0.1',0),Generation)
    thread=threading.Thread(target=server.serve_forever);thread.start()
    jev=Fixtures();processes=[];logs=[]
    env={k:v for k,v in os.environ.items() if k not in ('API_KEY','TYPESAFE_API_KEY','OPENROUTER_API_KEY')}
    def start(executable,path):
        log=(output/(path.stem+'.log')).open('w');logs.append(log)
        p=subprocess.Popen([str(executable),'--config',str(path)],env=env,stdout=log,stderr=log);processes.append(p)
        url='http://'+json.loads(path.read_text())['bind']
        for _ in range(150):
            if p.poll() is not None:raise RuntimeError('service exited')
            try:
                urllib.request.urlopen(url+'/health',timeout=.2).close();return url
            except OSError:time.sleep(.02)
        raise RuntimeError('service startup timeout')
    try:
        config={'bind':f'127.0.0.1:{port()}','mode':'mock','url':f'http://127.0.0.1:{server.server_port}/chat/completions',
                'journal_path':str(output/'generation.jsonl'),'deadline_ms':2000,'max_request_bytes':16384,'max_response_bytes':65536,
                'admission_limit':2,'max_calls':4,'routes':{r:{'model':'fixture/reviewer','provider':'fixture','max_tokens':512} for r in ('general','coding','reasoning')}}
        adapter=output/'adapter.json';adapter.write_text(json.dumps(config))
        subprocess.run([str(binary.with_name('braess-openrouter')),'--config',str(adapter),'--init'],env=env,check=True,capture_output=True)
        adapter_url=start(binary.with_name('braess-openrouter'),adapter)
        gconfig={'bind':f'127.0.0.1:{port()}','mode':'mock','jev_url':jev.url+'/v1/systemone','rubric_path':str(ROOT/'eval/rubric.json'),
                 'deadline_ms':4000,'max_request_bytes':16384,'max_response_bytes':65536,'admission_limit':2,'tracking_limit':16,
                 'uncertainty_ttl_ms':1000,'max_jev_calls':4,'handlers':{r:[adapter_url+'/generate/'+r] for r in config['routes']}}
        gateway=output/'gateway.json';gateway.write_text(json.dumps(gconfig));url=start(binary,gateway)
        ledger=Budget.create(output/'budget',cap_usd='0.02',max_attempts=3,pricing_sha256=digest(b'synthetic-pricing'))
        result=run(corpus,output/'prepared/tasks.json',output/'run',gateway_url=url+'/route',budget=ledger,estimate_usd='0.01',scope='synthetic',workers=1)
        assert result['summary']['completed']==1 and result['summary']['uncertain']==1 and result['summary']['deferred']==1
        assert len(requests)==2 and all(not r['authorization_present'] for r in requests)
        assert sum(e['kind']=='review_validated' for e in result['events'])==1
        assert len(list((output/'run/private').glob('*.response.json')))==2
        assert len(list((output/'run/private').glob('*.review.json')))==1
        assert ledger.inspect()['unresolved']==2
        private_write(output/'checks.json',canonical({'passed':True,'live_provider_calls':0,'generation_requests':len(requests),
                      'summary':result['summary'],'gateway_sha256':digest(binary.read_bytes()),
                      'adapter_sha256':digest(binary.with_name('braess-openrouter').read_bytes())}))
        print('PASS: actual gateway and adapter; one validated review, one rejected finding, one budget deferral; zero paid calls')
    finally:
        for p in processes:
            if p.poll() is None:p.terminate()
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
        for log in logs:log.close()
        jev.close();server.shutdown();server.server_close();thread.join()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--binary',type=Path,required=True)
    args=p.parse_args();smoke(args.output.resolve(),args.binary.resolve())
