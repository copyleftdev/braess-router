#!/usr/bin/env python3
"""Bounded review execution through Braess with private response artifacts.

No direct provider credentials. Live operation requires an existing budget ledger.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
from budget import Budget, BudgetError
from corpus import private_write, SHA
from observe import observe
from recording import Recorder, canonical, digest, verify
from review import validate


def durable_write(path, wire):
    private_write(path, wire)
    with path.open('rb') as handle:
        os.fsync(handle.fileno())
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def run(corpus, tasks_path, output, *, gateway_url, budget, estimate_usd, scope, workers=2):
    if not isinstance(budget, Budget):
        raise ValueError('fleet execution requires a shared budget ledger')
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError('worker count must be 1..4')
    corpus, tasks_path, output = Path(corpus), Path(tasks_path), Path(output)
    if tasks_path.stat().st_size > 8*1024*1024:
        raise ValueError('prepared task bundle too large')
    tasks_raw=tasks_path.read_bytes(); prepared=json.loads(tasks_raw)
    manifest_raw=(corpus/'manifest.json').read_bytes()
    if len(manifest_raw)>4*1024*1024 or digest(manifest_raw)!=prepared['corpus_manifest_sha256']:
        raise ValueError('corpus manifest mismatch')
    manifest=json.loads(manifest_raw)
    documents={d['document_id']:d for d in manifest['documents']}
    tasks=prepared['tasks']
    if prepared['status']!='prepared_not_executed' or not 1<=len(tasks)<=400:
        raise ValueError('bounded prepared tasks required')
    seen=set()
    for task in tasks:
        if (not isinstance(task['task_id'],str) or not SHA.fullmatch(task['task_id']) or
                task['task_id'] in seen or task['document_id'] not in documents):
            raise ValueError('invalid prepared task identity')
        seen.add(task['task_id'])
        doc=documents[task['document_id']]
        if digest(task['request'].encode())!=task['request_sha256'] or doc['source_sha256']!=task['source_sha256']:
            raise ValueError('prepared request mismatch')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    (output/'private').mkdir(mode=0o700)
    recorder=Recorder(output/'recording',scope=scope,metadata={'corpus_manifest_sha256':digest(manifest_raw)})
    durable_write(output/'input-manifest.json',canonical({'tasks_sha256':digest(tasks_raw),
                  'corpus_manifest_sha256':digest(manifest_raw),'protocol_sha256':prepared['protocol_sha256'],
                  'protocol_scope':prepared['protocol_scope'],'workers':workers,'prepared_exceptions':prepared['exceptions']}))
    def worker(task):
        task_id=task['task_id']
        document=documents[task['document_id']]
        def accept(body, raw):
            # Save even an invalid model response for private debugging, never public replay.
            durable_write(output/'private'/(task_id+'.response.json'),raw)
            answer=body['handler_response']['answer']
            if not isinstance(answer,str):raise ValueError('review answer must be text JSON')
            result=validate(corpus,document,answer.encode())
            wire=canonical(result)
            durable_write(output/'private'/(task_id+'.review.json'),wire)
            return {'review_sha256':digest(wire),'finding_count':len(result['findings'])}
        try:
            observe(recorder,task_id,gateway_url,task['request'],budget=budget,
                    estimate_usd=estimate_usd,on_result=accept)
        except BudgetError:
            recorder.append('task_deferred',task_id,reason='budget_admission_refused')
    try:
        for task in tasks:
            recorder.append('task_queued',task['task_id'],document_id=task['document_id'],
                            family_id=task['family_id'],modality='text')
        with ThreadPoolExecutor(max_workers=workers) as pool:
            # Input is bounded above; no recursive tasks or automatic retries.
            for result in pool.map(worker,tasks):
                pass
    finally:
        recorder.close()
    result=verify(output/'recording')
    durable_write(output/'result.json',canonical({'summary':result['summary'],
                  'budget':budget.inspect(),'scope':scope,'review_accuracy':'not_established'}))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus',type=Path);parser.add_argument('tasks',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--gateway-url',required=True);parser.add_argument('--budget',type=Path,required=True)
    parser.add_argument('--pricing-sha256',required=True);parser.add_argument('--estimate-usd',required=True)
    parser.add_argument('--scope',choices=['live','synthetic'],required=True);parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    result=run(args.corpus,args.tasks,args.output,gateway_url=args.gateway_url,
               budget=Budget(args.budget,pricing_sha256=args.pricing_sha256),estimate_usd=args.estimate_usd,
               scope=args.scope,workers=args.workers)
    print(json.dumps(result['summary']))
