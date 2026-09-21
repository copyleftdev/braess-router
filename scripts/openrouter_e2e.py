#!/usr/bin/env python3
"""Synthetic adapter and gateway integration; no external requests or API keys."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import gateway_e2e as gateway


def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def request(url, value=None):
    body = None if value is None else json.dumps(value).encode()
    r = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    try:
        response = urllib.request.urlopen(r, timeout=4)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return {'status': response.status, 'body': json.loads(response.read())}


def run(output, binary):
    output.mkdir(parents=True, exist_ok=False)
    records, events, processes = [], [], []
    began, release = threading.Event(), threading.Event()
    class Fixture(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            events.append({'path': self.path, 'body': body, 'authorization_present': 'Authorization' in self.headers})
            text = body['messages'][0]['content']
            result = {'id': 'gen-fixture', 'object': 'chat.completion', 'model': body['model'], 'provider': 'Fixture',
                      'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'synthetic answer'}}],
                      'usage': {'prompt_tokens': 4, 'completion_tokens': 2, 'total_tokens': 6, 'cost': .000001}}
            status = 200
            if text == 'hold':
                began.set()
                release.wait(3)
            elif text == 'malformed':
                result = b'{not-json'
            elif text == 'bad_usage':
                result['usage']['total_tokens'] = 999
            elif text == 'rate_limit':
                status, result = 429, {'error': {'message': 'PRIVATE-MARKER'}}
            elif text == 'redirect':
                status = 302
            elif text == 'oversized':
                result = {'padding': 'x' * 9000}
            elif text == 'slow':
                time.sleep(.7)
            wire = result if isinstance(result, bytes) else json.dumps(result).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(wire)))
            if status == 302:
                self.send_header('Location', '/redirect-target')
            self.end_headers()
            try:
                self.wfile.write(wire)
            except (BrokenPipeError, ConnectionResetError):
                pass
    fixture = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
    thread = threading.Thread(target=fixture.serve_forever)
    thread.start()
    env = {k: v for k, v in os.environ.items() if k not in ('OPENROUTER_API_KEY', 'TYPESAFE_API_KEY', 'API_KEY')}
    logs = []
    def command(args):
        r = subprocess.run(args, env=env, capture_output=True, text=True, timeout=5)
        records.append({'command': [str(a) for a in args], 'returncode': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr})
        return r
    def start(config_path, executable=binary):
        log = (output / f'process-{len(logs)}.log').open('w')
        logs.append(log)
        p = subprocess.Popen([str(executable), '--config', str(config_path)], env=env, stdout=log, stderr=log)
        processes.append(p)
        bind = json.loads(config_path.read_text())['bind']
        url = 'http://' + bind
        for _ in range(150):
            if p.poll() is not None:
                raise AssertionError('service exited during startup')
            try:
                if request(url + '/health')['status'] == 200:
                    return p, url
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(.02)
        raise AssertionError('service did not start')
    def stop(p, force=False):
        (p.kill if force else p.terminate)()
        p.wait(timeout=5)
    def fresh(name, cap=8, vision=None):
        config = {'bind': f'127.0.0.1:{port()}', 'mode': 'mock', 'url': f'http://127.0.0.1:{fixture.server_port}/chat/completions',
                  'journal_path': str(output / (name + '.jsonl')), 'deadline_ms': 400, 'max_request_bytes': 4096,
                  'max_response_bytes': 8192, 'admission_limit': 1, 'max_calls': cap,
                  'routes': {r: {'model': 'fixture/' + r, 'provider': 'fixture', 'max_tokens': 16} for r in ('general', 'coding', 'reasoning')}}
        path = output / (name + '.json')
        if vision:
            config['vision_bundles'] = vision
            for route in config['routes'].values(): route['input_mode'] = 'vision_reference'
        path.write_text(json.dumps(config, indent=2))
        assert command([str(binary), '--config', str(path), '--init']).returncode == 0
        return config, path
    result = {'passed': False, 'live_provider_calls': 0}
    try:
        config, path = fresh('success', cap=2)
        p, url = start(path)
        assert command([str(binary), '--config', str(path), '--inspect']).returncode != 0
        assert command([str(binary), '--config', str(path), '--init']).returncode != 0
        first = request(url + '/generate/coding', {'request': 'code', 'route': 'coding'})
        assert first['status'] == 200 and first['body']['execution']['usage']['total_tokens'] == 6
        assert first['body']['execution']['requested_model'] == 'fixture/coding'
        assert request(url + '/generate/general', {'request': 'x', 'route': 'coding'})['status'] == 400
        assert request(url + '/generate', {'request': 'x', 'route': 'fallback'})['status'] == 400
        assert request(url + '/generate', {'request': 'x', 'route': 'coding', 'model': 'evil'})['status'] == 400
        assert request(url + '/generate', {'request': 'x' * 6000, 'route': 'coding'})['status'] == 413
        assert request(url + '/status')['body']['calls_reserved'] == 1
        stop(p)
        inspected = command([str(binary), '--config', str(path), '--inspect'])
        assert inspected.returncode == 0 and json.loads(inspected.stdout)['completed'] == 1
        p, url = start(path)
        assert request(url + '/generate', {'request': 'hello', 'route': 'general'})['status'] == 200
        assert request(url + '/generate', {'request': 'hello', 'route': 'general'})['body']['error'] == 'generation_call_budget_exhausted'
        stop(p)
        failures = []
        for case in ['malformed', 'bad_usage', 'rate_limit', 'redirect', 'oversized', 'slow']:
            config, path = fresh(case)
            before = len(events)
            p, url = start(path)
            response = request(url + '/generate', {'request': case, 'route': 'general'})
            assert response['status'] in (502, 504) and 'PRIVATE-MARKER' not in json.dumps(response)
            assert request(url + '/status')['body']['pending'] == 1
            assert request(url + '/generate', {'request': 'retry', 'route': 'general'})['body']['error'] == 'generation_admission_full'
            assert len(events) == before + 1
            stop(p)
            p, url = start(path)
            assert request(url + '/ready')['status'] == 503
            stop(p)
            failures.append({'case': case, 'response': response, 'uncertainty_retained_after_restart': True})
        config, path = fresh('forced-death')
        p, url = start(path)
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(request, url + '/generate', {'request': 'hold', 'route': 'general'})
            assert began.wait(2)
            assert request(url + '/generate', {'request': 'parallel', 'route': 'general'})['status'] == 503
            stop(p, force=True)
            release.set()
            try:
                pending.result(timeout=3)
            except (OSError, urllib.error.URLError):
                pass
        p, url = start(path)
        assert request(url + '/status')['body']['pending'] == 1
        assert request(url + '/ready')['status'] == 503
        stop(p)
        # Actual Braess -> adapter -> mock OpenRouter path, with Jev usage separate.
        config, path = fresh('integration')
        p, url = start(path)
        jev = gateway.Fixtures()
        try:
            gconfig = {'bind': f'127.0.0.1:{port()}', 'mode': 'mock', 'jev_url': jev.url + '/v1/systemone',
                       'rubric_path': str(gateway.ROOT / 'eval/rubric.json'), 'deadline_ms': 2000,
                       'max_request_bytes': 8192, 'max_response_bytes': 8192, 'admission_limit': 2,
                       'tracking_limit': 8, 'uncertainty_ttl_ms': 1000, 'max_jev_calls': 3,
                       'handlers': {r: [url + '/generate/' + r] for r in config['routes']}}
            gp = output / 'gateway.json'
            gp.write_text(json.dumps(gconfig))
            gateway_process, gateway_url = start(gp, binary.with_name('braess-router'))
            routed = request(gateway_url + '/route', {'request': 'coding'})
            assert routed['status'] == 200 and routed['body']['route'] == 'coding'
            assert routed['body']['usage']['input_tokens'] == 30
            assert routed['body']['handler_response']['execution']['usage']['prompt_tokens'] == 4
            before = len(events)
            fallback = request(gateway_url + '/route', {'request': 'uncertain'})
            assert fallback['body']['route'] == 'fallback' and len(events) == before
            stop(gateway_process)
            # A provisioned PNG is resolved only after the selected vision route.
            image = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZ1kAAAAASUVORK5CYII=')
            image_hash = hashlib.sha256(image).hexdigest()
            bundle = output/'vision-bundle'; bundle.mkdir()
            (bundle/'page-1.png').write_bytes(image)
            page = {'page':1,'sha256':image_hash,'bytes':len(image),'width':1,'height':1}
            manifest = {'schema_version':1,'complete':True,'publication_approved':False,
                        'document_id':'fixture-image','native_source_sha256':image_hash,
                        'coordinate_unit':'source_page_pixels','pages':[{**page,'file':'page-1.png'}]}
            raw = json.dumps(manifest).encode(); (bundle/'manifest.json').write_bytes(raw)
            manifest_hash = hashlib.sha256(raw).hexdigest()
            vc,vp = fresh('vision',vision={manifest_hash:str(bundle)})
            vision_process, vision_url = start(vp)
            reference = {'schema_version':1,'kind':'vision_reference_v1','document_id':'fixture-image',
                         'native_source_sha256':image_hash,'inspector_manifest_sha256':manifest_hash,
                         'prompt':'Describe the fixture pixel.','pages':[page]}
            before = len(events)
            for changed in [{**reference,'document_id':'other'}, {**reference,'pages':[page,page]},
                            {**reference,'inspector_manifest_sha256':'0'*64},
                            {**reference,'pages':[{**page,'sha256':'0'*64}]},
                            {**reference,'url':'https://untrusted.invalid/image.png'}]:
                assert request(vision_url+'/generate/general',{'route':'general','request':json.dumps(changed)})['status']==400
            assert request(vision_url+'/status')['body']['calls_reserved']==0 and len(events)==before
            # The running process must keep the approved startup bytes immutable.
            (bundle/'page-1.png').write_bytes(b'changed after startup')
            gconfig['handlers']={r:[vision_url+'/generate/'+r] for r in vc['routes']}
            gconfig['bind']=f'127.0.0.1:{port()}'
            vgp=output/'vision-gateway.json'; vgp.write_text(json.dumps(gconfig))
            vg,vgurl=start(vgp,binary.with_name('braess-router'))
            reference_wire=json.dumps(reference)
            vision_response=request(vgurl+'/route',{'request':reference_wire})
            assert vision_response['status']==200 and vision_response['body']['route']=='general'
            evidence=vision_response['body']['handler_response']['execution']['input_evidence']
            assert evidence=={'reference_sha256':hashlib.sha256(reference_wire.encode()).hexdigest(),'image_sha256':[image_hash]}
            parts=events[-1]['body']['messages'][0]['content']
            assert parts[0]=={'type':'text','text':reference['prompt']}
            assert parts[1]['type']=='image_url'
            assert base64.b64decode(parts[1]['image_url']['url'].split(',',1)[1],validate=True)==image
            # Capture another real local call through the demo observer contract.
            sys.path.insert(0,str(gateway.ROOT/'demo'))
            from recording import Recorder, verify
            from observe import observe
            from run_metrics import metrics
            recording=Recorder(output/'vision-recording',scope='synthetic',metadata={})
            try:
                recording.append('task_queued','vision-fixture',document_id='fixture-image',family_id='fixture-image',modality='image')
                observe(recording,'vision-fixture',vgurl+'/route',reference_wire)
            finally:
                recording.close()
            captured=verify(output/'vision-recording')
            assert captured['summary']['completed']==1
            observed=[e['data'] for e in captured['events'] if e['kind']=='response_received'][0]
            assert observed['generation_input_evidence']==evidence
            analysis=metrics(output/'vision-recording',output/'vision-metrics.json')
            assert analysis['tasks'][0]['generation_input_evidence']==evidence
            (output/'vision-reference.json').write_text(reference_wire)
            stop(vg); stop(vision_process)
            assert command([str(binary),'--config',str(vp)]).returncode!=0
            (bundle/'page-1.png').write_bytes(image)
            restored,restored_url=start(vp)
            assert request(restored_url+'/status')['body']['completed']==2
            stop(restored)
            journal_text=Path(vc['journal_path']).read_text()
            assert image_hash in journal_text and reference['prompt'] not in journal_text and 'base64' not in journal_text
            result['vision_response']=vision_response
            result['vision_checks']=['invalid references refused before reservation','immutable source bytes',
                                     'gateway to multipart handler','exact PNG round trip','source hashes in durable receipt',
                                     'changed source refuses restart','observer and analysis retain bound image evidence']
        finally:
            jev.close()
        stop(p)
        for event in events:
            assert not event['authorization_present']
            body = event['body']
            assert body['stream'] is False and 'models' not in body
            assert body['provider'] == {'only': ['fixture'], 'order': ['fixture'], 'allow_fallbacks': False, 'require_parameters': True}
        result.update(passed=True, failures=failures, gateway_response=routed, checks=['private create-only state', 'duplicate owner refusal', 'route/path consistency', 'injection rejection', 'body bound', 'durable receipt', 'call budget across restart', 'no retry or redirect', 'uncertainty after errors', 'forced death retention', 'concurrent admission', 'gateway integration', 'local fallback without generation'])
    finally:
        release.set()
        for p in processes:
            if p.poll() is None:
                p.kill()
                p.wait(timeout=5)
        fixture.shutdown()
        fixture.server_close()
        thread.join()
        for log in logs:
            log.close()
        (output / 'result.json').write_text(json.dumps(result, indent=2))
        (output / 'commands.json').write_text(json.dumps(records, indent=2))
        (output / 'events.json').write_text(json.dumps(events, indent=2))
        hashes = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*') if p.is_file()}
        (output / 'SHA256SUMS.json').write_text(json.dumps(hashes, indent=2))
    print('PASS: OpenRouter adapter and gateway integration; zero live provider calls')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--binary', type=Path, required=True)
    args = parser.parse_args()
    run(args.output.resolve(), args.binary.resolve())
