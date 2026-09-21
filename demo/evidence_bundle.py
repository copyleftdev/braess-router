#!/usr/bin/env python3
"""Build a private, source-bound OCR inspector bundle; no inference or publication."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from corpus import private_write
from ocr_evidence import inspect, checked


def render(root, document, output):
    """Run only in a disposable child with resource limits applied before decoding."""
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (768*1024*1024,)*2)
    resource.setrlimit(resource.RLIMIT_CPU, (20,)*2)
    import warnings
    from PIL import Image, __version__
    Image.MAX_IMAGE_PIXELS = 16_000_000
    warnings.simplefilter('error', Image.DecompressionBombWarning)
    text, mapping = inspect(root, document)
    raw = checked(root, document['native_source_sha256'], '.bin', 8*1024*1024)
    pages = []
    total = 0
    with Image.open(io.BytesIO(raw)) as source:
        if getattr(source, 'n_frames', 1) != len(mapping['pages']):
            raise ValueError('decoded page count differs from OCR mapping')
        for index in range(len(mapping['pages'])):
            source.seek(index)
            geometry = mapping['pages'][str(index+1)]
            if source.size != (geometry['width'], geometry['height']):
                raise ValueError('decoded page geometry differs from OCR mapping')
            # Preserve source pixel coordinates: no resize, orientation or crop.
            image = source.convert('RGBA')
            image.info.clear()
            encoded = io.BytesIO()
            image.save(encoded, format='PNG')
            data = encoded.getvalue()
            total += len(data)
            if len(data)>64*1024*1024 or total>128*1024*1024:
                raise ValueError('rendered image byte bound exceeded')
            filename = f'page-{index+1}.png'
            private_write(output/filename, data)
            pages.append({'page':index+1, 'file':filename, **geometry,
                          'sha256':hashlib.sha256(data).hexdigest(), 'bytes':len(data)})
    private_write(output/'text.txt', text.encode('utf-8'))
    private_write(output/'words.json', json.dumps(mapping['words'], separators=(',', ':')).encode())
    result = {'schema_version':1, 'complete':True, 'document_id':document['document_id'],
              'native_source_sha256':document['native_source_sha256'],
              'source_sha256':document['source_sha256'],
              'ocr_mapping_sha256':document['ocr_mapping_sha256'],
              'normalization':mapping['normalization'], 'coordinate_unit':'source_page_pixels',
              'image_transform':'frame decode to RGBA PNG; no resize, crop or orientation transform',
              'decoder':{'name':'Pillow', 'version':__version__},
              'exporter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'source_document_sha256':hashlib.sha256((output/'source-document.json').read_bytes()).hexdigest(),
              'pages':pages,
              'text':{'file':'text.txt','sha256':hashlib.sha256((output/'text.txt').read_bytes()).hexdigest()},
              'words':{'file':'words.json','sha256':hashlib.sha256((output/'words.json').read_bytes()).hexdigest(),
                       'count':len(mapping['words'])},
              'review_performed':False, 'extraction_accuracy':'not_established',
              'publication_approved':False, 'provider_calls':0}
    private_write(output/'manifest.json', json.dumps(result, indent=2).encode()+b'\n')


def build(manifest_path, document_id, output):
    manifest_path, output = Path(manifest_path), Path(output)
    if manifest_path.is_symlink() or manifest_path.stat().st_size>4*1024*1024:
        raise ValueError('invalid corpus manifest')
    manifest = json.loads(manifest_path.read_bytes())
    matches = [d for d in manifest['documents'] if d['document_id']==document_id]
    if manifest.get('complete') is not True or len(matches)!=1 or matches[0].get('representation')!='ocr_text':
        raise ValueError('one complete OCR document required')
    document = matches[0]
    inspect(manifest_path.parent, document)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    private_write(output/'source-document.json', json.dumps(document).encode())
    # No provider credentials or inherited proxy settings are needed by the decoder.
    environment = {k:os.environ[k] for k in ('PATH','LANG','LC_ALL') if k in os.environ}
    try:
        process = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker',
                                  str(manifest_path.parent.resolve()), str(output.resolve())],
                                 capture_output=True, timeout=30, env=environment)
    except subprocess.TimeoutExpired:
        raise ValueError('evidence render deadline exceeded') from None
    if process.returncode != 0 or not (output/'manifest.json').is_file():
        raise ValueError('evidence rendering rejected; partial directory is not a bundle')
    return json.loads((output/'manifest.json').read_bytes())


if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--worker':
        try:
            directory = Path(sys.argv[3])
            render(Path(sys.argv[2]), json.loads((directory/'source-document.json').read_bytes()), directory)
        except Exception:
            sys.exit(2)
    else:
        parser=argparse.ArgumentParser(description=__doc__)
        parser.add_argument('manifest', type=Path)
        parser.add_argument('document_id')
        parser.add_argument('output', type=Path)
        args=parser.parse_args()
        report=build(args.manifest, args.document_id, args.output)
        print(json.dumps({'pages':len(report['pages']), 'words':report['words']['count'],
                          'provider_calls':0, 'publication_approved':False}))
