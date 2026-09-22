#!/usr/bin/env python3
"""Prepare a private human-review queue and bind supplied decisions to its evidence."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from corpus import private_write
from private_replay import load_recording
from recording import canonical, digest
from review_link import link, read, parse
from run_metrics import source_hashes


def queue(corpus,tasks,run):
    run=Path(run);before=source_hashes(run/'recording')
    replay=load_recording(run/'recording');grouped={}
    for event in replay['events']:grouped.setdefault(event['task_id'],[]).append(event)
    entries=[]
    for task_id,events in grouped.items():
        queued=events[0]['data'];last=events[-1]
        validated=last['kind']=='task_completed' and last['data']['outcome']=='review_validated'
        association=link(corpus,tasks,run,task_id) if validated else None
        entries.append({'task_id':task_id,'document_id':queued['document_id'],
            'family_id':queued['family_id'],'observed_state':last['kind'],
            'observed_outcome':last['data'].get('outcome'),
            'observed_reason':last['data'].get('error',last['data'].get('reason')),
            'last_event_sha256':last['sha256'],'status':'awaiting_human',
            'review_sha256':association['review_sha256'] if association else None,
            'review':association['review'] if association else None,
            'decision':None})
    if source_hashes(run/'recording')!=before:raise ValueError('recording changed during queue assembly')
    return {'schema_version':1,'run_id':replay['run']['run_id'],'scope':replay['run']['scope'],
        'source_hashes':before,'publication_approved':False,'redactions_approved':False,
        'purpose':'human assessment of recorded provisional reviews; not an inferred gold standard',
        'entries':entries}


def prepare(corpus,tasks,run,output):
    result=queue(corpus,tasks,run)
    raw=canonical(result)+b'\n'
    if len(raw)>16*1024*1024:raise ValueError('human-review queue size bound exceeded')
    private_write(Path(output),raw);return result


def resolve(corpus,tasks,run,queue_path,decisions_path,output):
    raw=read(queue_path,16*1024*1024);expected=queue(corpus,tasks,run)
    if parse(raw)!=expected:raise ValueError('queue no longer matches verified run and reviews')
    supplied=read(decisions_path,1024*1024);decisions=parse(supplied)
    if (not isinstance(decisions,dict) or set(decisions)!={'queue_sha256','reviewer_id','decisions'} or
            decisions['queue_sha256']!=digest(raw) or not isinstance(decisions['reviewer_id'],str) or
            not 1<=len(decisions['reviewer_id'])<=128 or any(ord(c)<33 or ord(c)>126 for c in decisions['reviewer_id']) or
            not isinstance(decisions['decisions'],list) or not 1<=len(decisions['decisions'])<=len(expected['entries'])):
        raise ValueError('bounded supplied decisions and exact queue hash required')
    by_id={entry['task_id']:entry for entry in expected['entries']};seen=set()
    for decision in decisions['decisions']:
        if not isinstance(decision,dict) or set(decision)!={'task_id','review_sha256','outcome','note'}:
            raise ValueError('invalid human decision shape')
        task=decision['task_id']
        if not isinstance(task,str) or task not in by_id or task in seen:raise ValueError('unknown or duplicate task')
        seen.add(task);entry=by_id[task]
        if (decision['review_sha256']!=entry['review_sha256'] or
                decision['outcome'] not in ('confirm_review','reject_review','needs_more_context') or
                not isinstance(decision['note'],str) or not decision['note'].strip() or len(decision['note'].encode())>2048):
            raise ValueError('decision must bind the exact review with a bounded note')
        if entry['review'] is None and decision['outcome']!='needs_more_context':
            raise ValueError('an unvalidated or absent review cannot be confirmed or rejected')
        entry['decision']=dict(decision)
        entry['status']='needs_more_context' if decision['outcome']=='needs_more_context' else 'assessed'
    report={**expected,'queue_sha256':digest(raw),'decisions_sha256':digest(supplied),
        'reviewer_id':decisions['reviewer_id'],'reviewer_identity_authenticated':False,
        'recorded_at':datetime.now(timezone.utc).isoformat(),
        'assessed':sum(e['status']=='assessed' for e in expected['entries']),
        'unresolved':sum(e['status']!='assessed' for e in expected['entries'])}
    raw=canonical(report)+b'\n'
    if len(raw)>16*1024*1024:raise ValueError('assessment size bound exceeded')
    private_write(Path(output),raw);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for command in ('prepare','resolve'):
        parser=sub.add_parser(command)
        for name in ('corpus','tasks','run'):parser.add_argument(name,type=Path)
        if command=='resolve':
            parser.add_argument('queue',type=Path);parser.add_argument('decisions',type=Path)
        parser.add_argument('output',type=Path)
    a=p.parse_args()
    result=(prepare(a.corpus,a.tasks,a.run,a.output) if a.command=='prepare' else
            resolve(a.corpus,a.tasks,a.run,a.queue,a.decisions,a.output))
    print(canonical({'run_id':result['run_id'],'tasks':len(result['entries']),
                     'assessed':result.get('assessed',0),'unresolved':result.get('unresolved',len(result['entries']))}).decode())
