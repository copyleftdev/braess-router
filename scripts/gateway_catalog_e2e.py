#!/usr/bin/env python3
"""Exercise a custom catalog with synthetic HTTP and durable accounting."""
import argparse
import json
from pathlib import Path
import shutil
import gateway_e2e as e


def answer(route='billing', confidence=.99):
    if route not in e.ROUTES:
        route = 'billing'
    return {'model': 'jev-1.13.0', 'usage': {'input_tokens': 30, 'output_tokens': 10},
            'answers': {'route': {'type': 'choice', 'choice': route,
                                  'confidence': confidence,
                                  'probabilities': {r: .98 if r == route else .01 for r in e.ROUTES}},
                        'supported': {'type': 'noul', 'noul': .99}}}


def run(binary, output):
    output.mkdir(parents=True, exist_ok=False)
    e.ROUTES = ('billing', 'support', 'fallback')
    e.fixture_answer = answer
    rubric = e.ROOT / 'eval/rubric.customer-service.json'
    records = []
    with e.gateway(binary, output, 'catalog', initialize_durable=True,
                   rubric_path=str(rubric), max_jev_calls=20) as (url, fixtures):
        for label, expected, handler in [('billing', 200, 'billing'),
                                         ('support', 200, 'support'),
                                         ('uncertain', 200, None),
                                         ('unknown_route', 502, None)]:
            start = len(fixtures.events)
            response = e.request(url + '/route', {'request': label})
            events = fixtures.events[start:]
            e.require(response['status'] == expected, f'{label}: wrong status')
            e.require([x['path'] for x in events if x['path'] != '/v1/systemone'] ==
                      ([] if handler is None else ['/' + handler]), 'incorrect dispatch')
            if expected == 200:
                e.require(response['body']['route'] == (handler or 'fallback'), 'incorrect route')
            records.append({'case': label, 'response': response})
        status = e.request(url + '/status')
        state = e.verify_ledgers(status)
        e.require(state['jev_calls_reserved'] == 4, 'incorrect budget')
        e.require(all(not x['authorization_present'] for x in fixtures.events), 'credential forwarded')
    journal = [json.loads(line) for line in (output / 'catalog.journal.jsonl').read_text().splitlines()]
    (output / 'results.json').write_text(json.dumps({'passed': True, 'cases': records,
                                                   'status': status, 'journal': journal}, indent=2) + '\n')
    paths = ['Cargo.toml', 'Cargo.lock', 'eval/rubric.customer-service.json',
             'config/gateway.customer-service.mock.json', 'scripts/gateway_catalog_e2e.py',
             'scripts/gateway_e2e.py']
    paths += [str(p.relative_to(e.ROOT)) for p in (e.ROOT / 'src').rglob('*.rs')]
    for path in paths:
        target = output / 'source' / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(e.ROOT / path, target)
    manifest = {str(p.relative_to(output)): e.sha(p.read_bytes())
                for p in sorted(output.rglob('*')) if p.is_file()}
    (output / 'manifest.json').write_text(json.dumps({'files': manifest,
        'binary_sha256': e.sha(binary.read_bytes())}, indent=2) + '\n')
    print(json.dumps({'passed': True, 'cases': len(records), 'artifact': str(output)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--binary', type=Path, default=Path('target/release/braess-router'))
    args = parser.parse_args()
    run(args.binary, args.output)
