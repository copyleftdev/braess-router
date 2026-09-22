#!/usr/bin/env python3
"""Check a local validation bundle against this checkout; not a v1 approval."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from validate_local import ROOT, source_paths

STAGES = ('toolchain', 'metadata', 'format', 'tests', 'clippy', 'build',
          'gateway', 'catalog', 'readiness', 'evaluator', 'deployment', 'provider_contract', 'openrouter', 'fastmetal', 'fastmetal_discovery')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contained(root, name):
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('invalid evidence path')
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError('evidence path escapes root or is a symlink')
    return path


def verify(bundle, sources):
    manifest = json.loads((bundle / 'SHA256SUMS.json').read_text())
    actual_files = {str(p.relative_to(bundle)) for p in bundle.rglob('*') if p.is_file()}
    if set(manifest) != actual_files - {'SHA256SUMS.json'}:
        raise ValueError('evidence manifest does not cover exactly the bundle files')
    for name, expected in manifest.items():
        if digest(contained(bundle, name)) != expected:
            raise ValueError('evidence hash mismatch: ' + name)
    result = json.loads((bundle / 'result.json').read_text())
    stages = json.loads((bundle / 'stages.json').read_text())
    if result.get('passed') is not True or result.get('failure') is not None:
        raise ValueError('validation did not pass')
    if result.get('stages_completed') != len(STAGES) or [s['name'] for s in stages] != list(STAGES):
        raise ValueError('required validation stages missing or reordered')
    if any(s.get('returncode') != 0 or s.get('timed_out') is not False for s in stages):
        raise ValueError('validation stage failed or timed out')
    recorded = json.loads((bundle / 'source-hashes.json').read_text())
    if set(recorded) != set(sources):
        raise ValueError('source inventory differs from current checkout')
    for name, current in sources.items():
        if recorded[name] != digest(current) or recorded[name] != digest(contained(bundle, 'source/' + name)):
            raise ValueError('stale or inconsistent source evidence: ' + name)
    return {'evidence_valid': True, 'source_files': len(sources), 'verified_files': len(manifest),
            'stages': list(STAGES), 'manifest_sha256': digest(bundle / 'SHA256SUMS.json'),
            'scope': 'local validation evidence matches checkout; not release acceptance',
            'v1_accepted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    if args.report.resolve().is_relative_to(bundle):
        raise ValueError('write the verification report outside the sealed bundle')
    report = verify(bundle, {str(p.relative_to(ROOT)): p for p in source_paths()})
    report['checkout_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    report['working_tree_clean'] = not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()
    with args.report.open('x') as file:
        json.dump(report, file, indent=2)
        file.write('\n')
    print('PASS: validation evidence matches checkout; v1 acceptance remains separate')


if __name__ == '__main__':
    main()
