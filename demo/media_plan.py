#!/usr/bin/env python3
"""Record evidence-based media preparation choices, without dispatch or inference."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from corpus import SHA, private_write
from media import identify, MAX_MEMBER, MAX_MEMBERS, MAX_EXPANDED


def read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4*1024*1024:
        raise ValueError('invalid or oversized metadata file')
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def plan(inventory_path, probe_path, output):
    inventory_path = Path(inventory_path)
    inventory, inventory_hash = read_json(inventory_path)
    probe, probe_hash = read_json(probe_path)
    members = inventory['members']
    if (inventory.get('schema_version') != 1 or not isinstance(members, list)
            or len(members) > MAX_MEMBERS or probe.get('schema_version') != 1
            or probe.get('inventory_sha256') != inventory_hash):
        raise ValueError('inventory and decoder receipt mismatch')
    images = probe['images']
    if not isinstance(images, list) or len(images) > 64:
        raise ValueError('decoder receipt bound exceeded')
    # An identical hash can occur under several native IDs. Preserve each member.
    receipts = {}
    for image in images:
        key = (image['document_id'], image['source_sha256'])
        if key in receipts and receipts[key] != image:
            raise ValueError('conflicting decoder receipts')
        if type(image.get('decoded')) is not bool:
            raise ValueError('invalid decoder status')
        receipts[key] = image
    records, used, total = [], set(), 0
    for index, member in enumerate(members):
        sha = member['sha256']
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            raise ValueError('invalid source hash')
        source = inventory_path.parent/'objects'/sha
        if source.parent.is_symlink() or source.is_symlink() or not source.is_file():
            raise ValueError('invalid source object')
        size = source.stat().st_size
        total += size
        if size > MAX_MEMBER or total > MAX_EXPANDED or size != member['bytes']:
            raise ValueError('source size bound or inventory mismatch')
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError('source hash mismatch')
        mime, capability = identify(raw)
        if mime != member['signature_type'] or capability != member['candidate_capability']:
            raise ValueError('source classification mismatch')
        receipt = None
        stage, reason = 'needs_decoder', 'signature_only'
        if mime == 'text/plain':
            stage, reason = 'prepare_text_review', 'strict_utf8_text_verified'
        elif mime.startswith('image/'):
            key = (member['document_id'], sha)
            if key not in receipts:
                raise ValueError('missing image decoder receipt')
            receipt = receipts[key]
            used.add(key)
            if receipt['decoded']:
                for field, limit in [('width', 16_000_000), ('height', 16_000_000), ('frames', 32)]:
                    if type(receipt.get(field)) is not int or not 1 <= receipt[field] <= limit:
                        raise ValueError('invalid decoded geometry')
                if receipt['width']*receipt['height'] > 16_000_000:
                    raise ValueError('decoded pixel bound exceeded')
                stage, reason = 'prepare_ocr', 'image_decoded_content_not_classified'
            else:
                stage, reason = 'inspect_failure', 'image_decoder_failed'
        elif mime == 'application/octet-stream':
            stage, reason = 'inspect_unknown', 'no_supported_signature'
        records.append({'inventory_member_index': index, 'document_id': member['document_id'],
                        'source_sha256': sha, 'source_bytes': size, 'signature_type': mime,
                        'candidate_capability': capability, 'preparation_stage': stage,
                        'reason': reason, 'decoder_receipt': receipt,
                        'semantic_route': None, 'dispatch_permitted': False})
    if set(receipts) != used:
        raise ValueError('unmatched decoder receipts')
    report = {'schema_version': 1, 'scope': 'offline media preparation plan; no semantic decisions',
              'inventory_sha256': inventory_hash, 'image_probe_sha256': probe_hash,
              'planner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'native_archive_complete': inventory['native_archive_complete'],
              'source_range': inventory['range'], 'scan_ended': inventory['scan_ended'],
              'provider_calls': 0, 'publication_approved': False,
              'direct_vision_handler_verified': False, 'audio_handler_verified': False,
              'stage_counts': dict(Counter(r['preparation_stage'] for r in records)),
              'members': records}
    private_write(Path(output), json.dumps(report, indent=2).encode()+b'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('image_probe', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = plan(args.inventory, args.image_probe, args.output)
    print(json.dumps({'stage_counts': report['stage_counts'], 'provider_calls': 0}))
