#!/usr/bin/env python3
"""Freeze a verified private replay, viewer and analysis into one offline directory."""
import argparse
import hashlib
import json
from pathlib import Path
from corpus import private_write
from inspector_assets import load_bundle
from private_replay import assets, image_execution_assets
from recording import canonical
from run_metrics import metrics
from serve import ASSETS


def build(corpus, tasks, run, output, *, inspector=None):
    def assemble():
        content=assets(corpus,tasks,run,inspector=inspector)
        if inspector:content.update(load_bundle(inspector))
        return content
    return freeze(Path(run)/'recording',output,assemble)


def build_execution(recording,reference,inspector,task_id,output):
    return freeze(recording,output,lambda:image_execution_assets(recording,reference,inspector,task_id))


def freeze(recording,output,assemble):
    output=Path(output)
    verified=assemble()
    content=dict(verified)
    for name, (source, mime) in ASSETS.items():
        if name != 'replay.json':
            content[name] = (source.read_bytes(), mime)
    if sum(len(body) for body, _ in content.values()) > 192*1024*1024:
        raise ValueError('replay package size bound exceeded')
    replay = json.loads(content['replay.json'][0])
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    analysis = metrics(recording, output/'route-metrics.json')
    if analysis['run_id'] != replay['run']['run_id']:
        raise ValueError('analysis and replay run mismatch')
    # The analysis verifier binds exact log bytes. Reassemble to ensure the
    # source associations did not change while the package was being prepared.
    if assemble() != verified:
        raise ValueError('replay inputs changed during packaging')
    entries = {}
    for name, (body, mime) in content.items():
        target = output/name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        private_write(target, body)
        entries[name] = {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body), 'media_type': mime}
    raw = (output/'route-metrics.json').read_bytes()
    entries['route-metrics.json'] = {'sha256': hashlib.sha256(raw).hexdigest(),
                                   'bytes': len(raw), 'media_type': 'application/json'}
    manifest = {'schema_version': 1, 'run_id': replay['run']['run_id'], 'scope': replay['run']['scope'],
                'purpose': 'private frozen replay and film input', 'publication_approved': False,
                'contains_private_source_content': True, 'provider_calls_during_packaging': 0,
                'packager_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'files': entries,
                'integrity_scope': 'hashes bind bytes; they do not authenticate a rewritten package',
                'omitted': ['credentials', 'raw provider responses', 'native corpus objects', 'budget databases']}
    private_write(output/'package.json', canonical(manifest)+b'\n')
    return manifest


def verify(directory):
    directory = Path(directory)
    path = directory/'package.json'
    if path.is_symlink() or path.stat().st_size > 1024*1024:
        raise ValueError('invalid package manifest')
    manifest = json.loads(path.read_bytes())
    files = manifest['files']
    if manifest.get('schema_version') != 1 or not isinstance(files, dict) or not 1 <= len(files) <= 64:
        raise ValueError('invalid package file count')
    total = 0
    for name, entry in files.items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or str(relative) != name:
            raise ValueError('invalid package path')
        target = directory/relative
        if any(p.is_symlink() for p in [target, *target.parents] if p != directory.parent):
            raise ValueError('symlink in package')
        size = target.stat().st_size
        total += size
        if size != entry['bytes'] or total > 192*1024*1024:
            raise ValueError('package size mismatch')
        if hashlib.sha256(target.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('package hash mismatch')
    actual = {str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file() or p.is_symlink()}
    if actual != {*files, 'package.json'}:
        raise ValueError('unexpected package files')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('build')
    for name in ('corpus', 'tasks', 'run', 'output'):
        create.add_argument(name, type=Path)
    create.add_argument('--inspector', type=Path)
    execution=commands.add_parser('build-execution')
    for name in ('recording','reference','inspector'):execution.add_argument(name,type=Path)
    execution.add_argument('task_id');execution.add_argument('output',type=Path)
    check = commands.add_parser('verify'); check.add_argument('directory', type=Path)
    args = parser.parse_args()
    if args.command=='build':result=build(args.corpus,args.tasks,args.run,args.output,inspector=args.inspector)
    elif args.command=='build-execution':result=build_execution(args.recording,args.reference,args.inspector,args.task_id,args.output)
    else:result=verify(args.directory)
    print(canonical({'run_id': result['run_id'], 'scope': result['scope'], 'files': len(result['files']),
                     'publication_approved': result['publication_approved']}).decode())
