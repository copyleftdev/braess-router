#!/usr/bin/env python3
"""Prepare private, bounded tasks from a corpus manifest and explicit review protocol.

No routing or model calls. Oversized documents remain in a visible exception list.
"""
import argparse
import hashlib
import json
from pathlib import Path
from corpus import private_write
from review import prompt


def prepare(corpus, protocol_path, output):
    corpus, protocol_path, output = Path(corpus), Path(protocol_path), Path(output)
    raw = protocol_path.read_bytes()
    if len(raw) > 16384:
        raise ValueError('protocol too large')
    protocol = json.loads(raw)
    if (set(protocol) != {'id','version','production_request','scope'} or
            not isinstance(protocol['id'],str) or not 1 <= len(protocol['id']) <= 128 or
            not isinstance(protocol['version'],str) or not 1 <= len(protocol['version']) <= 128 or
            protocol['scope'] not in ('synthetic_protocol', 'reviewed_production_request')):
        raise ValueError('explicit versioned review protocol required')
    manifest_raw = (corpus/'manifest.json').read_bytes()
    if len(manifest_raw) > 4*1024*1024:
        raise ValueError('manifest too large')
    manifest = json.loads(manifest_raw)
    if manifest.get('complete') is not True or not 1 <= len(manifest['documents']) <= 400:
        raise ValueError('completed bounded corpus manifest required')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    tasks, exceptions = [], []
    ids = set()
    for document in manifest['documents']:
        if document['document_id'] in ids:
            raise ValueError('duplicate source document ID')
        ids.add(document['document_id'])
        try:
            request = prompt(corpus, document, production_request=protocol['production_request'])
        except ValueError as error:
            if str(error) != 'review request exceeds initial gateway body bound; chunking required':
                raise
            exceptions.append({'document_id':document['document_id'],'reason':'requires_chunking'})
            continue
        task_id = hashlib.sha256(json.dumps([document['document_id'],document['source_sha256'],hashlib.sha256(raw).hexdigest()]).encode()).hexdigest()
        tasks.append({'task_id':task_id,'document_id':document['document_id'],
                      'family_id':document['family_id'], 'source_sha256':document['source_sha256'],
                      'protocol_id':protocol['id'], 'protocol_version':protocol['version'],
                      'request_sha256':hashlib.sha256(request.encode()).hexdigest(), 'request':request})
    result = {'schema_version':1, 'status':'prepared_not_executed',
              'protocol_sha256':hashlib.sha256(raw).hexdigest(), 'protocol_scope':protocol['scope'],
              'corpus_manifest_sha256':hashlib.sha256(manifest_raw).hexdigest(),
              'tasks':tasks,'exceptions':exceptions,'provider_calls':0}
    private_write(output/'tasks.json',json.dumps(result,indent=2).encode()+b'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus',type=Path);parser.add_argument('protocol',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    result=prepare(args.corpus,args.protocol,args.output)
    print(json.dumps({'status':result['status'],'tasks':len(result['tasks']),'exceptions':len(result['exceptions']),'provider_calls':0}))
