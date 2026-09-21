#!/usr/bin/env python3
"""Derive private route-comparison data from a sealed observer recording."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import math
from pathlib import Path
from corpus import private_write
from recording import canonical, verify, MAX_BYTES


def distribution(values):
    values = sorted(values)
    return {'observed': len(values), 'minimum': min(values) if values else None,
            'maximum': max(values) if values else None,
            'p50': values[math.ceil(len(values)*.50)-1] if values else None,
            'p95': values[math.ceil(len(values)*.95)-1] if values else None}


def totals(rows):
    costs = [Decimal(r['generation_cost_usd']) for r in rows if r['generation_cost_usd'] is not None]
    return {'tasks': len(rows), 'states': dict(Counter(r['state'] for r in rows)),
            'outcomes': dict(Counter(r['outcome'] for r in rows if r['outcome'] is not None)),
            'timing': {key: {**distribution([r[key] for r in rows if r[key] is not None]),
                             'missing': sum(r[key] is None for r in rows)}
                       for key in ('observer_request_ms', 'queue_wait_ns', 'decision_transport_ns',
                                   'handler_transport_ns', 'gateway_finished_ns')},
            'generation_cost_receipts': len(costs),
            'reported_generation_cost_usd': str(sum(costs, Decimal(0))) if costs else None,
            'total_cost_usd': None, 'savings_usd': None}


def source_hashes(directory):
    result = {}
    for name, limit in [('run.json', 65536), ('events.jsonl', MAX_BYTES), ('seal.json', 65536)]:
        path = directory/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
            raise ValueError('invalid recording file')
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def metrics(directory, output):
    directory = Path(directory)
    hashes = source_hashes(directory)
    recording = verify(directory)
    if source_hashes(directory) != hashes:
        raise ValueError('recording changed during verification')
    grouped = {}
    for event in recording['events']:
        grouped.setdefault(event['task_id'], []).append(event)
    rows = []
    for task, events in grouped.items():
        by_kind = {e['kind']: e for e in events}
        queued = by_kind['task_queued']
        started = by_kind.get('request_started')
        response = by_kind.get('response_received', {}).get('data', {})
        trace = response.get('routing_trace')
        decision = trace['decision'] if trace else None
        def interval(start, end):
            return trace[end]-trace[start] if trace and trace[start] is not None and trace[end] is not None else None
        rows.append({'task_id': task, 'modality': queued['data']['modality'],
                     'state': events[-1]['kind'],
                     'outcome': by_kind.get('task_completed', {}).get('data', {}).get('outcome'),
                     'route': response.get('route'), 'reason': response.get('reason'),
                     'decision': decision, 'policy_version': response.get('policy_version'),
                     'decision_model': response.get('decision_model'),
                     'generation_model': response.get('generation_model'),
                     'requested_model': response.get('requested_model'),
                     'generation_provider': response.get('generation_provider'),
                     'generation_id': response.get('generation_id'),
                     'generation_input_evidence': response.get('generation_input_evidence'),
                     'terminal_reason': events[-1]['data'].get('error', events[-1]['data'].get('reason')),
                     'http_status': response.get('http_status'),
                     'observer_request_ms': response.get('elapsed_ms'),
                     'queue_wait_ns': started['elapsed_ns']-queued['elapsed_ns'] if started else None,
                     'decision_transport_ns': interval('decision_send_started_ns', 'decision_validated_ns'),
                     'handler_transport_ns': interval('handler_send_started_ns', 'handler_validated_ns'),
                     'gateway_finished_ns': trace['finished_ns'] if trace else None,
                     'generation_cost_usd': response.get('generation_cost_usd'),
                     'budget_reserved_usd': started['data'].get('budget_reserved_usd') if started else None,
                     'tokens': {key: response.get(key) for key in ('decision_input_tokens',
                          'decision_output_tokens', 'generation_input_tokens', 'generation_output_tokens')},
                     'finding_count': by_kind.get('review_validated', {}).get('data', {}).get('finding_count'),
                     'event_sequences': [e['seq'] for e in events]})
    routes = sorted({r['route'] for r in rows if r['route'] is not None})
    report = {'schema_version': 1, 'run_id': recording['run']['run_id'],
              'scope': recording['run']['scope'], 'source_hashes': hashes,
              'analyzer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'publication_approved': False, 'summary': totals(rows),
              'by_route': [{'route': route, **totals([r for r in rows if r['route'] == route])} for route in routes],
              'without_observed_route': totals([r for r in rows if r['route'] is None]),
              'tasks': rows,
              'interpretation': {'quantiles': 'nearest rank; descriptive sample statistics only',
                  'timing': 'observer and gateway clocks remain separate; transport includes validation overhead',
                  'missing': 'null is unknown or not observed, never zero',
                  'cost': 'provider-reported generation receipts only; reservations are not charges',
                  'comparison': 'route cohorts are not randomized; no causal speedup or savings claim',
                  'quality': 'source-span validation does not establish legal accuracy'}}
    private_write(Path(output), canonical(report)+b'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = metrics(args.recording, args.output)
    print(canonical({'run_id': report['run_id'], 'scope': report['scope'], 'summary': report['summary']}).decode())
