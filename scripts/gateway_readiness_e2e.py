#!/usr/bin/env python3
"""Readiness transitions through actual HTTP, without provider traffic."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import time
import gateway_e2e as e


def run(binary, output):
    output.mkdir(parents=True, exist_ok=False)
    records = []

    def check(url, expected, reason=None):
        result = e.request(url + '/ready')
        records.append(result)
        e.require(result['status'] == expected, 'wrong readiness status')
        e.require(result['body']['ready'] == (expected == 200), 'wrong readiness body')
        e.require(result['body']['upstream_health'] == 'unchecked', 'invented upstream health')
        if reason:
            e.require(reason in result['body']['reasons'], 'missing rejection reason')
        e.require(e.request(url + '/health')['status'] == 200, 'liveness changed')
        return result

    with e.gateway(binary, output, 'budget', initialize_durable=True, max_jev_calls=1) as (url, fixtures):
        for _ in range(3):
            check(url, 200)
        e.require(not fixtures.events, 'readiness sent upstream traffic')
        e.require(e.request(url + '/status')['body']['jev_calls_reserved'] == 0, 'readiness spent budget')
        e.require(e.request(url + '/route', {'request': 'general'})['status'] == 200, 'route failed')
        check(url, 503, 'jev_call_budget_exhausted')

    with e.gateway(binary, output, 'held', admission_limit=1, deadline_ms=2000) as (url, fixtures):
        check(url, 200)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(e.request, url + '/route', {'request': 'hold'})
            e.require(fixtures.started.wait(2), 'held request did not start')
            check(url, 503, 'ingress_full')
            fixtures.release.set()
            e.require(pending.result()['status'] == 200, 'held request failed')
        check(url, 200)

    with e.gateway(binary, output, 'uncertain', initialize_durable=True,
                   admission_limit=1, tracking_limit=1, uncertainty_ttl_ms=0) as (url, fixtures):
        e.require(e.request(url + '/route', {'request': 'malformed'})['status'] == 502, 'fault failed')
        check(url, 503, 'jev_capacity_full')

    with e.gateway(binary, output, 'handler', admission_limit=1,
                   tracking_limit=1, uncertainty_ttl_ms=0) as (url, fixtures):
        e.require(e.request(url + '/route', {'request': 'bad_handler'})['status'] == 502, 'fault failed')
        report = check(url, 503, 'handler_capacity_full')
        e.require(report['body']['unavailable_routes'] == ['general'], 'wrong unavailable route')

    with e.gateway(binary, output, 'rate', jev_rate_limit={'max_requests': 1, 'window_ms': 1000}) as (url, fixtures):
        check(url, 503, 'jev_rate_limited')
        time.sleep(1.05)
        check(url, 200)
        e.require(e.request(url + '/route', {'request': 'general'})['status'] == 200, 'route failed')
        check(url, 503, 'jev_rate_limited')
        time.sleep(1.05)
        check(url, 200)

    (output / 'results.json').write_text(json.dumps({'passed': True, 'observations': records}, indent=2) + '\n')
    paths = ['Cargo.toml', 'Cargo.lock', 'scripts/gateway_readiness_e2e.py',
             'scripts/gateway_e2e.py', 'eval/rubric.json']
    paths += [str(p.relative_to(e.ROOT)) for p in (e.ROOT / 'src').rglob('*.rs')]
    for path in paths:
        target = output / 'source' / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(e.ROOT / path, target)
    manifest = {str(p.relative_to(output)): e.sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}
    (output / 'manifest.json').write_text(json.dumps({'files': manifest, 'binary_sha256': e.sha(binary.read_bytes())}, indent=2) + '\n')
    print(json.dumps({'passed': True, 'readiness_observations': len(records)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--binary', type=Path, default=Path('target/release/braess-router'))
    args = parser.parse_args()
    run(args.binary, args.output)
