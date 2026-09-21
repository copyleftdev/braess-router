#!/usr/bin/env python3
"""Run actual local Rust transports with scripted findings on one private OCR source."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import urllib.request
from budget import Budget
from corpus import private_write
from evidence_bundle import build
from fleet import run
from fleet_smoke import port
from prepare_review import prepare
from recording import canonical,digest
from review import load_text
from review_link import link


def smoke(corpus,output,binaries,quote):
    corpus,output,binaries=Path(corpus).resolve(),Path(output).resolve(),Path(binaries).resolve()
    manifest=json.loads((corpus/'manifest.json').read_bytes())
    if len(manifest['documents'])!=1 or manifest['documents'][0].get('representation')!='ocr_text':raise ValueError('one OCR source required')
    document=manifest['documents'][0];text=load_text(corpus,document)
    if not quote or len(quote)>500 or quote not in text:raise ValueError('explicit source quote required')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    private_write(output/'protocol.json',canonical({'id':'ocr-location-fixture','version':'1','scope':'synthetic_protocol',
                  'production_request':'Locate the specified phrase for a source-mapping integration test: '+quote+'. This scripted exercise does not evaluate legal relevance.'}))
    prepared=prepare(corpus,output/'protocol.json',output/'prepared')
    if len(prepared['tasks'])!=1:raise ValueError('OCR fixture must fit one gateway request')
    rubric_path=Path(__file__).resolve().parent.parent/'eval/rubric.discovery.json';rubric=json.loads(rubric_path.read_bytes())
    counts={'decision':0,'generation':0};errors=[]
    class Fixture(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            try:
                assert 'Authorization' not in self.headers
                length=int(self.headers['Content-Length']);assert 0<length<=65536
                value=json.loads(self.rfile.read(length))
                if self.path=='/v1/systemone':
                    assert value['questions']==rubric['questions'] and value['model']==rubric['model']
                    counts['decision']+=1
                    result={'model':rubric['model'],'usage':{'input_tokens':30,'output_tokens':10},
                            'answers':{'route':{'type':'choice','choice':'review_deep','confidence':.99,
                            'probabilities':{'review_standard':.01,'review_deep':.98,'fallback':.01}},
                            'supported':{'type':'noul','noul':.99}}}
                else:
                    assert self.path=='/chat/completions' and value['model']=='fixture/reviewer-deep'
                    source=json.loads(value['messages'][0]['content']);assert source['evidence_text']==text
                    start=text.index(quote);counts['generation']+=1
                    report={'schema_version':1,'document_id':document['document_id'],'source_sha256':document['source_sha256'],
                            'responsiveness':'responsive','findings':[{'id':'location1','kind':'issue_highlight','start':start,
                            'end':start+len(quote),'quote':quote,'note':'Scripted source-location fixture, not a legal-review conclusion.'}]}
                    result={'id':'gen-ocr-fixture','object':'chat.completion','model':value['model'],'provider':'Fixture',
                            'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(report)}}],
                            'usage':{'prompt_tokens':10,'completion_tokens':10,'total_tokens':20,'cost':0.000001}}
                wire=canonical(result);self.send_response(200);self.send_header('Content-Length',str(len(wire)))
                self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(wire)
            except Exception:
                errors.append('fixture_contract_failure');self.send_error(500)
    server=ThreadingHTTPServer(('127.0.0.1',0),Fixture);thread=threading.Thread(target=server.serve_forever);thread.start()
    processes=[];logs=[];environment={k:os.environ[k] for k in ('PATH','HOME','LANG') if k in os.environ}
    def start(name,configuration):
        path=output/(name+'.json');private_write(path,canonical(configuration))
        if name=='adapter':subprocess.run([str(binaries/'braess-openrouter'),'--config',str(path),'--init'],env=environment,check=True,capture_output=True)
        log=open(output/(name+'.log'),'xb');logs.append(log)
        process=subprocess.Popen([str(binaries/('braess-openrouter' if name=='adapter' else 'braess-router')),'--config',str(path)],env=environment,stdout=log,stderr=log);processes.append(process)
        url='http://'+configuration['bind'];opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(100):
            if process.poll() is not None:raise ValueError('fixture service exited')
            try:
                with opener.open(url+'/health',timeout=.2) as response:
                    if response.status==200:return url
            except OSError:pass
            time.sleep(.03)
        raise ValueError('fixture service startup timeout')
    try:
        adapter=start('adapter',{'bind':f'127.0.0.1:{port()}','mode':'mock','url':f'http://127.0.0.1:{server.server_port}/chat/completions',
                      'journal_path':str(output/'generation.jsonl'),'deadline_ms':2000,'max_request_bytes':16384,'max_response_bytes':65536,
                      'admission_limit':1,'max_calls':1,'routes':{r:{'model':'fixture/'+r.replace('review_','reviewer-'),'provider':'fixture','max_tokens':1024} for r in ('review_standard','review_deep')}})
        gateway=start('gateway',{'bind':f'127.0.0.1:{port()}','mode':'mock','jev_url':f'http://127.0.0.1:{server.server_port}/v1/systemone',
                      'rubric_path':str(rubric_path),'deadline_ms':4000,'max_request_bytes':16384,'max_response_bytes':65536,
                      'admission_limit':1,'tracking_limit':16,'uncertainty_ttl_ms':1000,'max_jev_calls':1,
                      'handlers':{r:[adapter+'/generate/'+r] for r in ('review_standard','review_deep')}})
        budget=Budget.create(output/'budget',cap_usd='0.01',max_attempts=1,pricing_sha256=digest(b'ocr-fixture-not-real-pricing'))
        result=run(corpus,output/'prepared/tasks.json',output/'run',gateway_url=gateway+'/route',budget=budget,estimate_usd='0.01',scope='synthetic',workers=1)
        assert result['summary']['completed']==1 and not errors and counts=={'decision':1,'generation':1}
        build(corpus/'manifest.json',document['document_id'],output/'inspector')
        association=link(corpus,output/'prepared/tasks.json',output/'run',prepared['tasks'][0]['task_id'],inspector=output/'inspector')
        private_write(output/'review-link.json',canonical(association))
        private_write(output/'checks.json',canonical({'scope':'real local Rust transports; scripted decision and review on private OCR source; no semantic accuracy evaluation',
                      'run_id':result['run']['run_id'],'counts':counts,'external_provider_calls':0,'authorization_present':False,
                      'binary_sha256':{name:digest((binaries/name).read_bytes()) for name in ('braess-router','braess-openrouter')},
                      'rubric_sha256':digest(rubric_path.read_bytes()),'finding_regions':len(association['review']['findings'][0]['location']['image_regions'])}))
        print('PASS: OCR quote linked through real local gateway and adapter; scripted providers; zero paid calls')
    finally:
        for process in reversed(processes):
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        for log in logs:log.close()
        server.shutdown();server.server_close();thread.join()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('corpus','output','binaries'):p.add_argument(name,type=Path)
    p.add_argument('--quote',required=True);a=p.parse_args();smoke(a.corpus,a.output,a.binaries,a.quote)
