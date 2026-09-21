#!/usr/bin/env python3
"""Replay observed provider responses and verify the gateway locally; no provider calls."""
import argparse
from contextlib import contextmanager
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

import gateway_e2e as e


@contextmanager
def fixture(cases, injected=None):
    events = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def do_POST(self):
            selected = None
            if injected is not None and self.path in ('/billing', '/support'):
                length = int(self.headers.get('Content-Length', '0'))
                self.rfile.read(min(length, 65536))
                events.append({'path': self.path})
                raw = b'{"answer":"synthetic local handler"}'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            try:
                length = int(self.headers.get('Content-Length', '-1'))
                if self.path == '/v1/systemone' and 0 <= length <= 65536:
                    body = json.loads(self.rfile.read(length))
                    authorization = self.headers.get('Authorization')
                    events.append({'path': self.path, 'body': body, 'authorization_present': authorization is not None})
                    if injected is not None:
                        selected = injected
                    elif authorization in (None, 'Bearer replay-test'):
                        selected = next((c for c in cases if c['request'] == body
                                         and c['authenticated'] == (authorization is not None)), None)
            except (ValueError, OSError):
                pass
            raw = selected['response_utf8'].encode() if selected else b'{"mock_error":"unobserved_request"}'
            self.send_response(selected['status'] if selected else 501)
            self.send_header('Content-Type', selected['content_type'] if selected else 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever)
    worker.start()
    try:
        yield server.server_port, events
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def run(output, binary):
    output.mkdir(parents=True, exist_ok=False)
    corpus = e.ROOT / 'eval/provider-contract.json'
    cases = json.loads(corpus.read_text())['cases']
    e.require(len({c['id'] for c in cases}) == len(cases), 'duplicate capture identity')
    for case in cases:
        e.require(hashlib.sha256(case['response_utf8'].encode()).hexdigest() == case['response_sha256'],
                  'captured response bytes changed')
    records = []
    with fixture(cases) as (port, _):
        for case in cases:
            client = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            headers = {'Content-Type': 'application/json'}
            if case['authenticated']:
                headers['Authorization'] = 'Bearer replay-test'
            client.request('POST', '/v1/systemone', json.dumps(case['request']), headers)
            response = client.getresponse()
            raw = response.read()
            e.require(response.status == case['status'] and raw == case['response_utf8'].encode(),
                      'recorded response replay differs')
            e.require(response.getheader('Content-Type') == case['content_type'], 'content type differs')
            records.append({'case': case['id'], 'status': response.status, 'exact_replay': True})
            client.close()
        for body, headers in [({}, {}), (cases[0]['request'], {'Authorization': 'Bearer unobserved'})]:
            client = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            client.request('POST', '/v1/systemone', json.dumps(body), headers)
            response = client.getresponse()
            e.require(response.status == 501 and json.loads(response.read())['mock_error'] == 'unobserved_request',
                      'fixture invented unobserved provider behavior')
            client.close()
    router = next(c for c in cases if c['id'] == 'router')
    gateway_records = []
    for case in [router, *(c for c in cases if c['status'] >= 400)]:
        # Error bodies are injected into a valid router request. This tests gateway
        # handling; it does not claim that valid requests naturally produce these errors.
        with fixture(cases, injected=case) as (port, events):
            with e.gateway(binary, output, case['id'], initialize_durable=True,
                           jev_url=f'http://127.0.0.1:{port}/v1/systemone', deadline_ms=2000,
                           rubric_path=str(e.ROOT / 'eval/rubric.customer-service.json'),
                           handlers={'billing': [f'http://127.0.0.1:{port}/billing'],
                                     'support': [f'http://127.0.0.1:{port}/support']}) as (url, handlers):
                response = e.request(url + '/route', {'request': router['request']['state']['request']})
                state = e.request(url + '/status')['body']
                e.require(events[0]['body'] == router['request'], 'gateway request differs from the captured router request')
                e.require(not events[0]['authorization_present'], 'mock gateway forwarded credentials')
                if case['status'] >= 400:
                    e.require(response['status'] == 502, 'provider error was not translated to a gateway error')
                    e.require(response['body'] == {'error': 'jev_transport_error'}, 'provider error details escaped')
                    e.require(state['request_journal']['pending'] == 1, 'provider error discarded uncertainty')
                    e.require(len(events) == 1 and not handlers.events, 'provider error dispatched to a handler')
                else:
                    e.require(response['status'] == 200 and response['body']['route'] == 'billing',
                              'captured success did not dispatch to billing')
                    e.require([row['path'] for row in events] == ['/v1/systemone', '/billing'],
                              'captured success dispatched unexpected work')
                    e.require(state['request_journal']['pending'] == 0, 'validated success left pending work')
                    e.require(response['body']['usage'] == json.loads(case['response_utf8'])['usage'],
                              'captured token usage was changed')
                e.require(state['jev_calls_reserved'] == 1, 'captured response changed call accounting')
                gateway_records.append({'case': case['id'], 'response': response, 'state': state,
                                        'mode': 'captured_response_injection'})
    (output / 'result.json').write_text(json.dumps({'passed': True, 'live_calls': 0,
        'replays': records, 'gateway_cases': gateway_records}, indent=2) + '\n')
    for source in (corpus, Path(__file__), e.ROOT / 'scripts/gateway_e2e.py'):
        (output / source.name).write_bytes(source.read_bytes())
    (output / 'SHA256SUMS.json').write_text(json.dumps({str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.rglob('*')) if p.is_file()}, indent=2) + '\n')
    print(f'PASS: {len(cases)} exact replays and {len(gateway_records)} gateway response checks; zero live calls')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--binary', type=Path, required=True)
    args = parser.parse_args()
    run(args.output.resolve(), args.binary.resolve())
