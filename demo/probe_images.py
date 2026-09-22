#!/usr/bin/env python3
"""Bounded local image decoding in disposable subprocesses. No semantic/model review."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from corpus import SHA, private_write


def worker(path, expected):
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(5,5))
    import warnings
    from PIL import Image, __version__
    Image.MAX_IMAGE_PIXELS=16_000_000
    warnings.simplefilter('error',Image.DecompressionBombWarning)
    if path.is_symlink() or path.stat().st_size>8*1024*1024 or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise ValueError('invalid image object')
    with Image.open(path) as image:
        if image.width*image.height>16_000_000 or getattr(image,'n_frames',1)>32:
            raise ValueError('image geometry bound exceeded')
        image.verify()
    with Image.open(path) as image:
        result={'decoded':True,'width':image.width,'height':image.height,'format':image.format,
                'frames':getattr(image,'n_frames',1),'decoder':'Pillow','decoder_version':__version__,
                'semantic_review_performed':False}
        for frame in range(result['frames']):
            image.seek(frame)
            if image.width*image.height>16_000_000:raise ValueError('frame pixel bound exceeded')
            image.load()
    return result


def probe(inventory_path, output):
    path=Path(inventory_path)
    if path.stat().st_size>4*1024*1024:raise ValueError('inventory bound exceeded')
    raw=path.read_bytes();inventory=json.loads(raw)
    images=[m for m in inventory['members'] if m['signature_type'].startswith('image/')]
    if len(images)>64:raise ValueError('image probe batch limit exceeded')
    results=[]
    for member in images:
        sha=member['sha256']
        if not isinstance(sha,str) or not SHA.fullmatch(sha):raise ValueError('invalid object hash')
        object_path=path.parent/'objects'/sha
        try:
            process=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',str(object_path),sha],
                                   capture_output=True,timeout=8,env={k:v for k,v in os.environ.items() if k not in ('OPENROUTER_API_KEY','TYPESAFE_API_KEY','API_KEY')})
            result=json.loads(process.stdout) if process.returncode==0 else {'decoded':False,'reason':'decoder_rejected_or_resource_limit'}
        except subprocess.TimeoutExpired:
            result={'decoded':False,'reason':'decoder_deadline_exceeded'}
        results.append({'document_id':member['document_id'],'source_sha256':sha,**result})
    report={'schema_version':1,'inventory_sha256':hashlib.sha256(raw).hexdigest(),
            'scope':'local image decoding only; no image content classified','provider_calls':0,'images':results}
    private_write(Path(output),json.dumps(report,indent=2).encode()+b'\n')
    return report


if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--worker':
        try:print(json.dumps(worker(Path(sys.argv[2]),sys.argv[3])))
        except Exception:sys.exit(2)
    else:
        parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('inventory',type=Path);parser.add_argument('output',type=Path)
        a=parser.parse_args();r=probe(a.inventory,a.output)
        print(json.dumps({'images':len(r['images']),'decoded':sum(i['decoded'] for i in r['images']),'provider_calls':0}))
