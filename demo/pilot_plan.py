#!/usr/bin/env python3
"""Bind a two-task text/OCR pilot to priced routes. Offline; never starts services."""
import argparse
import json
from pathlib import Path
from corpus import private_write
from pricing_quote import plan
from recording import canonical, digest
from review import load_text
from review_link import read, parse


def inputs(corpus,tasks):
    corpus=Path(corpus);raw=read(tasks,8*1024*1024);prepared=parse(raw)
    manifest_raw=read(corpus/'manifest.json',4*1024*1024);manifest=parse(manifest_raw)
    if (prepared.get('status')!='prepared_not_executed' or manifest.get('complete') is not True or
            prepared['corpus_manifest_sha256']!=digest(manifest_raw) or len(prepared['tasks'])!=2 or
            prepared['exceptions']):raise ValueError('exactly two fully prepared tasks required')
    seen=set()
    for task in prepared['tasks']:
        documents=[d for d in manifest['documents'] if d['document_id']==task['document_id']]
        if len(documents)!=1:raise ValueError('ambiguous pilot document')
        document=documents[0];load_text(corpus,document)
        expected=digest(json.dumps([document['document_id'],document['source_sha256'],prepared['protocol_sha256']]).encode())
        if (task['task_id']!=expected or expected in seen or task['source_sha256']!=document['source_sha256'] or
                task['family_id']!=document['family_id'] or digest(task['request'].encode())!=task['request_sha256'] or
                len(json.dumps({'request':task['request']}).encode())>16384):
            raise ValueError('pilot task binding or body bound mismatch')
        seen.add(expected)
    return raw,manifest_raw


def configs(root,quote):
    root=Path(root).resolve()
    adapter={'bind':'127.0.0.1:8179','mode':'live','url':'https://openrouter.ai/api/v1/chat/completions',
             'journal_path':str(root/'generation.jsonl'),'deadline_ms':8000,'max_request_bytes':16384,
             'max_response_bytes':65536,'admission_limit':1,'max_calls':2,
             'routes':{name:{'model':q['model'],'provider':q['provider'],'max_tokens':q['requested_max_tokens']}
                       for name,q in quote['routes'].items()}}
    gateway={'bind':'127.0.0.1:8178','mode':'live','jev_url':'https://api.typesafe.ai/v1/systemone',
             'rubric_path':str(root/'rubric.json'),'deadline_ms':10000,'max_request_bytes':16384,
             'max_response_bytes':65536,'admission_limit':1,'tracking_limit':16,'uncertainty_ttl_ms':1000,
             'max_jev_calls':2,'budget_path':str(root/'jev.budget'),'request_journal_path':str(root/'requests.journal'),
             'handlers':{name:['http://127.0.0.1:8179/generate/'+name] for name in quote['routes']}}
    return {'adapter.json':adapter,'gateway.json':gateway}


def create(corpus,tasks,sources,rubric,output,*,now=None):
    output=Path(output).resolve();corpus=Path(corpus).resolve();tasks=Path(tasks).resolve()
    sources=Path(sources).resolve()
    tasks_raw,manifest_raw=inputs(corpus,tasks)
    quote=plan(sources,now=now);rubric_raw=read(rubric,65536);policy=parse(rubric_raw)
    if (policy['model']!=quote['decision']['model'] or
            set(policy['questions']['route']['criteria'])!=set(quote['routes'])|{'fallback'}):
        raise ValueError('rubric does not match priced decision model and routes')
    files={'tasks.json':tasks_raw,'rubric.json':rubric_raw,'pricing.json':canonical(quote)}
    files.update({name:canonical(value) for name,value in configs(output,quote).items()})
    result={'schema_version':1,'status':'prepared_not_authorized','corpus':str(corpus),'pricing_sources':str(sources),
            'corpus_manifest_sha256':digest(manifest_raw),'files':{name:digest(raw) for name,raw in files.items()},
            'task_count':2,'workers':1,'max_jev_calls':2,'max_generation_calls':2,'automatic_retries':0,
            'decision_transport':'typesafe_direct','estimate_usd':quote['per_task_reservation_usd'],
            'total_reservation_usd':quote['two_task_reservation_usd'],'expires_at':quote['expires_at'],
            'selected_allowance_usd':None,'provider_calls':0,
            'limits':['Reservation estimates are not a guaranteed invoice ceiling.',
                      'Generation receipts do not settle the combined Jev/generation cost.',
                      'This plan initializes no budget, journal, service or credential.']}
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    for name,raw in files.items():private_write(output/name,raw)
    private_write(output/'plan.json',canonical(result)+b'\n')
    return result


def verify(directory,*,now=None):
    root=Path(directory).resolve();manifest=parse(read(root/'plan.json',65536))
    names={'tasks.json','rubric.json','pricing.json','adapter.json','gateway.json'}
    if (manifest.get('schema_version')!=1 or manifest.get('status')!='prepared_not_authorized' or
            set(manifest['files'])!=names or manifest['selected_allowance_usd'] is not None):
        raise ValueError('invalid offline pilot plan')
    files={name:read(root/name,8*1024*1024 if name=='tasks.json' else 65536) for name in names}
    if any(digest(raw)!=manifest['files'][name] for name,raw in files.items()):raise ValueError('pilot config changed')
    quote=plan(manifest['pricing_sources'],now=now)
    if canonical(quote)!=files['pricing.json']:raise ValueError('pricing changed or no longer matches plan')
    _,corpus_raw=inputs(manifest['corpus'],root/'tasks.json')
    if digest(corpus_raw)!=manifest['corpus_manifest_sha256']:raise ValueError('pilot corpus changed')
    policy=parse(files['rubric.json'])
    if policy['model']!=quote['decision']['model'] or set(policy['questions']['route']['criteria'])!=set(quote['routes'])|{'fallback'}:
        raise ValueError('pilot rubric catalog changed')
    if any(canonical(value)!=files[name] for name,value in configs(root,quote).items()):raise ValueError('runtime configuration differs from priced plan')
    if (manifest['task_count']!=2 or manifest['workers']!=1 or manifest['max_jev_calls']!=2 or
            manifest['max_generation_calls']!=2 or manifest['automatic_retries']!=0 or
            manifest['estimate_usd']!=quote['per_task_reservation_usd'] or
            manifest['total_reservation_usd']!=quote['two_task_reservation_usd'] or
            manifest['expires_at']!=quote['expires_at'] or manifest['decision_transport']!='typesafe_direct'):
        raise ValueError('pilot admission limits changed')
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    new=sub.add_parser('create')
    for name in ('corpus','tasks','sources','rubric','output'):new.add_argument(name,type=Path)
    check=sub.add_parser('verify');check.add_argument('directory',type=Path)
    a=p.parse_args();result=verify(a.directory) if a.command=='verify' else create(a.corpus,a.tasks,a.sources,a.rubric,a.output)
    print(json.dumps({key:result[key] for key in ('status','task_count','total_reservation_usd','selected_allowance_usd','provider_calls')}))
