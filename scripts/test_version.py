#!/usr/bin/env python3
"""Exercise version policy using disposable Git repositories."""
import subprocess
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name('check_version.py').resolve()


def run(*args, cwd, success=True):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    assert (result.returncode == 0) == success, result.stderr
    return result.stdout.strip()


for new, changelog, success in [('0.1.0-alpha.1', True, False),
                                ('0.1.0-alpha.0', True, False),
                                ('0.1.0-alpha.2', False, False),
                                ('0.1.0-alpha.2', True, True),
                                ('0.1.0', True, True)]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        run('git', 'init', '-q', cwd=root)
        run('git', 'config', 'user.email', 'test@example.invalid', cwd=root)
        run('git', 'config', 'user.name', 'Version test', cwd=root)
        manifest = root / 'Cargo.toml'
        manifest.write_text('[package]\nversion="0.1.0-alpha.1"\n')
        run('git', 'add', '.', cwd=root)
        run('git', 'commit', '-qm', 'base', cwd=root)
        base = run('git', 'rev-parse', 'HEAD', cwd=root)
        manifest.write_text('[package]\nversion="' + new + '"\n')
        (root / 'src').mkdir()
        (root / 'src/lib.rs').write_text('// changed runtime\n')
        if changelog:
            (root / 'CHANGELOG.md').write_text('New version\n')
        run('git', 'add', '.', cwd=root)
        run('git', 'commit', '-qm', 'change', cwd=root)
        run('python3', str(SCRIPT), '--base', base, cwd=root, success=success)
print('PASS: unchanged, backwards, missing changelog, prerelease and stable version cases')
