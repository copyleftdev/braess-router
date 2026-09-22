#!/usr/bin/env python3
"""Bounded TREC Enron text-rendering ingest. Originals/native media are not inferred."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tarfile

MAX_DOCUMENT = 2 * 1024 * 1024
MAX_SCAN_BYTES = 2 * 1024 * 1024 * 1024
MAX_MEMBERS = 1_000_000
DOC_ID = re.compile(r'[0-9]+\.[0-9]+\.[A-Z0-9]+(?:\.[0-9]+)?\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')
BASE = 'https://trec-legal.umiacs.umd.edu/corpora/trec/legal10/'


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def private_write(path, data):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'wb') as target:
        target.write(data)


def seeds(path):
    if Path(path).stat().st_size > 4*1024*1024:
        raise ValueError('seed file too large')
    result = {}
    with Path(path).open(encoding='utf-8', newline='') as source:
        for row in csv.reader(source):
            if len(row) != 4 or not DOC_ID.fullmatch(row[3]):
                raise ValueError('invalid seed row')
            family = row[0].split('_', 1)[0]
            if not DOC_ID.fullmatch(family) or family.count('.') != 2:
                raise ValueError('invalid family ID')
            topic, assessment = int(row[1]), int(row[2])
            if not 200 <= topic <= 207 or assessment not in (-2, -1, 0, 1):
                raise ValueError('unknown seed judgment')
            label = {'topic': topic, 'assessment': assessment,
                     'status': {1:'responsive', 0:'nonresponsive', -1:'not_assessed', -2:'not_assessed'}[assessment],
                     'partition': 'training_seed'}
            entry = result.setdefault(row[3], {'family_id': family, 'judgments': [], 'judgment_conflicts': []})
            if entry['family_id'] != family:
                raise ValueError('conflicting family mapping')
            prior = next((j for j in entry['judgments'] if j['topic'] == topic), None)
            if prior is not None and prior != label and topic not in entry['judgment_conflicts']:
                entry['judgment_conflicts'].append(topic)
            if label not in entry['judgments']:
                entry['judgments'].append(label)
    return result


def ingest(archive, seed_file, output, *, limit=40):
    if type(limit) is not int or not 1 <= limit <= 400:
        raise ValueError('sample limit must be 1..400')
    archive, seed_file, output = Path(archive), Path(seed_file), Path(output)
    labels = seeds(seed_file)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (output/'objects').mkdir(mode=0o700)
    result = {'schema_version':1, 'corpus':'EDRM Enron v2 / TREC Legal 2010 text renderings',
              'scope':'development sample of training seeds; not a representative evaluation',
              'selection':'first labeled document IDs encountered in archive order',
              'limit':limit, 'native_media_available':False,
              'sources':[{'url':BASE+archive.name, 'sha256':file_hash(archive), 'bytes':archive.stat().st_size},
                         {'url':BASE+seed_file.name, 'sha256':file_hash(seed_file), 'bytes':seed_file.stat().st_size}],
              'documents':[], 'exclusions':[], 'complete':False}
    scanned_bytes = 0
    seen = set()
    with tarfile.open(archive, 'r|bz2') as source:
        for index, member in enumerate(source, 1):
            if index > MAX_MEMBERS or member.size < 0 or member.size > MAX_DOCUMENT:
                raise ValueError('archive scan bound exceeded')
            scanned_bytes += member.size
            if scanned_bytes > MAX_SCAN_BYTES:
                raise ValueError('archive expansion bound exceeded')
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or member.issym() or member.islnk() or member.isdev():
                raise ValueError('unsafe archive member')
            if not member.isfile() or path.suffix != '.txt':
                continue
            key = path.stem
            if key not in labels or key in seen:
                continue
            seen.add(key)
            stream = source.extractfile(member)
            with stream:
                raw = stream.read(MAX_DOCUMENT+1)
            if len(raw) != member.size:
                raise ValueError('archive member size mismatch')
            try:
                text = raw.decode('utf-8', errors='strict')
                if '\x00' in text:
                    raise ValueError('NUL in rendered text')
            except (UnicodeError, ValueError):
                result['exclusions'].append({'document_id':key, 'reason':'unsupported_text_encoding_or_content'})
                continue
            digest = hashlib.sha256(raw).hexdigest()
            object_path = output/'objects'/(digest+'.txt')
            if not object_path.exists():
                private_write(object_path, raw)
            result['documents'].append({'document_id':key, **labels[key],
                                        'source_member':member.name, 'source_sha256':digest,
                                        'representation':'text_rendering', 'modality':'text',
                                        'native_modality':'unknown', 'encoding':'utf-8',
                                        'normalization':'identity', 'characters':len(text), 'bytes':len(raw),
                                        'object':'objects/'+digest+'.txt'})
            if len(result['documents']) >= limit:
                break
    result['complete'] = True
    result['sample_limit_reached'] = len(result['documents']) == limit
    result['scanned_members'] = index if 'index' in locals() else 0
    result['scanned_declared_bytes'] = scanned_bytes
    result['judgment_counts'] = dict(Counter(j['status'] for d in result['documents'] for j in d['judgments']))
    result['documents_with_conflicting_judgments'] = sum(bool(d['judgment_conflicts']) for d in result['documents'])
    result['seed_conflicting_document_topics'] = sum(len(d['judgment_conflicts']) for d in labels.values())
    result['unique_content_hashes'] = len({d['source_sha256'] for d in result['documents']})
    private_write(output/'manifest.json', json.dumps(result, indent=2).encode()+b'\n')
    return result


def locate(root, document, *, start, end, quote):
    """Validate a finding against exact extracted-source characters and byte offsets."""
    digest = document['source_sha256']
    if not isinstance(digest, str) or not SHA.fullmatch(digest):
        raise ValueError('invalid source hash')
    source = Path(root)/'objects'/(digest+'.txt')
    if source.is_symlink() or source.stat().st_size > MAX_DOCUMENT:
        raise ValueError('invalid source object')
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('source changed')
    text = raw.decode('utf-8', errors='strict')
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text) or text[start:end] != quote:
        raise ValueError('unsupported finding span')
    extra = {}
    if document.get('representation') == 'ocr_text':
        from ocr_evidence import location
        extra = location(root, document, start, end)
    return {'document_id':document['document_id'], 'source_sha256':digest,
            'representation':'text_rendering', 'normalization':'identity',
            'start_character':start, 'end_character':end,
            'start_byte':len(text[:start].encode('utf-8')), 'end_byte':len(text[:end].encode('utf-8')), **extra}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path);parser.add_argument('seeds',type=Path)
    parser.add_argument('output',type=Path);parser.add_argument('--limit',type=int,default=40)
    args=parser.parse_args()
    result=ingest(args.archive,args.seeds,args.output,limit=args.limit)
    print(json.dumps({k:result[k] for k in ['scope','sample_limit_reached','scanned_members','judgment_counts','unique_content_hashes']}))
