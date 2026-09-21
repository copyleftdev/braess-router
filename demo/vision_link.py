#!/usr/bin/env python3
"""Bind a received image reference to exact provisioned scan pages; no inference."""
import argparse
from pathlib import Path
from corpus import private_write
from inspector_assets import load_bundle
from private_replay import load_recording
from recording import canonical, digest
from review_link import read, parse


def link(recording, reference, inspector, task_id):
    replay=load_recording(recording)
    raw=read(reference,65536);ref=parse(raw)
    required={'schema_version','kind','document_id','native_source_sha256','inspector_manifest_sha256','prompt','pages'}
    if (not isinstance(ref,dict) or set(ref)!=required or type(ref['schema_version']) is not int or
            ref['schema_version']!=1 or ref['kind']!='vision_reference_v1' or
            not isinstance(ref['prompt'],str) or not ref['prompt'].strip() or len(ref['prompt'].encode())>8192 or
            not isinstance(ref['pages'],list) or not 1<=len(ref['pages'])<=8):
        raise ValueError('invalid bounded image reference')
    assets=load_bundle(inspector)
    manifest_raw=assets['evidence/manifest.json'][0];manifest=parse(manifest_raw)
    if (digest(manifest_raw)!=ref['inspector_manifest_sha256'] or
            manifest['document_id']!=ref['document_id'] or
            manifest['native_source_sha256']!=ref['native_source_sha256']):
        raise ValueError('image reference does not bind this inspector')
    selected=[];seen=set();total=0
    for item in ref['pages']:
        if (not isinstance(item,dict) or set(item)!={'page','sha256','bytes','width','height'} or
                any(type(item[k]) is not int or item[k]<=0 for k in ('page','bytes','width','height')) or
                item['page']>len(manifest['pages']) or item['page'] in seen):
            raise ValueError('invalid image page selection')
        seen.add(item['page']);page=manifest['pages'][item['page']-1]
        pixels=assets['evidence/'+page['file']][0];total+=len(pixels)
        expected={k:page[k] for k in ('page','sha256','width','height')} | {'bytes':len(pixels)}
        if item!=expected or total>8*1024*1024:raise ValueError('image page bytes or geometry mismatch')
        selected.append(expected)
    events=[e for e in replay['events'] if e['task_id']==task_id]
    queued=[e for e in events if e['kind']=='task_queued']
    responses=[e for e in events if e['kind']=='response_received']
    evidence={'reference_sha256':digest(raw),'image_sha256':[p['sha256'] for p in selected]}
    if (len(queued)!=1 or queued[0]['data']['document_id']!=ref['document_id'] or
            len(responses)!=1 or responses[0]['data'].get('generation_input_evidence')!=evidence):
        raise ValueError('recorded task does not carry this exact image receipt')
    event=responses[0]
    return {'schema_version':1,'association':'verified_image_input_receipt',
            'run_id':replay['run']['run_id'],'scope':replay['run']['scope'],'task_id':task_id,
            'document_id':ref['document_id'],'native_source_sha256':ref['native_source_sha256'],
            'inspector_manifest_sha256':ref['inspector_manifest_sha256'],
            'reference_sha256':digest(raw),'pages':selected,'response_event_sha256':event['sha256'],
            'input_visibility_after_elapsed_ns':event['elapsed_ns'],
            'publication_approved':False,'model_understanding_established':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('recording','reference','inspector'):p.add_argument(name,type=Path)
    p.add_argument('task_id');p.add_argument('output',type=Path)
    a=p.parse_args();result=link(a.recording,a.reference,a.inspector,a.task_id)
    private_write(a.output,canonical(result)+b'\n')
    print('Verified image receipt and ordered source-page association; no inference performed.')
