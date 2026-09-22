#!/usr/bin/env python3
"""Build and validate the current router offline with synthetic HTTP fixtures.

Requires cached Cargo dependencies, rustfmt, Clippy, Python 3 and loopback sockets.
Never invokes a live/provider harness. Each run requires a new artifact directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def source_paths():
    paths = [ROOT / n for n in ('Cargo.toml', 'Cargo.lock', 'README.md', 'CONTRIBUTING.md',
                               'CHANGELOG.md', 'SECURITY.md', 'LICENSE-MIT', 'LICENSE-APACHE', '.gitignore')]
    for directory, pattern in [('src', '*.rs'), ('src', '*.json'), ('scripts', '*.py'), ('scripts', '*.c'), ('config', '*.json'),
                               ('eval', '*.json'), ('docs', '*.md'), ('.github', '*.yml')]:
        paths.extend((ROOT / directory).rglob(pattern))
    for pattern in ('*.py', '*.html', '*.css', '*.js', '*.cjs', '*.json', '*.md', '*.txt'):
        paths.extend((ROOT / 'demo').rglob(pattern))
    paths.extend(ROOT / 'eval' / n for n in ('rubric.json', 'rubric.customer-service.json', 'cases.jsonl'))
    return sorted(set(paths))


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    records = []
    env = {k: v for k, v in os.environ.items() if k not in ('TYPESAFE_API_KEY', 'OPENROUTER_API_KEY', 'FASTMETAL_API_KEY', 'FAST_METAL_API', 'API_KEY')}
    sources = {str(p.relative_to(ROOT)): digest(p) for p in source_paths()}
    for name in sources:
        target = output / 'source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    write(output / 'source-hashes.json', sources)
    binaries = {}

    def stage(name, command, timeout=300):
        print('Running ' + name, flush=True)
        start = time.monotonic()
        timed_out = False
        with (output / (name + '.stdout')).open('w') as stdout, (output / (name + '.stderr')).open('w') as stderr:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stdout,
                                       stderr=stderr, start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    code = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    code = process.wait(timeout=5)
        records.append(dict(name=name, command=command, returncode=code, timed_out=timed_out,
                            elapsed_seconds=time.monotonic() - start))
        write(output / 'stages.json', records)
        if code != 0 or timed_out:
            raise RuntimeError('stage failed: ' + name)

    failure = None
    try:
        stage('toolchain', ['rustc', '--version', '--verbose'])
        stage('metadata', ['cargo', 'metadata', '--locked', '--offline', '--no-deps', '--format-version', '1'])
        metadata = json.loads((output / 'metadata.stdout').read_text())
        target = Path(metadata['target_directory']) / 'release'
        stage('format', ['cargo', 'fmt', '--check'])
        stage('tests', ['cargo', 'test', '--locked', '--offline'])
        stage('clippy', ['cargo', 'clippy', '--locked', '--offline', '--all-targets', '--', '-D', 'warnings'])
        stage('build', ['cargo', 'build', '--locked', '--offline', '--release', '--bins'], timeout=1800)
        binaries = {str(target / n): digest(target / n) for n in
                    ('braess-router', 'braess-eval', 'braess-budget-init', 'braess-journal-init', 'braess-journal-compact', 'braess-openrouter', 'braess-fastmetal', 'braess-fastmetal-discover')}
        write(output / 'binary-hashes.json', binaries)
        for name, script, binary in [('gateway', 'gateway_e2e.py', 'braess-router'),
                                     ('catalog', 'gateway_catalog_e2e.py', 'braess-router'),
                                     ('readiness', 'gateway_readiness_e2e.py', 'braess-router'),
                                     ('evaluator', 'custom_eval_e2e.py', 'braess-eval'),
                                     ('deployment', 'deployment_e2e.py', 'braess-router'),
                                     ('provider_contract', 'provider_contract_e2e.py', 'braess-router'),
                                     ('openrouter', 'openrouter_e2e.py', 'braess-openrouter'),
                                     ('fastmetal', 'fastmetal_e2e.py', 'braess-fastmetal'),
                                     ('fastmetal_discovery', 'fastmetal_discovery_e2e.py', 'braess-fastmetal-discover')]:
            stage(name, [sys.executable, str(ROOT / 'scripts' / script), str(output / name),
                         '--binary', str(target / binary)])
        actual = {str(p.relative_to(ROOT)): digest(p) for p in source_paths()}
        if actual != sources:
            raise RuntimeError('source changed during validation')
        if any(digest(Path(path)) != expected for path, expected in binaries.items()):
            raise RuntimeError('binary changed during validation')
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        failure = str(error)
    write(output / 'result.json', dict(passed=failure is None, failure=failure,
          stages_completed=len(records), scope='offline build and synthetic core regressions; not production acceptance'))
    write(output / 'SHA256SUMS.json', {str(p.relative_to(output)): digest(p)
          for p in sorted(output.rglob('*')) if p.is_file()})
    print(('PASS' if failure is None else 'FAIL') + ': ' + str(output), flush=True)
    return 0 if failure is None else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.output.resolve()))
