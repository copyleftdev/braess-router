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
DISCOVERY_TASKS = {
    'c3104590315a704833fbf064b2b714e4c5f4569ad43b5376f97ae575ef17a182': '3.0.A',
    '1bead4dd940b5702a0b1a79d4a495ab658a50886eaa765c44e1ebee1c934266c': '3.1.A',
    '0e955e3d45168904192400337af75ab92583f4963fd59a696debb4191d3d3fa9': '3.2.A',
    '6b4da7175c0e6dfdc5cefaadee39450f1e6ff1c6a9b584122f904ab28f0c6c58': '3.3.A',
}
DISCOVERY_LABELS = {**FLEET_LABELS,
    'route': {'review_standard','review_deep','fallback'},
    'reason': {'accepted','model_fallback','budget_admission_refused'},
    'policy_version': {'discovery-review-v1'},
    'generation_model': {'fixture/reviewer-standard','fixture/reviewer-deep'},
    'requested_model': {'fixture/reviewer-standard','fixture/reviewer-deep'},
    'outcome': {'review_validated','fallback'},
}


def check_fleet(data, *, discovery=False):
    # This is an explicit publication profile for the three public-code fixtures,
    # not authorization to publish arbitrary runs labeled synthetic.
    tasks = DISCOVERY_TASKS if discovery else FLEET_TASKS
    labels = DISCOVERY_LABELS if discovery else FLEET_LABELS
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
        if event['task_id'] not in tasks:
            raise ValueError('unexpected fleet task')
        for key, value in event['data'].items():
            if key == 'routing_trace':
                decision = value['decision']
                if decision and set(decision['probabilities']) != labels['route']:
                    raise ValueError('unapproved decision catalog')
            if not isinstance(value, str):
                continue  # recording.verify already validates numeric fields.
            if key in ('document_id', 'family_id'):
                valid = value == tasks[event['task_id']]
            elif key.endswith('_sha256') or key == 'budget_attempt_id':
                valid = re.fullmatch('[0-9a-f]{64}', value)
            elif key in ('generation_cost_usd', 'budget_reserved_usd'):
                valid = re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', value)
            else:
                valid = value in labels.get(key, set())
            if not valid:
                raise ValueError('unapproved fleet metadata')


def export(source, destination, *, profile='gateway'):
    data = verify(source)
    if data['run']['scope'] != 'synthetic':
        raise ValueError('live public export requires content review; not implemented')
    if any('generation_input_evidence' in event['data'] for event in data['events']):
        raise ValueError('image receipt publication requires an explicit export profile')
    if profile not in ('gateway', 'fleet', 'discovery'):
        raise ValueError('unknown publication profile')
    if profile in ('fleet','discovery'):
        check_fleet(data,discovery=profile=='discovery')
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
    if profile in ('fleet','discovery'):
        data['presentation'].update(title='Review fleet observation study',
            description='Real Braess and adapter execution with synthetic Jev and reviewer responses. Source-span validation and budget gating ran locally; no legal corpus or paid inference.',
            approval='allowlisted fleet fixture metadata only')
    if profile == 'discovery':
        data['presentation'].update(title='Discovery policy transport study',
            description='Real Braess and adapter execution with scripted standard, deep and fallback decisions. Synthetic reviewer responses exercise validation and budget gating; this does not evaluate Jev semantic accuracy.',
            approval='allowlisted discovery fixture metadata only')
    if any('routing_trace' in event['data'] for event in data['events']):
        data['presentation']['internal_decision_timing'] = 'gateway monotonic boundaries; only present traces observed'
    Path(destination).write_bytes(canonical(data) + b'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--profile', choices=['gateway', 'fleet','discovery'], default='gateway')
    args = parser.parse_args()
    export(args.source, args.destination, profile=args.profile)
