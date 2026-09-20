#!/usr/bin/env python3
"""Create a fresh private deployment; never replace an installation or reset state."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

BINARIES = ('braess-router', 'braess-budget-init', 'braess-journal-init', 'braess-journal-compact')


def systemd_quote(value):
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('Control characters are not supported in installation paths')
    value = value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    return '"' + value + '"'


def install(config_path, binary_dir, destination, name):
    if not re.fullmatch(r'braess-router(?:-[a-z0-9-]+)?', name):
        raise ValueError('Service name must be braess-router or braess-router-<lowercase suffix>')
    destination = destination.absolute()
    systemd_quote(str(destination))
    config = json.loads(config_path.read_text())
    if config.get('budget_path') is not None or config.get('request_journal_path') is not None:
        raise ValueError('Fresh installs require a configuration without existing state paths')
    rubric = Path(config['rubric_path']).resolve(strict=True)
    sources = {name: (binary_dir / name).resolve(strict=True) for name in BINARIES}
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    # A failed install remains visible for inspection. Never silently reset or reuse it.
    for directory in ('bin', 'config', 'state'):
        (destination / directory).mkdir(mode=0o700)
    for binary_name, source in sources.items():
        target = destination / 'bin' / binary_name
        shutil.copyfile(source, target)
        target.chmod(0o700)
    copied_rubric = destination / 'config/rubric.json'
    shutil.copyfile(rubric, copied_rubric)
    copied_rubric.chmod(0o600)
    config.update(rubric_path=str(copied_rubric),
                  budget_path=str(destination / 'state/calls.budget'),
                  request_journal_path=str(destination / 'state/requests.journal'))
    installed_config = destination / 'config/gateway.json'
    installed_config.write_text(json.dumps(config, indent=2) + '\n')
    installed_config.chmod(0o600)
    env = {k: v for k, v in os.environ.items() if k not in ('TYPESAFE_API_KEY', 'API_KEY')}
    for command in ([str(destination / 'bin/braess-journal-init'), str(installed_config)],
                    [str(destination / 'bin/braess-budget-init'), config['budget_path'], str(config['max_jev_calls'])]):
        subprocess.run(command, check=True, env=env, umask=0o077, capture_output=True)
    service = destination / (name + '.service')
    service.write_text(f'''[Unit]
Description=Braess semantic router
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
Type=exec
ExecStart=:{systemd_quote(str(destination / 'bin/braess-router'))} --config {systemd_quote(str(installed_config))}
EnvironmentFile=-{str(destination / 'config/provider.env').replace('%', '%%')}
UMask=0077
NoNewPrivileges=yes
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
KillMode=control-group

[Install]
WantedBy=default.target
''')
    service.chmod(0o600)
    manifest = {'service': str(service), 'config': str(installed_config),
                'binary_sha256': {n: hashlib.sha256((destination / 'bin' / n).read_bytes()).hexdigest() for n in BINARIES}}
    (destination / 'installation.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (destination / 'installation.json').chmod(0o600)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--binary-dir', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--name', default='braess-router')
    args = parser.parse_args()
    result = install(args.config, args.binary_dir, args.destination, args.name)
    print('Created service:', result['service'])
    print('No credentials copied; service not enabled or started.')
