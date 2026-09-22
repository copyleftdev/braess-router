#!/usr/bin/env python3
"""Verify a private recording-to-source association without inference or publication."""
import argparse
import json
import tempfile
from pathlib import Path
from corpus import SHA, private_write
from recording import canonical, digest, verify
from review import validate, strict_object


def read(path, maximum):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>maximum:
        raise ValueError('invalid review-link input')
    return path.read_bytes()


def parse(raw):
    return json.loads(raw,object_pairs_hook=strict_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def link(corpus, tasks_path, run, task_id, *, inspector=None):
    if not isinstance(task_id,str) or not SHA.fullmatch(task_id):
        raise ValueError('invalid task identity')
    corpus,run=Path(corpus),Path(run)
    tasks_raw=read(tasks_path,8*1024*1024);prepared=parse(tasks_raw)
    corpus_raw=read(corpus/'manifest.json',4*1024*1024);manifest=parse(corpus_raw)
    input_raw=read(run/'input-manifest.json',1024*1024);inputs=parse(input_raw)
    if (inputs['tasks_sha256']!=digest(tasks_raw) or
            inputs['corpus_manifest_sha256']!=digest(corpus_raw) or
            prepared['corpus_manifest_sha256']!=digest(corpus_raw) or
            inputs['protocol_sha256']!=prepared['protocol_sha256'] or
            inputs['protocol_scope']!=prepared['protocol_scope'] or
            manifest.get('complete') is not True or prepared.get('status')!='prepared_not_executed'):
        raise ValueError('run input binding mismatch')
    protocol=prepared['protocol_sha256']
    if not isinstance(protocol,str) or not SHA.fullmatch(protocol):raise ValueError('invalid protocol hash')
    matches=[t for t in prepared['tasks'] if t['task_id']==task_id]
    if len(matches)!=1:raise ValueError('one prepared task required')
    task=matches[0]
    docs=[d for d in manifest['documents'] if d['document_id']==task['document_id']]
    if len(docs)!=1:raise ValueError('one source document required')
    document=docs[0]
    expected_id=digest(json.dumps([document['document_id'],document['source_sha256'],protocol]).encode())
    if (task_id!=expected_id or task['source_sha256']!=document['source_sha256'] or
            task['family_id']!=document['family_id'] or digest(task['request'].encode())!=task['request_sha256']):
        raise ValueError('task source binding mismatch')
    # Bound all recorder files before invoking its chain/state-machine verifier.
    for name,maximum in [('run.json',1024*1024),('seal.json',1024*1024),('events.jsonl',32*1024*1024)]:
        read(run/'recording'/name,maximum)
    recording=verify(run/'recording')
    if recording['run']['provenance'].get('corpus_manifest_sha256')!=digest(corpus_raw):
        raise ValueError('recorded corpus mismatch')
    events=[e for e in recording['events'] if e['task_id']==task_id]
    kinds=['task_queued','request_started','response_received','review_validated','task_completed']
    if [e['kind'] for e in events]!=kinds:
        raise ValueError('task has no completed validated review')
    queued,started,response,reviewed,completed=events
    if (queued['data']['document_id']!=document['document_id'] or
            queued['data']['family_id']!=document['family_id'] or
            queued['data']['modality']!=document.get('modality','text') or
            started['data']['input_sha256']!=digest(json.dumps({'request':task['request']}).encode()) or
            completed['data']['outcome']!='review_validated' or response['data']['http_status']!=200):
        raise ValueError('recorded task binding mismatch')
    response_raw=read(run/'private'/(task_id+'.response.json'),1024*1024)
    review_raw=read(run/'private'/(task_id+'.review.json'),4*1024*1024)
    if digest(response_raw)!=response['data']['response_sha256'] or digest(review_raw)!=reviewed['data']['review_sha256']:
        raise ValueError('recorded artifact hash mismatch')
    body=parse(response_raw)
    if not body.get('route') or body['route']=='fallback' or body['route']!=response['data'].get('route'):
        raise ValueError('response route mismatch')
    answer=body['handler_response']['answer']
    if not isinstance(answer,str):raise ValueError('review answer must be JSON text')
    report=validate(corpus,document,answer.encode())
    if canonical(report)!=review_raw or len(report['findings'])!=reviewed['data']['finding_count']:
        raise ValueError('review cannot be reproduced from response and source')
    inspector_hash=None
    if inspector is not None:
        from inspector_assets import load_bundle
        assets=load_bundle(inspector)
        inspector_raw=assets['evidence/manifest.json'][0];bundle=parse(inspector_raw)
        if document.get('representation')!='ocr_text' or any(bundle.get(k)!=document.get(k) for k in
                ('document_id','source_sha256','native_source_sha256','ocr_mapping_sha256')):
            raise ValueError('inspector refers to a different source')
        # Manifest claims alone cannot prove these pixels/boxes came from the source.
        # Re-render in the existing bounded child and compare the resulting assets.
        from evidence_bundle import build
        with tempfile.TemporaryDirectory(prefix='braess-review-link-') as temporary:
            expected=build(corpus/'manifest.json',document['document_id'],Path(temporary)/'bundle')
            if (bundle['pages']!=expected['pages'] or bundle['text']!=expected['text'] or
                    bundle['words']!=expected['words']):
                raise ValueError('inspector assets do not reproduce from source')
        inspector_hash=digest(inspector_raw)
    return {'schema_version':1,'association':'verified_local_artifact_chain',
            'run_id':recording['run']['run_id'],'scope':recording['run']['scope'],
            'task_id':task_id,'document_id':document['document_id'],'family_id':document['family_id'],
            'source_sha256':document['source_sha256'],
            'native_source_sha256':document.get('native_source_sha256'),
            'ocr_mapping_sha256':document.get('ocr_mapping_sha256'),
            'protocol_sha256':protocol,'protocol_scope':prepared['protocol_scope'],
            'tasks_sha256':digest(tasks_raw),'corpus_manifest_sha256':digest(corpus_raw),
            'input_manifest_sha256':digest(input_raw),'response_sha256':digest(response_raw),
            'review_sha256':digest(review_raw),'inspector_manifest_sha256':inspector_hash,
            'recording_seal_sha256':digest(read(run/'recording/seal.json',1024*1024)),
            'events':[{'kind':e['kind'],'seq':e['seq'],'elapsed_ns':e['elapsed_ns'],'sha256':e['sha256']} for e in events],
            'finding_visibility_after_elapsed_ns':reviewed['elapsed_ns'],
            'response_metadata':response['data'],
            'review':report,'verification_code_sha256':digest(Path(__file__).read_bytes()),
            'authenticity':'not_established_by_hashes','legal_accuracy':'not_established',
            'publication_approved':False,'provider_calls':0}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('corpus','tasks','run'):p.add_argument(name,type=Path)
    p.add_argument('task_id');p.add_argument('output',type=Path)
    p.add_argument('--inspector',type=Path)
    a=p.parse_args();result=link(a.corpus,a.tasks,a.run,a.task_id,inspector=a.inspector)
    private_write(a.output,canonical(result)+b'\n')
    print(json.dumps({'association':result['association'],'scope':result['scope'],
                      'findings':len(result['review']['findings']),'provider_calls':0}))
