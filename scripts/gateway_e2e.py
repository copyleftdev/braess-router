#!/usr/bin/env python3
"""Bounded, synthetic loopback gateway checks. No provider traffic or credentials.

Runs a release binary against independently implemented HTTP fixtures. Output must
be a new directory; artifacts include actual responses, fixture events and hashes.
This is correctness evidence, not a production capacity benchmark.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ROUTES = ('general', 'coding', 'reasoning', 'fallback')
MARKER = 'UPSTREAM_PRIVATE_DIAGNOSTIC_MUST_NOT_ESCAPE'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def fixture_answer(route='general', confidence=.99):
    return {'model': 'jev-1.13.0', 'usage': {'input_tokens': 30, 'output_tokens': 10},
            'answers': {'route': {'type': 'choice', 'choice': route,
                                  'confidence': confidence,
                                  'probabilities': {r: .97 if r == route else .01 for r in ROUTES}},
                        'supported': {'type': 'noul', 'noul': .99}}}


class Fixtures:
    def __init__(self):
        self.events = []
        self.lock = threading.Lock()
        self.started = threading.Event()
        self.release = threading.Event()
        fixtures = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                try:
                    value = json.loads(body)
                except ValueError:
                    value = {}
                request = value.get('state', value).get('request', '')
                with fixtures.lock:
                    fixtures.events.append({'path': self.path, 'request': request,
                                            'body': value, 'body_sha256': sha(body),
                                            'authorization_present': self.headers.get('Authorization') is not None})
                status = 200
                response = {}
                if self.path == '/v1/systemone':
                    route = request if request in ROUTES else 'general'
                    response = fixture_answer(route, .1 if request == 'uncertain' else .99)
                    if request == 'malformed':
                        response = b'{invalid'
                    elif request == 'unknown_route':
                        response['answers']['route']['choice'] = 'http://evil.invalid/execute'
                    elif request == 'invalid_contract':
                        response['model'] = 'unexpected-model'
                    elif request == 'redirect':
                        status = 302
                    elif request == 'rate_limit':
                        status, response = 429, {'private': MARKER}
                    elif request == 'oversized':
                        response = {'private': MARKER, 'padding': 'x' * 20000}
                    elif request == 'delayed':
                        time.sleep(.7)
                    elif request == 'hold':
                        fixtures.started.set()
                        fixtures.release.wait(3)
                else:
                    response = {'answer': 'synthetic handler answer', 'handler': self.path[1:]}
                    if request == 'bad_handler':
                        response = b'not-json'
                    elif request == 'error_handler':
                        status, response = 500, {'private': MARKER}
                wire = response if isinstance(response, bytes) else json.dumps(response).encode()
                try:
                    self.send_response(status)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(wire)))
                    if status == 302:
                        self.send_header('Location', fixtures.url + '/redirect-target')
                    self.end_headers()
                    if request == 'slow_body' and self.path == '/v1/systemone':
                        self.wfile.write(wire[:1])
                        self.wfile.flush()
                        time.sleep(.7)
                        self.wfile.write(wire[1:])
                    else:
                        self.wfile.write(wire)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = False
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


def request(url, value=None):
    data = None if value is None else json.dumps(value).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json', 'Authorization': 'Bearer inbound-synthetic-canary'})
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            status, body = response.status, response.read()
            retry_after = response.headers.get('Retry-After')
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read()
        retry_after = error.headers.get('Retry-After')
    return {'status': status, 'body': json.loads(body), 'body_sha256': sha(body), 'retry_after': retry_after,
            'elapsed_ms': (time.monotonic() - start) * 1000}


@contextmanager
def gateway(binary, output, name, initialize_durable=False, **overrides):
    fixtures = Fixtures()
    process = None
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    config = {'bind': f'127.0.0.1:{port}', 'mode': 'mock',
              'jev_url': fixtures.url + '/v1/systemone',
              'rubric_path': str(ROOT / 'eval/rubric.json'),
              'deadline_ms': 200, 'max_request_bytes': 4096, 'max_response_bytes': 4096,
              'admission_limit': 4, 'tracking_limit': 32, 'uncertainty_ttl_ms': 100,
              'max_jev_calls': 200,
              'handlers': {r: [fixtures.url + '/' + r] for r in ROUTES if r != 'fallback'}}
    config.update(overrides)
    if initialize_durable:
        config['budget_path'] = str((output / (name + '.budget.bin')).resolve())
        config['request_journal_path'] = str((output / (name + '.journal.jsonl')).resolve())
    config_path = output / (name + '.config.json')
    config_path.write_text(json.dumps(config, indent=2) + '\n')
    try:
        if initialize_durable:
            subprocess.run([str(binary.with_name('braess-budget-init')), config['budget_path'], str(config['max_jev_calls'])], check=True, capture_output=True)
            subprocess.run([str(binary.with_name('braess-journal-init')), str(config_path)], check=True, capture_output=True)
        with (output / (name + '.log')).open('w') as log:
            process = subprocess.Popen([str(binary), '--config', str(config_path)],
                                       cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                       env={k: v for k, v in os.environ.items() if k != 'TYPESAFE_API_KEY'})
            url = f'http://127.0.0.1:{port}'
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError(f'{name}: gateway exited; inspect {name}.log')
                try:
                    health = request(url + '/health')
                    if health['status'] == 200:
                        break
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(.02)
            else:
                raise RuntimeError('gateway readiness timeout')
            yield url, fixtures
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        fixtures.close()
        (output / (name + '.fixture-events.json')).write_text(json.dumps(fixtures.events, indent=2) + '\n')


def verify_ledgers(status):
    require(status['status'] == 200, 'status endpoint failed')
    body = status['body']
    ledgers = [body['jev_ledger']] + [ledger for group in body['handler_ledgers'].values() for ledger in group]
    for ledger in ledgers:
        require(ledger['admitted_total'] == sum(ledger[key] for key in (
            'active', 'unconfirmed', 'expired_unconfirmed', 'not_sent_total',
            'response_received_total', 'backend_acknowledged_total')), 'ledger conservation violated')
        require(ledger['active'] == 0, 'request left active ledger owner')
    require(body['jev_calls_reserved'] <= body['max_jev_calls'], 'budget accounting violated')
    return body


def run(binary, output):
    output.mkdir(parents=True, exist_ok=False)
    records = []
    cases = [(r, {'request': r}, 200, r) for r in ('general', 'coding', 'reasoning')]
    cases += [('uncertain', {'request': 'uncertain'}, 200, None),
              ('unknown_field', {'request': 'general', 'destination': 'http://evil.invalid'}, 400, None),
              ('oversized_input', {'request': 'x' * 10000}, 413, None),
              ('redirect', {'request': 'redirect'}, 502, None),
              ('malformed', {'request': 'malformed'}, 502, None),
              ('invalid_contract', {'request': 'invalid_contract'}, 502, None),
              ('unknown_route', {'request': 'unknown_route'}, 502, None),
              ('rate_limit', {'request': 'rate_limit'}, 502, None),
              ('oversized', {'request': 'oversized'}, 502, None),
              ('delayed', {'request': 'delayed'}, 504, None),
              ('slow_body', {'request': 'slow_body'}, 504, None),
              ('bad_handler', {'request': 'bad_handler'}, 502, 'general'),
              ('error_handler', {'request': 'error_handler'}, 502, 'general')]
    for name, payload, expected_status, dispatched in cases:
        with gateway(binary, output, name) as (url, fixtures):
            result = request(url + '/route', payload)
            status = request(url + '/status')
            state = verify_ledgers(status)
            if name in ('malformed', 'invalid_contract', 'unknown_route', 'rate_limit', 'oversized', 'delayed', 'slow_body', 'redirect'):
                ledger = state['jev_ledger']
                require(ledger['unconfirmed'] + ledger['expired_unconfirmed'] == 1, f'{name}: lost uncertain Jev work')
            if name in ('bad_handler', 'error_handler'):
                ledger = state['handler_ledgers']['general'][0]
                require(ledger['unconfirmed'] + ledger['expired_unconfirmed'] == 1, f'{name}: lost uncertain handler work')
            record = {'case': name, 'input': payload, 'expected_status': expected_status,
                      'expected_handler': dispatched, 'response': result, 'status_after': status}
            records.append(record)
            require(result['status'] == expected_status, f'{name}: {result}')
            if name not in ('unknown_field', 'oversized_input'):
                trace = result['body']['routing_trace']
                boundaries = [trace[k] for k in ('decision_send_started_ns', 'decision_validated_ns',
                              'handler_send_started_ns', 'handler_validated_ns', 'finished_ns') if trace[k] is not None]
                require(boundaries == sorted(boundaries), f'{name}: unordered routing trace')
                require(trace['decision_send_started_ns'] is not None, f'{name}: missing decision send start')
                if dispatched is not None or name == 'uncertain':
                    evidence = trace['decision']
                    require(evidence['choice'] == (dispatched or 'general'), f'{name}: wrong model choice')
                    require(evidence['probabilities'][evidence['choice']] == .97, 'wrong model probability')
                    require(evidence['confidence'] == (.1 if name == 'uncertain' else .99), 'wrong confidence')
                    require(trace['decision_validated_ns'] is not None, 'validated decision not timed')
                else:
                    require(trace['decision'] is None and trace['decision_validated_ns'] is None,
                            f'{name}: failed decision falsely validated')
                require((trace['handler_send_started_ns'] is not None) == (dispatched is not None),
                        f'{name}: incorrect handler dispatch observation')
                require((trace['handler_validated_ns'] is not None) == (name in ('general','coding','reasoning')),
                        f'{name}: incorrect handler validation observation')
            require(MARKER not in json.dumps(result), f'{name}: private upstream body escaped')
            handlers = [event for event in fixtures.events if event['path'] != '/v1/systemone']
            require([event['path'] for event in handlers] == ([] if dispatched is None else ['/' + dispatched]),
                    f'{name}: unexpected dispatch {handlers}')
            require(all(not event['authorization_present'] for event in fixtures.events), 'inbound authorization forwarded upstream')
            if name in ('unknown_field', 'oversized_input'):
                require(not fixtures.events, 'invalid caller input reached upstream')
            if name == 'uncertain':
                require(result['body']['route'] == 'fallback', 'uncertain result must expose abstention')
            if name in ('general', 'coding', 'reasoning'):
                require(result['body']['route'] == name, 'wrong route returned')
                require(result['body']['handler_response']['handler'] == name, 'wrong handler result returned')

    with gateway(binary, output, 'budget', max_jev_calls=2) as (url, fixtures):
        responses = [request(url + '/route', {'request': 'general'}) for _ in range(3)]
        records.append({'case': 'budget', 'responses': responses, 'status_after': request(url + '/status')})
        require([r['status'] for r in responses[:2]] == [200, 200], 'budget rejected valid calls')
        require(responses[2]['status'] >= 400, 'budget permitted an extra call')
        require(responses[2]['body']['routing_trace']['decision_send_started_ns'] is None,
                'budget refusal falsely reports Jev dispatch')
        require(sum(e['path'] == '/v1/systemone' for e in fixtures.events) == 2, 'Jev budget exceeded')

    with gateway(binary, output, 'concurrency', admission_limit=1, deadline_ms=2000) as (url, fixtures):
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(request, url + '/route', {'request': 'hold'})
            require(fixtures.started.wait(2), 'held request never reached Jev')
            rejected = request(url + '/route', {'request': 'general'})
            during = request(url + '/status')
            fixtures.release.set()
            first = pending.result(timeout=5)
        after = request(url + '/route', {'request': 'coding'})
        records.append({'case': 'concurrency', 'held': first, 'rejected': rejected, 'replacement': after,
                        'status_during': during, 'status_after': request(url + '/status')})
        require(rejected['status'] >= 400, 'concurrent admission exceeded cap')
        trace = rejected['body'].get('routing_trace')
        require(trace is None or trace['decision_send_started_ns'] is None,
                'admission refusal falsely reports Jev dispatch')
        require(first['status'] == after['status'] == 200, 'permit did not recover after success')
        require(sum(e['path'] == '/v1/systemone' for e in fixtures.events) == 2, 'rejected work reached Jev')

    with gateway(binary, output, 'concurrent_budget', max_jev_calls=3, admission_limit=8) as (url, fixtures):
        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(lambda _: request(url + '/route', {'request': 'general'}), range(12)))
        records.append({'case': 'concurrent_budget', 'responses': responses, 'status_after': request(url + '/status')})
        require(sum(e['path'] == '/v1/systemone' for e in fixtures.events) == 3, 'concurrent Jev budget exceeded')
        require(sum(r['status'] == 200 for r in responses) == 3, 'concurrent budget success count incorrect')

    with gateway(binary, output, 'uncertainty_bound', admission_limit=1, tracking_limit=1,
                 uncertainty_ttl_ms=1000) as (url, fixtures):
        malformed = request(url + '/route', {'request': 'malformed'})
        retained = request(url + '/route', {'request': 'general'})
        require(malformed['status'] == 502 and retained['status'] == 503,
                'unconfirmed work failed to retain capacity')
        time.sleep(1.05)
        expired = request(url + '/route', {'request': 'general'})
        after = request(url + '/status')
        require(expired['status'] == 503, 'expired uncertainty evicted from bounded tracking')
        require(after['body']['jev_ledger']['expired_unconfirmed'] == 1, 'expiry falsely confirmed completion')
        require(len(fixtures.events) == 1, 'tracking/admission rejected request reached upstream')
        records.append({'case': 'uncertainty_bound', 'malformed': malformed, 'retained': retained,
                        'expired': expired, 'status_after': after})

    with gateway(binary, output, 'slow_headers', deadline_ms=100) as (url, fixtures):
        port = int(url.rsplit(':', 1)[1])
        with socket.create_connection(('127.0.0.1', port), timeout=3) as peer:
            peer.sendall(b'POST /route HTTP/1.1\r\nHost: localhost\r\n')
            start = time.monotonic()
            try:
                closed = peer.recv(4096) == b''
            except ConnectionResetError:
                closed = True
            elapsed = time.monotonic() - start
        require(closed, 'incomplete headers connection did not close')
        require(not fixtures.events, 'incomplete headers reached upstream')
        records.append({'case': 'slow_headers', 'closed_after_seconds': elapsed,
                        'status_after': request(url + '/status')})

    with gateway(binary, output, 'client_drop', deadline_ms=200) as (url, fixtures):
        port = int(url.rsplit(':', 1)[1])
        body = json.dumps({'request': 'hold'}).encode()
        with socket.create_connection(('127.0.0.1', port), timeout=3) as peer:
            peer.sendall((f'POST /route HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n').encode() + body)
            require(fixtures.started.wait(2), 'disconnect case never reached upstream')
        for _ in range(100):
            after = request(url + '/status')
            ledger = after['body']['jev_ledger']
            if ledger['active'] == 0 and ledger['unconfirmed'] + ledger['expired_unconfirmed'] == 1:
                break
            time.sleep(.02)
        else:
            raise AssertionError('client disconnect/deadline lost uncertain work or leaked owner')
        require(all(e['path'] == '/v1/systemone' for e in fixtures.events), 'disconnected request dispatched handler')
        fixtures.release.set()
        records.append({'case': 'client_drop', 'status_after': after,
                        'scope': 'eventual cleanup within request deadline; immediate disconnect cancellation not assumed'})

    with gateway(binary, output, 'bounded_load', admission_limit=8, deadline_ms=2000) as (url, fixtures):
        start = time.monotonic()
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _: request(url + '/route', {'request': 'general'}), range(100)))
        elapsed = time.monotonic() - start
        records.append({'case': 'bounded_load', 'attempts': 100, 'concurrency': 4,
                        'elapsed_seconds': elapsed, 'responses': responses,
                        'status_after': request(url + '/status')})
        require(all(r['status'] == 200 for r in responses), 'bounded local workload lost requests')
        require(len(fixtures.events) == 200, 'unexpected number of upstream requests')
    for record in records:
        verify_ledgers(record['status_after'])
    (output / 'results.json').write_text(json.dumps(records, indent=2) + '\n')
    sources = ['scripts/gateway_e2e.py', 'src/gateway.rs', 'src/bin/braess-router.rs',
               'src/lib.rs', 'src/ledger_http.rs', 'src/request_ledger.rs', 'Cargo.toml', 'Cargo.lock', 'eval/rubric.json']
    for name in sources:
        if (ROOT / name).exists():
            destination = output / 'sources' / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / name).read_bytes())
    (output / 'source-hashes.json').write_text(json.dumps(
        {name: sha((ROOT / name).read_bytes()) for name in sources if (ROOT / name).exists()}, indent=2) + '\n')
    (output / 'binary-sha256.txt').write_text(sha(binary.read_bytes()) + '\n')
    (output / 'VERIFICATION.txt').write_text(f'PASS: {len(cases)} isolated cases; finite and concurrent call budgets; synchronized admission; bounded uncertainty tracking; slow headers; client drop; 100 local load requests. Synthetic mocks only.\n')
    hashes = {str(p.relative_to(output)): sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}
    (output / 'SHA256SUMS.json').write_text(json.dumps(hashes, indent=2) + '\n')
    print((output / 'VERIFICATION.txt').read_text(), end='')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--binary', type=Path, default=Path('target/release/braess-router'))
    arguments = parser.parse_args()
    run(arguments.binary.resolve(), arguments.output.resolve())
