#!/usr/bin/env python3
"""Execute one explicitly funded, preflight-verified pilot. No retries or resume."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
from budget import Budget, usd_units, usd_string
from fleet import durable_write, run as run_fleet
from pilot_plan import verify
from recording import canonical, digest

BINARIES=('braess-router','braess-openrouter','braess-budget-init','braess-journal-init')
SOURCES=('pilot_run.py','pilot_plan.py','pricing_quote.py','fleet.py','observe.py',
         'recording.py','review.py','corpus.py','ocr_evidence.py','budget.py','routing_trace.py')
STATE=('execution.json','execution-summary.json','run','spend','generation.jsonl','jev.budget','requests.journal')


def child_environment(key=None,value=None):
    result={name:os.environ[name] for name in ('PATH','HOME','LANG','LC_ALL','TZ') if name in os.environ}
    if key:result[key]=value
    return result


def preflight(root,binaries,allowance):
    root=Path(root).resolve();binaries=Path(binaries).resolve()
    manifest=verify(root)
    if usd_units(allowance)<usd_units(manifest['total_reservation_usd']):
        raise ValueError('allowance cannot cover the two-task reservation')
    if any((root/name).exists() or (root/name).is_symlink() for name in STATE):
        raise ValueError('pilot already attempted or contains initialized state; no resume')
    hashes={}
    for name in BINARIES:
        path=binaries/name
        if path.is_symlink() or not path.is_file() or not os.access(path,os.X_OK) or path.stat().st_size>256*1024*1024:
            raise ValueError('expected executable unavailable')
        hashes[name]=digest(path.read_bytes())
    return manifest,hashes


def ports_available():
    # This catches occupied endpoints before any child starts. Child liveness and
    # startup failures are checked again; loopback is a trusted-host boundary.
    sockets=[]
    try:
        for port in (8178,8179):
            s=socket.socket();sockets.append(s);s.bind(('127.0.0.1',port))
    finally:
        for s in sockets:s.close()


def execute(directory,binaries,*,allowance_usd):
    root=Path(directory).resolve();binaries=Path(binaries).resolve()
    manifest,binary_hashes=preflight(root,binaries,allowance_usd)
    # Only explicitly named credentials reach their respective child; no dotenv
    # parsing, shell interpolation, or wholesale environment inheritance.
    keys={name:os.environ.get(name) for name in ('TYPESAFE_API_KEY','OPENROUTER_API_KEY')}
    if any(not value or len(value)>8192 or any(ord(c)<33 or ord(c)>126 for c in value) for value in keys.values()):
        raise ValueError('both provider credentials must be supplied in the environment')
    ports_available()
    claim={'schema_version':1,'status':'attempt_started','at':datetime.now(timezone.utc).isoformat(),
           'plan_sha256':digest((root/'plan.json').read_bytes()),'configuration_sha256':manifest['files'],
           'binary_sha256':binary_hashes,'coordinator_source_sha256':{
               name:digest((Path(__file__).parent/name).read_bytes()) for name in SOURCES},
           'allowance_usd':usd_string(usd_units(allowance_usd)),
           'per_task_reservation_usd':manifest['estimate_usd'],'workers':1,'max_attempts':2,
           'credential_names':sorted(keys),'credential_values_recorded':False}
    # Create-only durable claim prevents restarting this plan after any attempt,
    # including initialization failure or a crash with unknown upstream outcome.
    durable_write(root/'execution.json',canonical(claim))
    processes=[];logs=[];stage='initialization';summary=None
    try:
        ledger=Budget.create(root/'spend',cap_usd=allowance_usd,max_attempts=2,
                             pricing_sha256=manifest['files']['pricing.json'])
        commands=[('braess-openrouter',['--config',str(root/'adapter.json'),'--init']),
                  ('braess-budget-init',[str(root/'jev.budget'),'2']),
                  ('braess-journal-init',[str(root/'gateway.json')])]
        for binary,args in commands:
            subprocess.run([str(binaries/binary),*args],env=child_environment(),
                           check=True,timeout=10,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        def start(binary,config,port,key):
            fd=os.open(root/(binary+'.log'),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            log=os.fdopen(fd,'wb');logs.append(log)
            process=subprocess.Popen([str(binaries/binary),'--config',str(root/config)],
                env=child_environment(key,keys[key]),stdout=log,stderr=log)
            processes.append(process)
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                if process.poll() is not None:raise ValueError('pilot service exited during startup')
                try:
                    with opener.open(f'http://127.0.0.1:{port}/health',timeout=.2) as response:
                        if response.status==200 and process.poll() is None:return
                except OSError:pass
                time.sleep(.05)
            raise ValueError('pilot service startup deadline exceeded')
        stage='startup'
        start('braess-openrouter','adapter.json',8179,'OPENROUTER_API_KEY')
        start('braess-router','gateway.json',8178,'TYPESAFE_API_KEY')
        # Recheck the evidence immediately before fleet admission. State files
        # are expected now, so use plan verification rather than preflight.
        if verify(root)!=manifest:raise ValueError('plan changed during startup')
        if digest((root/'plan.json').read_bytes())!=claim['plan_sha256']:
            raise ValueError('plan bytes changed during startup')
        if any(digest((binaries/name).read_bytes())!=value for name,value in binary_hashes.items()):
            raise ValueError('pilot binary changed during startup')
        stage='fleet'
        result=run_fleet(manifest['corpus'],root/'tasks.json',root/'run',
                         gateway_url='http://127.0.0.1:8178/route',budget=ledger,
                         estimate_usd=manifest['estimate_usd'],scope='live',workers=1)
        summary={'status':'fleet_finished','run_id':result['run']['run_id'],
                 'summary':result['summary'],'budget':ledger.inspect(),
                 'billing_reconciled':False,'publication_approved':False}
        return summary
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
        for log in logs:log.close()
        if summary is None:summary={'status':'attempt_aborted','stage':stage,'outcome':'may be unknown; reservations retained','retry_permitted':False}
        durable_write(root/'execution-summary.json',canonical(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('plan',type=Path);p.add_argument('binaries',type=Path)
    p.add_argument('--allowance-usd',required=True)
    a=p.parse_args()
    try:
        result=execute(a.plan,a.binaries,allowance_usd=a.allowance_usd)
        print(canonical(result).decode())
    except Exception:
        # Provider logs/captures stay private. Exception strings are not an output channel.
        raise SystemExit('pilot did not complete; inspect private execution state before any further action') from None
