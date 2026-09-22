#!/usr/bin/env python3
"""Offline FastMetal HTTP contracts, durable reservations and currency checks."""
import argparse
import http.server
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request


def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def call(url, body=None):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def run(output, binary):
    output.mkdir(parents=True, exist_ok=False)
    events = []
    class Fixture(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert self.headers.get('Authorization') is None
            events.append(body)
            text = body.get('messages', [{}])[0].get('content', '')
            v = json.loads(Path('src/generation/fixtures/fastmetal-text.json').read_text())
            v['model'] = 'gpt-4.1-nano' if text != 'mismatch' else 'wrong-model'
            v['choices'][0]['message']['content'] = 'synthetic answer'
            if text == 'tool':
                v['choices'][0]['message']['content'] = None
                v['choices'][0]['message']['tool_calls'] = [{}]
            if self.path == '/jev':
                from gateway_e2e import fixture_answer
                v = fixture_answer('general')
                v['model'] = 'typesafe/jev-1.13-20260917'
                if body['state']['request'] == 'uncertain':
                    v['answers']['supported']['noul'] = .52
                if body['state']['request'] == 'wrong-pin':
                    v['model'] = 'jev-1.13.0'
            payload = json.dumps(v).encode()
            self.send_response(429 if text == 'rate' else 200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('X-Litellm-Response-Cost', '-1' if text == 'cost' else '0.0005361')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
    fixture = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    env = {k:v for k,v in os.environ.items() if k not in ('FASTMETAL_API_KEY','FAST_METAL_API','OPENROUTER_API_KEY','TYPESAFE_API_KEY')}
    results = []
    try:
        for case in ['success','mismatch','cost','tool','rate']:
            bind = port()
            config = json.loads(Path('config/fastmetal.live.example.json').read_text())
            config.update(mode='mock',bind=f'127.0.0.1:{bind}',url=f'http://127.0.0.1:{fixture.server_port}/v1/chat/completions',journal_path=str((output / (case+'.jsonl')).resolve()),max_calls=1)
            path = output / (case+'.config.json')
            path.write_text(json.dumps(config))
            subprocess.run([str(binary),'--config',str(path),'--init'],check=True,env=env,capture_output=True)
            for restart in range(2):
                process = subprocess.Popen([str(binary),'--config',str(path)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                try:
                    for _ in range(100):
                        try:
                            call(f'http://127.0.0.1:{bind}/health'); break
                        except OSError: time.sleep(.02)
                    else: raise AssertionError('adapter failed startup')
                    before = len(events)
                    status, response = call(f'http://127.0.0.1:{bind}/generate/general',{'route':'general','request':case})
                    if restart:
                        assert status == 503 and len(events) == before, (status,response)
                    elif case == 'success':
                        assert status == 200, response
                        receipt = response['execution']
                        assert receipt['backend'] == 'fastmetal'
                        assert receipt['reported_cost_jpy'] == .0005361
                        assert receipt['usage'].get('cost') is None
                    else:
                        assert status == 502, response
                    results.append({'case':case,'restart':restart,'status':status})
                finally:
                    process.terminate();process.communicate(timeout=5)
        for body in events:
            assert 'provider' not in body and body['stream'] is False
            assert body['model'] == 'gpt-4.1-nano'
        assert len(events)==5
        # Exercise the FastMetal Jev gateway through the real companion handler.
        bind = port()
        config.update(bind=f'127.0.0.1:{bind}',journal_path=str((output/'two-hop.jsonl').resolve()),max_calls=2)
        path=output/'two-hop.config.json';path.write_text(json.dumps(config))
        subprocess.run([str(binary),'--config',str(path),'--init'],check=True,env=env,capture_output=True)
        adapter=subprocess.Popen([str(binary),'--config',str(path)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        gateway_bind=port()
        gateway_config=json.loads(Path('config/gateway.fastmetal.live.example.json').read_text())
        gateway_config.update(mode='mock',bind=f'127.0.0.1:{gateway_bind}',jev_url=f'http://127.0.0.1:{fixture.server_port}/jev')
        gateway_config['handlers']={r:[f'http://127.0.0.1:{bind}/generate/{r}'] for r in gateway_config['handlers']}
        gateway_path=output/'gateway.config.json';gateway_path.write_text(json.dumps(gateway_config))
        gateway=subprocess.Popen([str(binary.with_name('braess-router')),'--config',str(gateway_path)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            for target in (bind,gateway_bind):
                for _ in range(100):
                    try:
                        call(f'http://127.0.0.1:{target}/health'); break
                    except OSError: time.sleep(.02)
                else: raise AssertionError('two-hop startup failed')
            before=len(events)
            status,response=call(f'http://127.0.0.1:{gateway_bind}/route',{'request':'general'})
            assert status==200 and len(events)==before+2, (status,response)
            assert events[before]['model']=='typesafe/jev-1.13'
            assert events[before+1]['model']=='gpt-4.1-nano'
            status,response=call(f'http://127.0.0.1:{gateway_bind}/route',{'request':'uncertain'})
            assert status==200 and len(events)==before+3, (status,response)
            status,response=call(f'http://127.0.0.1:{gateway_bind}/route',{'request':'wrong-pin'})
            assert status==502 and len(events)==before+4, (status,response)
            count=len(events)
            status,response=call(f'http://127.0.0.1:{gateway_bind}/route',{'request':'x'*8192})
            assert status==413 and len(events)==count, (status,response)
            results.append({'case':'two-hop, fallback, wrong model pin, encoded size bound','passed':True})
        finally:
            gateway.terminate();gateway.communicate(timeout=5)
            adapter.terminate();adapter.communicate(timeout=5)
        (output/'result.json').write_text(json.dumps({'passed':True,'requests':events,'checks':results},indent=2)+'\n')
    finally:
        fixture.shutdown();fixture.server_close()
    print('PASS FastMetal HTTP contracts and restart accounting')

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    parser.add_argument('--binary',type=Path,required=True)
    args=parser.parse_args()
    run(args.output,args.binary.resolve())
