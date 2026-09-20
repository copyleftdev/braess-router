#!/usr/bin/env python3
"""Check release versions without requiring third-party Python packages."""
import argparse
import re
import subprocess
import tomllib
from pathlib import Path


def version(text):
    match = re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(alpha|beta|rc)\.(0|[1-9]\d*))?', text)
    if not match:
        raise ValueError('Use X.Y.Z or X.Y.Z-{alpha,beta,rc}.N')
    major, minor, patch, stage, number = match.groups()
    return (int(major), int(minor), int(patch), {'alpha': 0, 'beta': 1, 'rc': 2, None: 3}[stage], int(number or 0))


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base')
    parser.add_argument('--tag')
    args = parser.parse_args()
    current = tomllib.loads(Path('Cargo.toml').read_text())['package']['version']
    value = version(current)
    if args.base:
        changed = git('diff', '--name-only', args.base, 'HEAD').splitlines()
        runtime = any(p.startswith('src/') or p in ('Cargo.toml', 'Cargo.lock') for p in changed)
        if runtime:
            previous = tomllib.loads(git('show', args.base + ':Cargo.toml'))['package']['version']
            if value <= version(previous):
                raise ValueError('Runtime/dependency changes require a greater package version')
            if 'CHANGELOG.md' not in changed:
                raise ValueError('Runtime/dependency changes require a changelog entry')
    if args.tag:
        if args.tag != 'v' + current:
            raise ValueError('Release tag must equal v' + current)
        if git('rev-parse', args.tag + '^{commit}') != git('rev-parse', 'HEAD'):
            raise ValueError('Checkout does not match release tag')
        subprocess.run(['git', 'merge-base', '--is-ancestor', 'HEAD', 'origin/main'], check=True)
    print('Version check passed:', current)


if __name__ == '__main__':
    main()
