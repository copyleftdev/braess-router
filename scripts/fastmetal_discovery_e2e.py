#!/usr/bin/env python3
"""Offline MCP initialization, SSE/JSON contracts and discovery-only enforcement."""
import argparse
import http.server
import json
import os
from pathlib import Path
import subprocess
import threading

CANARY = 'PRIVATE_DISCOVERY_CANARY'
FREE = {'list_models', 'get_model', 'quota'}
FIXTURES = Path(__file__).resolve().parents[1] / 'src/fastmetal/discovery/fixtures'


def run(output, binary):
    output.mkdir(parents=True, exist_ok=False)
    events = []
    failures = []
    current = 'sse'

    class Fixture(http.server.BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *_):
            pass

        def handle(self):
            try:
                super().handle()
            except ConnectionResetError:
                pass  # Rejected response bodies may cause a deliberate early disconnect.

        def do_POST(self):
            try:
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                method = body['method']
                events.append({'case': current, 'method': method, 'params': body['params']})
                assert self.headers.get('Authorization') is None
                assert self.headers.get('Accept') == 'application/json, text/event-stream'
                if method != 'initialize':
                    assert self.headers.get('Mcp-Session-Id') == 'synthetic-session'
                    assert self.headers.get('MCP-Protocol-Version') == '2025-03-26'
                if method == 'notifications/initialized':
                    assert 'id' not in body
                    self.send_response(202)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                if method == 'initialize':
                    result = json.loads((FIXTURES / 'initialize.json').read_text())['result']
                    assert body['params']['capabilities'] == {}
                    if current == 'protocol':
                        result['protocolVersion'] = 'unknown-version'
                elif method == 'tools/list':
                    def tool(name):
                        schema = {'type': 'object', 'properties': {}}
                        if name == 'get_model':
                            schema.update(properties={'model': {'type': 'string'}}, required=['model'])
                        return {'name': name, 'inputSchema': schema}
                    tools = [tool(n) for n in sorted(FREE)] + [tool('ask'), tool('decide')]
                    if current == 'missing':
                        tools = [t for t in tools if t['name'] != 'quota']
                    if current == 'schema':
                        tools[0]['inputSchema']['required'] = ['prompt']
                    if current == 'duplicate':
                        tools.append(tools[0])
                    result = {'tools': tools}
                    if current == 'pages':
                        if 'cursor' not in body['params']:
                            result = {'tools': tools[:1], 'nextCursor': 'next'}
                        else:
                            assert body['params']['cursor'] == 'next'
                            result = {'tools': tools[1:]}
                    if current == 'cursor-loop':
                        result = {'tools': [], 'nextCursor': 'repeat'}
                elif method == 'tools/call':
                    name = body['params']['name']
                    assert name in FREE, 'paid or unknown tool invoked'
                    if name == 'list_models':
                        result = json.loads((FIXTURES / 'catalog.json').read_text())['result']
                        if current == 'count':
                            result['structuredContent']['count'] += 1
                    elif name == 'get_model':
                        assert body['params']['arguments'] == {'model': 'gpt-4.1-nano'}
                        result = json.loads((FIXTURES / 'model.json').read_text())['result']
                        if current == 'model':
                            result['structuredContent']['model'] = 'wrong-model'
                    else:
                        result = {'structuredContent': {'balance': 99, 'max_budget': 100, 'spend': 1,
                                                       'key': CANARY, 'video': {'private': CANARY}}}
                        if current == 'quota':
                            result['structuredContent']['spend'] = 'bad'
                    if current == 'tool-error':
                        result = {'isError': True, 'content': [{'type': 'text', 'text': CANARY}]}
                else:
                    raise AssertionError('unexpected method')
                envelope = {'jsonrpc': '2.0', 'id': body['id'], 'result': result}
                if current == 'id':
                    envelope['id'] += 1
                if current == 'rpc-error':
                    envelope.pop('result')
                    envelope['error'] = {'code': -32603, 'message': CANARY}
                wire = json.dumps(envelope).encode()
                if current == 'json':
                    content_type = 'application/json; charset=utf-8'
                else:
                    content_type = 'text/event-stream'
                    wire = b': keepalive\r\nevent: message\r\ndata: ' + wire + b'\r\n\r\n'
                if current == 'truncated':
                    wire = wire[:-4]
                if current == 'oversize':
                    wire = b'x' * (2 * 1024 * 1024 + 1)
                if current == 'html':
                    content_type = 'text/html'
                self.send_response(302 if current == 'redirect' else 200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(wire)))
                self.send_header('Mcp-Session-Id', 'synthetic-session')
                if current == 'redirect':
                    self.send_header('Location', f'http://127.0.0.1:{self.server.server_port}/leak')
                self.end_headers()
                try:
                    # Deliberately split UTF-8/SSE boundaries across writes.
                    for offset in range(0, len(wire), 31):
                        self.wfile.write(wire[offset:offset + 31])
                except (BrokenPipeError, ConnectionResetError):
                    pass
            except Exception as error:
                failures.append(type(error).__name__ + ': ' + str(error))
                self.close_connection = True

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    env = {k: v for k, v in os.environ.items() if k not in ('FASTMETAL_API_KEY', 'FAST_METAL_API', 'OPENROUTER_API_KEY', 'TYPESAFE_API_KEY')}
    env['FASTMETAL_API_KEY'] = CANARY  # Mock transport must never forward this.
    results = []
    try:
        for current in ['sse', 'json', 'pages', 'protocol', 'missing', 'schema', 'duplicate',
                        'cursor-loop', 'count', 'model', 'quota', 'tool-error', 'id', 'rpc-error',
                        'truncated', 'oversize', 'html', 'redirect']:
            target = output / (current + '.snapshot.json')
            command = [str(binary), '--output', str(target), '--model', 'gpt-4.1-nano',
                       '--mock-url', f'http://127.0.0.1:{server.server_port}/mcp']
            start = len(events)
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
            assert not failures, failures
            assert CANARY not in result.stdout + result.stderr + target.read_text()
            if current in ('sse', 'json', 'pages'):
                assert result.returncode == 0, result.stderr
                snapshot = json.loads(target.read_text())
                assert snapshot['currency'] == 'JPY' and snapshot['quota']['balance'] == 99
                assert snapshot['completed_at_unix_ms'] >= snapshot['started_at_unix_ms']
                assert len(snapshot['models']) == 3
                assert snapshot['selected_models'][0]['supports_vision'] is True
                assert snapshot['quota'] == {'balance': 99, 'max_budget': 100, 'spend': 1}
                assert target.stat().st_mode & 0o777 == 0o600
                assert [e['params']['name'] for e in events[start:] if e['method'] == 'tools/call'] == ['list_models', 'get_model', 'quota']
                count = len(events)
                original = target.read_bytes()
                duplicate = subprocess.run(command, env=env, capture_output=True, text=True, timeout=5)
                assert duplicate.returncode != 0 and len(events) == count and target.read_bytes() == original
            else:
                assert result.returncode != 0 and target.read_bytes() == b'', (current, result.stdout, result.stderr)
                if current == 'redirect':
                    assert len(events) == start + 1
            results.append({'case': current, 'passed': True, 'requests': len(events) - start})
        (output / 'result.json').write_text(json.dumps({'passed': True, 'checks': results, 'events': events}, indent=2) + '\n')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    print('PASS MCP discovery: initialization, schemas, bounds, currency, redaction and no paid tools')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--binary', type=Path, required=True)
    args = parser.parse_args()
    run(args.output, args.binary.resolve())
