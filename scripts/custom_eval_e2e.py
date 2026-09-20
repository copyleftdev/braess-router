#!/usr/bin/env python3
"""Offline CLI regression for custom catalogs; no provider calls."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(output, binary=Path('target/release/braess-eval')):
    output.mkdir(parents=True, exist_ok=False)
    cases = [{'id': label, 'split': 'heldout' if label == 'fallback' else 'dev',
              'tag': 'synthetic_cli_fixture', 'request': 'Synthetic ' + label,
              'expected': label} for label in ('billing', 'support', 'fallback')]
    dataset = output / 'cases.jsonl'
    dataset.write_text(''.join(json.dumps(c) + '\n' for c in cases))
    invalid = output / 'invalid.jsonl'
    invalid.write_text(json.dumps({**cases[0], 'expected': 'coding'}) + '\n')
    commands = []

    def invoke(name, arguments, success):
        target = output / (name + '.json')
        command = [str(binary), '--out', str(target), *arguments]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                env={k: v for k, v in os.environ.items() if k != 'TYPESAFE_API_KEY'})
        commands.append(dict(command=command, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr))
        assert (result.returncode == 0) == success
        if success:
            report = json.loads(target.read_text())
            assert report['live'] is False and report['complete'] is True
            assert all(r['response'] is None for r in report['records'])
            events = [json.loads(line) for line in Path(report['attempt_log']).read_text().splitlines()]
            assert events[0]['event'] == 'header' and events[-1]['event'] == 'report_written'
            assert events[0]['planned_cases'] == [r['case'] for r in report['records']]
            assert len(events) == 2 + 2 * len(report['records'])
            for index, record in enumerate(report['records']):
                assert events[1 + index * 2] == {'event': 'begin', 'case_id': record['case']['id']}
                assert events[2 + index * 2] == {'event': 'outcome', 'record': record}
            return report
        assert not target.exists(), 'invalid labels produced an output artifact'

    args = ['--rubric', 'eval/rubric.customer-service.json', '--cases', str(dataset)]
    report = invoke('custom', args, True)
    assert report['baseline_policy'] == 'always_fallback'
    assert report['completed_cases'] == 3
    assert all(r['baseline'] == 'fallback' for r in report['records'])
    assert all(s['jev'] is None for s in report['splits'].values())
    subset = invoke('heldout', args + ['--split', 'heldout'], True)
    assert subset['completed_cases'] == 1 and subset['records'][0]['case']['expected'] == 'fallback'
    legacy = invoke('legacy', [], True)
    assert legacy['completed_cases'] == 24 and legacy['baseline_policy'] == 'legacy_keyword'
    invoke('invalid', ['--rubric', 'eval/rubric.customer-service.json', '--cases', str(invalid)], False)
    (output / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    (output / 'verification.json').write_text(json.dumps({'passed': True, 'cli_cases': 4, 'live_calls': 0}) + '\n')
    for source in [*ROOT.glob('src/**/*.rs'), ROOT / 'Cargo.toml', ROOT / 'Cargo.lock',
                   ROOT / 'eval/rubric.json', ROOT / 'eval/rubric.customer-service.json',
                   ROOT / 'eval/cases.jsonl', Path(__file__).resolve()]:
        target = output / 'source' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    (output / 'binary.sha256').write_text(hashlib.sha256(binary.read_bytes()).hexdigest() + '\n')
    (output / 'SHA256SUMS.json').write_text(json.dumps({str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.rglob('*')) if p.is_file()}, indent=2) + '\n')
    print('PASS: custom labels, heldout selection, legacy baseline, invalid-label refusal; no live calls.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--binary', type=Path, default=Path('target/release/braess-eval'))
    args = parser.parse_args()
    run(args.output.resolve(), args.binary.resolve())
