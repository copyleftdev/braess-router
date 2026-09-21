#!/usr/bin/env python3
"""Inventory complete members of a bounded native-archive prefix; never execute media."""
from collections import Counter
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
from corpus import DOC_ID, file_hash, private_write

MAX_MEMBER = 8*1024*1024
MAX_EXPANDED = 128*1024*1024
MAX_MEMBERS = 4096


def identify(raw):
    signatures=[(b'%PDF-','application/pdf','document_perception'),
                (b'\x89PNG\r\n\x1a\n','image/png','image_inspection'),
                (b'\xff\xd8\xff','image/jpeg','image_inspection'),
                (b'GIF87a','image/gif','image_inspection'),(b'GIF89a','image/gif','image_inspection'),
                (b'II*\x00','image/tiff','image_inspection'),(b'MM\x00*','image/tiff','image_inspection'),
                (b'BM','image/bmp','image_inspection'),
                (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1','application/x-ole-storage','document_conversion'),
                (b'PK\x03\x04','application/zip','container_inspection'),
                (b'{\\rtf','application/rtf','document_conversion'),
                (b'ID3','audio/mpeg','audio_transcription')]
    for magic, mime, capability in signatures:
        if raw.startswith(magic):return mime,capability
    if raw.startswith(b'RIFF') and len(raw)>=12:
        kind=raw[8:12]
        if kind==b'WAVE':return 'audio/wav','audio_transcription'
        if kind==b'AVI ':return 'video/x-msvideo','video_inspection'
        if kind==b'WEBP':return 'image/webp','image_inspection'
    if len(raw)>=12 and raw[4:8]==b'ftyp':return 'application/iso-base-media','media_container_inspection'
    try:
        text=raw.decode('utf-8',errors='strict')
        if text and all(ord(c)>=32 or c in '\r\n\t' for c in text):return 'text/plain','text_review'
    except UnicodeError:pass
    return 'application/octet-stream','human_inspection'


def native_id(name):
    base=PurePosixPath(name).name
    if DOC_ID.fullmatch(base):return base
    stem=base.rsplit('.',1)[0]
    return stem if DOC_ID.fullmatch(stem) else None


def inventory(prefix, headers, output, *, source_url):
    prefix,headers,output=Path(prefix),Path(headers),Path(output)
    if prefix.stat().st_size>32*1024*1024 or headers.stat().st_size>65536:
        raise ValueError('input range bound exceeded')
    fields={}
    for line in headers.read_text().splitlines():
        if ':' in line:
            key,value=line.split(':',1);fields[key.lower().strip()]=value.strip()
    match=re.fullmatch(r'bytes 0-([0-9]+)/([0-9]+)',fields.get('content-range',''))
    if not match or int(match[1])+1!=prefix.stat().st_size or int(match[2])<=int(match[1]):
        raise ValueError('verified initial HTTP byte range required')
    output.mkdir(mode=0o700,parents=True,exist_ok=False);(output/'objects').mkdir(mode=0o700)
    result={'schema_version':1,'scope':'bounded native archive prefix, not full-corpus coverage',
            'created_at':datetime.now(timezone.utc).isoformat(),'source_url':source_url,
            'range':fields['content-range'],'source_etag':fields.get('etag'),
            'prefix_sha256':file_hash(prefix),'headers_sha256':file_hash(headers),
            'native_archive_complete':prefix.stat().st_size==int(match[2]),
            'classification':'file signatures only; decoder validation and semantic review not performed',
            'members':[],'scan_ended':'archive_end','expanded_bytes':0}
    try:
        with tarfile.open(prefix,'r|bz2') as archive:
            for index, member in enumerate(archive,1):
                if index>MAX_MEMBERS:
                    result['scan_ended']='member_limit';break
                path=PurePosixPath(member.name)
                if path.is_absolute() or '..' in path.parts or member.issym() or member.islnk() or member.isdev():
                    raise ValueError('unsafe archive member')
                if member.size<0 or member.size>MAX_MEMBER or result['expanded_bytes']+member.size>MAX_EXPANDED:
                    result['scan_ended']='expanded_byte_limit';break
                if not member.isfile():continue
                result['expanded_bytes']+=member.size
                with archive.extractfile(member) as stream:raw=stream.read(MAX_MEMBER+1)
                if len(raw)!=member.size:raise EOFError('partial member')
                sha=hashlib.sha256(raw).hexdigest();mime,capability=identify(raw)
                target=output/'objects'/sha
                if not target.exists():private_write(target,raw)
                result['members'].append({'source_member':member.name,'document_id':native_id(member.name),
                    'sha256':sha,'bytes':len(raw),'signature_type':mime,'candidate_capability':capability,
                    'decoder_validated':False,'object':'objects/'+sha})
    except (EOFError, tarfile.ReadError):
        result['scan_ended']='prefix_end_or_invalid_compressed_stream'
    result['signature_counts']=dict(Counter(m['signature_type'] for m in result['members']))
    result['complete_members']=len(result['members'])
    private_write(output/'inventory.json',json.dumps(result,indent=2).encode()+b'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('prefix',type=Path);p.add_argument('headers',type=Path);p.add_argument('output',type=Path);p.add_argument('--source-url',required=True)
    a=p.parse_args();r=inventory(a.prefix,a.headers,a.output,source_url=a.source_url)
    print(json.dumps({k:r[k] for k in ('complete_members','signature_counts','scan_ended','native_archive_complete')}))
