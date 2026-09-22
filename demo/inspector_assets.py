"""Verify and freeze the explicit assets of one private OCR inspector bundle."""
import hashlib
import json
from pathlib import Path
from corpus import SHA


def load_bundle(directory):
    root=Path(directory)
    def read(name, maximum, digest=None):
        path=root/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size>maximum:
            raise ValueError('invalid inspector asset')
        raw=path.read_bytes()
        if digest is not None and (not isinstance(digest,str) or not SHA.fullmatch(digest) or hashlib.sha256(raw).hexdigest()!=digest):
            raise ValueError('inspector asset hash mismatch')
        return raw
    raw=read('manifest.json',1024*1024);m=json.loads(raw)
    if m.get('schema_version')!=1 or m.get('complete') is not True or m.get('publication_approved') is not False:
        raise ValueError('private complete evidence bundle required')
    if m.get('coordinate_unit')!='source_page_pixels' or not 1<=len(m['pages'])<=32:
        raise ValueError('invalid inspector geometry')
    assets={'evidence/manifest.json':(raw,'application/json')}
    total=0
    for i,page in enumerate(m['pages'],1):
        if page['page']!=i or page['file']!=f'page-{i}.png' or any(type(page[k]) is not int or page[k]<=0 for k in ('width','height')) or page['width']*page['height']>16_000_000:
            raise ValueError('invalid inspector page')
        data=read(page['file'],64*1024*1024,page['sha256']);total+=len(data)
        if total>128*1024*1024:raise ValueError('inspector byte bound exceeded')
        assets['evidence/'+page['file']]=(data,'image/png')
    for key,name,mime,limit in [('text','text.txt','text/plain; charset=utf-8',2*1024*1024),('words','words.json','application/json',16*1024*1024)]:
        if m[key]['file']!=name:raise ValueError('invalid inspector asset name')
        assets['evidence/'+name]=(read(name,limit,m[key]['sha256']),mime)
    return assets
