#!/usr/bin/env python3
"""Verify the installed deployment, optionally through a real user systemd manager."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import urllib.error
import uuid

import gateway_e2e as e
from install_service import install


def run(output, binary, systemd=False):
    output.mkdir(parents=True, exist_ok=False)
    destination = output / 'installed bundle % $'
    name = 'braess-router-test-' + uuid.uuid4().hex
    fixtures = e.Fixtures()
    process = None
    linked = False
    log = (output / 'process.log').open('w')
    records = []
    env = {k: v for k, v in os.environ.items() if k not in ('TYPESAFE_API_KEY', 'API_KEY')}

    def command(*args):
        result = subprocess.run(args, capture_output=True, text=True, timeout=40, env=env)
        records.append({'command': list(args), 'returncode': result.returncode,
                        'stdout': result.stdout, 'stderr': result.stderr})
        result.check_returncode()
        return result.stdout

    def stop():
        nonlocal process
        if systemd:
            command('systemctl', '--user', 'stop', name + '.service')
            status = command('systemctl', '--user', 'show', name + '.service',
                             '--property=ExecMainStatus', '--value').strip()
            e.require(status == '0', 'service did not stop cleanly')
        elif process is not None:
            process.send_signal(signal.SIGTERM)
            e.require(process.wait(timeout=5) == 0, 'installed process did not stop cleanly')
            process = None

    def start():
        nonlocal process
        if systemd:
            command('systemctl', '--user', 'start', name + '.service')
        else:
            process = subprocess.Popen([str(destination / 'bin/braess-router'), '--config',
                                        str(destination / 'config/gateway.json')],
                                       cwd='/tmp', env=env, stdout=log, stderr=log)
        for _ in range(150):
            try:
                if e.request(url + '/health')['status'] == 200:
                    if systemd:
                        pid = int(command('systemctl', '--user', 'show', name + '.service',
                                          '--property=MainPID', '--value').strip())
                        entries = Path(f'/proc/{pid}/environ').read_bytes().split(b'\0')
                        e.require(b'BRAESS_DEPLOYMENT_TEST=synthetic' in entries,
                                  'service did not load its environment file')
                    return
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(.02)
        raise AssertionError('installed deployment did not start')

    try:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        url = f'http://127.0.0.1:{port}'
        config = json.loads((e.ROOT / 'config/gateway.mock.json').read_text())
        config.update(bind=f'127.0.0.1:{port}', jev_url=fixtures.url + '/v1/systemone',
                      rubric_path=str(e.ROOT / 'eval/rubric.json'), admission_limit=1,
                      deadline_ms=1000, max_jev_calls=10,
                      handlers={r: [fixtures.url + '/' + r] for r in e.ROUTES if r != 'fallback'})
        config_path = output / 'input.json'
        config_path.write_text(json.dumps(config))
        manifest = install(config_path, binary.parent, destination, name)
        e.require(destination.stat().st_mode & 0o777 == 0o700, 'deployment directory is not private')
        e.require(not (destination / 'config/provider.env').exists(), 'installer copied a provider credential')
        for path in (destination / 'state').iterdir():
            e.require(path.stat().st_mode & 0o077 == 0, 'state file accessible by other users')
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (destination / 'state').iterdir()}
        try:
            install(config_path, binary.parent, destination, name)
            raise AssertionError('installer overwrote existing deployment')
        except FileExistsError:
            pass
        e.require(before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (destination / 'state').iterdir()}, 'reinstallation changed state')
        invalid = output / 'existing-state.json'
        invalid.write_text((destination / 'config/gateway.json').read_text())
        try:
            install(invalid, binary.parent, output / 'refused', name)
            raise AssertionError('installer accepted existing state configuration')
        except ValueError:
            pass
        e.require(not (output / 'refused').exists(), 'refused install created files')
        command('systemd-analyze', '--recursive-errors=no', '--man=no', 'verify', manifest['service'])
        if systemd:
            marker = destination / 'config/provider.env'
            marker.write_text('BRAESS_DEPLOYMENT_TEST=synthetic\n')
            marker.chmod(0o600)
            command('systemctl', '--user', 'link', manifest['service'])
            linked = True
            command('systemctl', '--user', 'daemon-reload')
        start()
        duplicate = subprocess.run([str(destination / 'bin/braess-router'), '--config', manifest['config']],
                                   capture_output=True, env=env, timeout=5)
        e.require(duplicate.returncode != 0, 'second state owner was admitted')
        # Stop during actual upstream work. A timer releases the fixture while stop drains.
        with ThreadPoolExecutor(max_workers=2) as pool:
            response = pool.submit(e.request, url + '/route', {'request': 'hold'})
            e.require(fixtures.started.wait(2), 'held request never dispatched')
            stopped = pool.submit(stop)
            time.sleep(.05)
            fixtures.release.set()
            e.require(response.result(timeout=5)['status'] == 200, 'shutdown dropped in-flight response')
            stopped.result(timeout=5)
        start()
        clean = e.request(url + '/status')['body']
        e.require(clean['jev_calls_reserved'] == 1 and clean['request_journal']['pending'] == 0,
                  'clean restart did not preserve completed accounting')
        stop()
        active_config = destination / 'config/gateway.json'
        next_config = destination / 'config/next.json'
        revised = json.loads(active_config.read_text())
        revised['tracking_limit'] += 1
        next_config.write_text(json.dumps(revised))
        tool = str(destination / 'bin/braess-journal-compact')
        archive = destination / 'state/pre-migration.journal'
        checkpoint = destination / 'state/migration.checkpoint'
        budget_path = destination / 'state/calls.budget'
        journal_path = destination / 'state/requests.journal'
        budget_before = budget_path.read_bytes()
        journal_before = journal_path.read_bytes()
        inspected = json.loads(command(tool, str(active_config), '--inspect'))
        e.require(inspected['budget_used'] == 1 and inspected['state']['pending'] == 0,
                  'offline inspection disagrees with clean restart')
        migration = json.loads(command(tool, str(active_config), str(archive), str(checkpoint),
                                       '--migrate-to', str(next_config)))
        e.require(migration['migrated'] and archive.read_bytes() == journal_before,
                  'migration lost original journal evidence')
        e.require(budget_path.read_bytes() == budget_before, 'migration changed spent budget')
        old = subprocess.run([tool, str(active_config), '--inspect'], capture_output=True, timeout=5)
        e.require(old.returncode != 0, 'old configuration still opens migrated scope')
        new = json.loads(command(tool, str(next_config), '--inspect'))
        e.require(new['budget_used'] == 1 and new['state'] == inspected['state'],
                  'migration changed completed counters')
        os.replace(next_config, active_config)
        start()
        fixtures.started.clear()
        fixtures.release.clear()
        timeout = e.request(url + '/route', {'request': 'hold'})
        e.require(timeout['status'] == 504, 'held upstream did not reach deadline')
        if systemd:
            command('systemctl', '--user', 'kill', '--signal=SIGKILL', '--kill-whom=main', name + '.service')
            command('systemctl', '--user', 'stop', name + '.service')
        else:
            process.kill()
            e.require(process.wait(timeout=5) == -signal.SIGKILL, 'forced stop did not kill the installed process')
            process = None
        fixtures.release.set()
        start()
        uncertain = e.request(url + '/status')['body']
        e.require(uncertain['jev_calls_reserved'] == 2 and uncertain['request_journal']['pending'] == 1,
                  'restart discarded uncertain work or a spent reservation')
        ready = e.request(url + '/ready')
        e.require(ready['status'] == 503, 'unresolved upstream unexpectedly admits new work')
        events = len(fixtures.events)
        e.require(e.request(url + '/route', {'request': 'coding'})['status'] == 503,
                  'restart bypassed unresolved admission charge')
        e.require(len(fixtures.events) == events, 'blocked route reached upstream')
        stop()
        revised['tracking_limit'] += 1
        next_config.write_text(json.dumps(revised))
        budget_before = budget_path.read_bytes()
        journal_before = journal_path.read_bytes()
        refused_archive = destination / 'state/refused.archive'
        refused_checkpoint = destination / 'state/refused.checkpoint'
        refused = subprocess.run([tool, str(active_config), str(refused_archive), str(refused_checkpoint),
                                  '--migrate-to', str(next_config)], capture_output=True, timeout=5)
        e.require(refused.returncode != 0 and b'unresolved' in refused.stderr,
                  'scope migration accepted unresolved work')
        e.require(not refused_archive.exists() and not refused_checkpoint.exists(),
                  'refused migration created artifacts')
        e.require(budget_path.read_bytes() == budget_before and journal_path.read_bytes() == journal_before,
                  'refused migration changed durable state')
        result = {'passed': True, 'systemd': systemd, 'live_provider_calls': 0, 'environment_file_verified': systemd,
                  'checks': ['private installation', 'reinstall refusal', 'existing-state refusal',
                             'service syntax', 'quiescent migration', 'read-only inspection', 'uncertain migration refusal', 'duplicate owner refusal', 'in-flight SIGTERM drain',
                             'completed accounting restart', 'unresolved accounting after forced death', 'no blocked dispatch'],
                  'clean_restart': clean, 'uncertain_restart': uncertain, 'readiness': ready}
    finally:
        fixtures.release.set()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        try:
            if linked:
                command('systemctl', '--user', 'stop', name + '.service')
                command('systemctl', '--user', 'disable', name + '.service')
                command('systemctl', '--user', 'daemon-reload')
        finally:
            fixtures.close()
            log.close()
            (output / 'commands.json').write_text(json.dumps(records, indent=2) + '\n')
            (output / 'fixture-events.json').write_text(json.dumps(fixtures.events, indent=2) + '\n')
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    for name in ('scripts/install_service.py', 'scripts/deployment_e2e.py', 'scripts/gateway_e2e.py',
                 'Cargo.toml', 'Cargo.lock'):
        copy = output / 'source' / name
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes((e.ROOT / name).read_bytes())
    (output / 'SHA256SUMS.json').write_text(json.dumps({str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.rglob('*')) if p.is_file()}, indent=2) + '\n')
    print('PASS: installed deployment lifecycle' + (' through user systemd' if systemd else ' in foreground'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--systemd', action='store_true')
    args = parser.parse_args()
    run(args.output.resolve(), args.binary.resolve(), args.systemd)
