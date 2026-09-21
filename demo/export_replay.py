#!/usr/bin/env python3
"""Export a verified synthetic observer bundle; live exports require a future review gate."""
import argparse
import re
from datetime import datetime
from uuid import UUID
from pathlib import Path
from recording import canonical, verify


FLEET_TASKS = {
    'c3104590315a704833fbf064b2b714e4c5f4569ad43b5376f97ae575ef17a182': '3.0.A',
    '1bead4dd940b5702a0b1a79d4a495ab658a50886eaa765c44e1ebee1c934266c': '3.1.A',
    '919a4b6459be16ffd95787d3c436438cfa754c05b3c23a689b3f418a6bf6d1c8': '3.2.A',
}
FLEET_LABELS = {
    'modality': {'text'}, 'route': {'general', 'coding', 'reasoning', 'fallback'},
    'reason': {'accepted', 'budget_admission_refused'},
    'policy_version': {'capability-v1'}, 'decision_model': {'jev-1.13.0'},
    'generation_model': {'fixture/reviewer'}, 'requested_model': {'fixture/reviewer'},
    'generation_provider': {'Fixture'},
    'generation_id': {'gen-fixture-1', 'gen-fixture-2'},
    'outcome': {'review_validated'}, 'error': {'review_validation_failed'},
}


def check_fleet(data):
    # This is an explicit publication profile for the three public-code fixtures,
    # not authorization to publish arbitrary runs labeled synthetic.
    run = data['run']
    if (set(run) != {'schema_version','run_id','scope','created_at','observation_scope','provenance'} or
            run['observation_scope'] != 'gateway client boundary' or
            set(run['provenance']) - {'gateway_binary_sha256','corpus_manifest_sha256','rubric_sha256'} or
            any(not re.fullmatch('[0-9a-f]{64}', value) for value in run['provenance'].values())):
        raise ValueError('unapproved run metadata')
    if str(UUID(run['run_id'])) != run['run_id'] or datetime.fromisoformat(run['created_at']).isoformat() != run['created_at']:
        raise ValueError('invalid run identity')
    for event in data['events']:
        if datetime.fromisoformat(event['at']).isoformat() != event['at']:
            raise ValueError('invalid event timestamp')
        if event['task_id'] not in FLEET_TASKS:
            raise ValueError('unexpected fleet task')
        for key, value in event['data'].items():
            if not isinstance(value, str):
                continue  # recording.verify already validates numeric fields.
            if key in ('document_id', 'family_id'):
                valid = value == FLEET_TASKS[event['task_id']]
            elif key.endswith('_sha256') or key == 'budget_attempt_id':
                valid = re.fullmatch('[0-9a-f]{64}', value)
            elif key in ('generation_cost_usd', 'budget_reserved_usd'):
                valid = re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', value)
            else:
                valid = value in FLEET_LABELS.get(key, set())
            if not valid:
                raise ValueError('unapproved fleet metadata')


def export(source, destination, *, profile='gateway'):
    data = verify(source)
    if data['run']['scope'] != 'synthetic':
        raise ValueError('live public export requires content review; not implemented')
    if profile not in ('gateway', 'fleet'):
        raise ValueError('unknown publication profile')
    if profile == 'fleet':
        check_fleet(data)
    data['presentation'] = {'profile': profile, 'title': 'Gateway observation study',
                            'description': 'Real Braess execution with synthetic Jev and handlers. No legal corpus or real model inference.',
                            'timing': 'Measured client events; spatial paths are illustrative.',
                            'internal_decision_timing': 'not_observed',
                            'approval': 'synthetic protocol metadata only'}
    # Even synthetic identifiers are checked against the known smoke namespace.
    for event in data['events'] if profile == 'gateway' else []:
        if event['task_id'] not in {f'task-{i}' for i in range(6)}:
            raise ValueError('unexpected task; review required before export')
        for key in ('document_id', 'family_id'):
            if key in event['data'] and event['data'][key] not in {f'fixture-{i}' for i in range(6)}:
                raise ValueError('unexpected source identifier')
    if profile == 'fleet':
        data['presentation'].update(title='Review fleet observation study',
            description='Real Braess and adapter execution with synthetic Jev and reviewer responses. Source-span validation and budget gating ran locally; no legal corpus or paid inference.',
            approval='allowlisted fleet fixture metadata only')
    Path(destination).write_bytes(canonical(data) + b'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--profile', choices=['gateway', 'fleet'], default='gateway')
    args = parser.parse_args()
    export(args.source, args.destination, profile=args.profile)
