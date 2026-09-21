#!/usr/bin/env python3
"""Prepare private vision wire-shape evidence offline; does not dispatch or authorize it."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from corpus import private_write
from inspector_assets import load_bundle
from recording import canonical


def prepare(bundle, output, *, prompt, model, provider, pages):
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode()) > 8192:
        raise ValueError('bounded nonempty prompt required')
    if any(not isinstance(v, str) or not v or len(v) > 256 or any(c.isspace() or ord(c)<32 for c in v)
           for v in (model, provider)):
        raise ValueError('explicit model and provider labels required')
    if not isinstance(pages, list) or not 1 <= len(pages) <= 8 or any(type(p) is not int or p < 1 for p in pages) or len(set(pages)) != len(pages):
        raise ValueError('select one to eight distinct source pages')
    assets = load_bundle(bundle)
    manifest_raw = assets['evidence/manifest.json'][0]
    manifest = json.loads(manifest_raw)
    parts = [{'type': 'text', 'text': prompt}]
    references, total = [], 0
    for number in pages:
        if number > len(manifest['pages']): raise ValueError('page outside bundle')
        page = manifest['pages'][number-1]
        raw = assets['evidence/'+page['file']][0]
        total += len(raw)
        if total > 8*1024*1024: raise ValueError('vision input byte bound exceeded')
        encoded = base64.b64encode(raw).decode('ascii')
        if base64.b64decode(encoded, validate=True) != raw: raise ValueError('image encoding mismatch')
        parts.append({'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,'+encoded}})
        references.append({'page': number, 'sha256': hashlib.sha256(raw).hexdigest(),
                           'bytes': len(raw), 'width': page['width'], 'height': page['height']})
    reference = {'schema_version': 1, 'kind': 'vision_reference_v1',
                 'document_id': manifest['document_id'], 'native_source_sha256': manifest['native_source_sha256'],
                 'inspector_manifest_sha256': hashlib.sha256(manifest_raw).hexdigest(),
                 'prompt': prompt, 'pages': references}
    wire = canonical({'model': model, 'messages': [{'role': 'user', 'content': parts}],
                      'stream': False, 'max_tokens': 1024,
                      'provider': {'only': [provider], 'order': [provider],
                                   'allow_fallbacks': False, 'require_parameters': True}})
    ref = canonical(reference)
    gateway_wire = canonical({'request': ref.decode()})
    if len(gateway_wire) > 16384: raise ValueError('reference exceeds current pilot ingress limit')
    output = Path(output); output.mkdir(mode=0o700, parents=True, exist_ok=False)
    private_write(output/'reference.json', ref+b'\n')
    private_write(output/'provider-request.json', wire)
    report = {'schema_version': 1, 'scope': 'offline request-shape experiment; not executable by current text adapter',
              'document_id': manifest['document_id'], 'pages': references,
              'inspector_manifest_sha256': reference['inspector_manifest_sha256'],
              'reference_sha256': hashlib.sha256(ref+b'\n').hexdigest(),
              'provider_request_sha256': hashlib.sha256(wire).hexdigest(),
              'provider_request_bytes': len(wire), 'gateway_reference_bytes': len(gateway_wire),
              'source_image_bytes': total, 'encoding_roundtrip_verified': True,
              'provider_capability_verified': False, 'provider_calls': 0,
              'pricing_verified': False, 'dispatch_authorized': False, 'publication_approved': False}
    private_write(output/'experiment.json', canonical(report)+b'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path); parser.add_argument('output', type=Path)
    parser.add_argument('--prompt', required=True); parser.add_argument('--model', required=True)
    parser.add_argument('--provider', required=True); parser.add_argument('--pages', nargs='+', type=int, required=True)
    args = parser.parse_args()
    result = prepare(args.bundle,args.output,prompt=args.prompt,model=args.model,provider=args.provider,pages=args.pages)
    print(canonical({k: result[k] for k in ('provider_request_bytes','gateway_reference_bytes','source_image_bytes','provider_calls')}).decode())
