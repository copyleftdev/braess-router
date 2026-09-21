#!/usr/bin/env python3
"""Run the real Braess binary with synthetic providers and record measured events."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from gateway_e2e import gateway
from observe import observe
from recording import Recorder, canonical, digest, verify


def run(output, binary):
    output.mkdir(parents=True, exist_ok=False)
    recorder = Recorder(output / 'recording', scope='synthetic',
                        metadata={'gateway_binary_sha256': digest(binary.read_bytes())})
    cases = ['general', 'coding', 'reasoning', 'uncertain', 'malformed', 'error_handler']
    try:
        with gateway(binary, output, 'recording-smoke', deadline_ms=2000,
                     admission_limit=8, max_jev_calls=20) as (url, fixtures):
            for i, _ in enumerate(cases):
                recorder.append('task_queued', f'task-{i}', document_id=f'fixture-{i}',
                                family_id=f'fixture-{i}', modality='text')
            with ThreadPoolExecutor(max_workers=2) as pool:
                jobs = [pool.submit(observe, recorder, f'task-{i}', url + '/route', text)
                        for i, text in enumerate(cases)]
                for job in jobs:
                    job.result()
    finally:
        recorder.close()
    result = verify(output / 'recording')
    assert result['summary']['tasks'] == 6
    assert result['summary']['incomplete'] == 0
    assert result['summary']['uncertain'] >= 1
    assert result['summary']['total_cost_usd'] is None
    (output / 'replay.json').write_bytes(canonical(result))
    print('PASS: real gateway, synthetic providers, measured observer events; no paid calls')
    print(result['summary'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--binary', required=True, type=Path)
    args = parser.parse_args()
    run(args.output.resolve(), args.binary.resolve())
