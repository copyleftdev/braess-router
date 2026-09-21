"""Durable, content-free observer events for the discovery demo.

This records measured client observations, not inferred internal router timings.
It is deliberately independent of the UI and is not a billing/admission ledger.
"""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
import uuid
from routing_trace import validate_trace

VERSION = 1
MAX_EVENTS = 100_000
MAX_BYTES = 32 * 1024 * 1024
FIELDS = {
    'task_queued': {'document_id', 'family_id', 'modality'},
    'request_started': {'input_sha256', 'budget_attempt_id', 'budget_reserved_usd', 'pricing_sha256'},
    'response_received': {'http_status', 'response_sha256', 'elapsed_ms', 'route',
                          'reason', 'policy_version', 'decision_model', 'handler_index',
                          'decision_input_tokens', 'decision_output_tokens',
                          'generation_model', 'requested_model', 'generation_provider', 'generation_id',
                          'generation_input_tokens', 'generation_output_tokens',
                          'generation_cost_usd', 'generation_attempt_id', 'routing_trace'},
    'review_validated': {'review_sha256', 'finding_count'},
    'task_deferred': {'reason'},
    'task_completed': {'outcome'},
    'task_uncertain': {'error'},
}
REQUIRED = {
    'task_queued': {'document_id', 'family_id', 'modality'},
    'request_started': {'input_sha256'},
    'response_received': {'http_status', 'response_sha256', 'elapsed_ms'},
    'review_validated': {'review_sha256', 'finding_count'},
    'task_deferred': {'reason'},
    'task_completed': {'outcome'},
    'task_uncertain': {'error'},
}
INTEGER_FIELDS = {'finding_count', 'http_status', 'handler_index', 'decision_input_tokens',
                  'decision_output_tokens', 'generation_input_tokens',
                  'generation_output_tokens', 'generation_attempt_id'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def label(value):
    return isinstance(value, str) and 0 < len(value) <= 256 and all(ord(c) >= 32 for c in value)


def validate(event, states):
    expected = {'schema_version', 'run_id', 'seq', 'elapsed_ns', 'at', 'kind', 'task_id', 'data', 'previous_sha256'}
    if set(event) - {'sha256'} != expected:
        raise ValueError('invalid event envelope')
    kind, task, data = event['kind'], event['task_id'], event['data']
    if kind not in FIELDS or not label(task) or not isinstance(data, dict):
        raise ValueError('invalid event')
    if not REQUIRED[kind] <= data.keys() or data.keys() - FIELDS[kind]:
        raise ValueError('invalid event fields')
    for key, value in data.items():
        if key == 'routing_trace':
            trace = validate_trace(value)
            if trace['decision'] and any(k in data and data[k] != trace['decision'][k] for k in ('route','reason')):
                raise ValueError('response contradicts routing trace')
        elif key in INTEGER_FIELDS:
            if type(value) is not int or value < 0:
                raise ValueError('invalid count')
        elif key == 'elapsed_ms':
            if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
                raise ValueError('invalid duration')
        elif key in ('generation_cost_usd', 'budget_reserved_usd'):
            if not isinstance(value, str) or len(value) > 64:
                raise ValueError('cost must be a decimal string')
            amount = Decimal(value)
            if not amount.is_finite() or amount < 0:
                raise ValueError('invalid cost')
        elif not label(value):
            raise ValueError('invalid label')
    if 'http_status' in data and not 100 <= data['http_status'] <= 599:
        raise ValueError('invalid HTTP status')
    for key in ('input_sha256', 'response_sha256'):
        if key in data and (len(data[key]) != 64 or any(c not in '0123456789abcdef' for c in data[key])):
            raise ValueError('invalid content hash')
    if kind == 'task_queued' and data['modality'] not in ('text', 'image', 'audio', 'video', 'mixed', 'unsupported'):
        raise ValueError('invalid modality')
    if kind == 'task_completed' and data['outcome'] not in ('handler_completed', 'fallback', 'review_validated'):
        raise ValueError('invalid outcome')
    allowed = {None: {'task_queued'}, 'task_queued': {'request_started', 'task_deferred'},
               'request_started': {'response_received', 'task_uncertain'},
               'response_received': {'review_validated', 'task_completed', 'task_uncertain'},
               'review_validated': {'task_completed', 'task_uncertain'}}
    if kind not in allowed.get(states.get(task), set()):
        raise ValueError('invalid task transition')


class Recorder:
    def __init__(self, directory, *, scope, metadata):
        if scope not in ('synthetic', 'live'):
            raise ValueError('invalid scope')
        # Metadata accepts only provenance hashes, never configuration or secrets.
        if set(metadata) - {'gateway_binary_sha256', 'corpus_manifest_sha256', 'rubric_sha256'}:
            raise ValueError('unknown provenance field')
        if any(not isinstance(v, str) or len(v) != 64 or any(c not in '0123456789abcdef' for c in v)
               for v in metadata.values()):
            raise ValueError('invalid provenance hash')
        self.path = Path(directory)
        self.path.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.manifest = {'schema_version': VERSION, 'run_id': str(uuid.uuid4()), 'scope': scope,
                         'created_at': datetime.now(timezone.utc).isoformat(),
                         'observation_scope': 'gateway client boundary', 'provenance': metadata}
        self._write('run.json', canonical(self.manifest))
        self.previous = digest(canonical(self.manifest))
        self.fd = os.open(self.path / 'events.jsonl', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        self.start = time.monotonic_ns()
        self.lock = threading.Lock()
        self.states = {}
        self.sequence = self.size = 0
        self.closed = self.poisoned = False
        self._sync_directory()

    def _sync_directory(self):
        fd = os.open(self.path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _write(self, name, data):
        fd = os.open(self.path / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())

    def append(self, kind, task_id, **data):
        with self.lock:
            if self.closed or self.poisoned or self.sequence >= MAX_EVENTS:
                raise ValueError('recorder unavailable')
            event = {'schema_version': VERSION, 'run_id': self.manifest['run_id'],
                     'seq': self.sequence + 1, 'elapsed_ns': time.monotonic_ns() - self.start,
                     'at': datetime.now(timezone.utc).isoformat(), 'kind': kind,
                     'task_id': task_id, 'data': data, 'previous_sha256': self.previous}
            validate(event, self.states)
            event['sha256'] = digest(canonical(event))
            wire = canonical(event) + b'\n'
            if self.size + len(wire) > MAX_BYTES:
                raise ValueError('event byte limit reached')
            try:
                pending = memoryview(wire)
                while pending:
                    written = os.write(self.fd, pending)
                    if written <= 0:
                        raise OSError('short write')
                    pending = pending[written:]
                os.fsync(self.fd)
            except OSError:
                self.poisoned = True
                raise
            self.size += len(wire)
            self.sequence += 1
            self.previous = event['sha256']
            self.states[task_id] = kind
            return event

    def close(self):
        with self.lock:
            if self.closed:
                return
            os.close(self.fd)
            self.closed = True
            if self.poisoned:
                raise ValueError('failed recorder cannot be sealed')
            self._write('seal.json', canonical({'run_sha256': digest(canonical(self.manifest)),
                                               'events': self.sequence, 'last_sha256': self.previous}))
            self._sync_directory()


def verify(directory, *, allow_unsealed=False):
    path = Path(directory)
    manifest = json.loads((path / 'run.json').read_bytes())
    if manifest['schema_version'] != VERSION or manifest['scope'] not in ('synthetic', 'live'):
        raise ValueError('invalid run manifest')
    run_hash = previous = digest(canonical(manifest))
    with (path / 'events.jsonl').open('rb') as stream:
        wire = stream.read(MAX_BYTES + 1)
    if len(wire) > MAX_BYTES or (wire and not wire.endswith(b'\n')):
        raise ValueError('oversized or torn log')
    events, states, last_time = [], {}, -1
    for index, line in enumerate(wire.splitlines(), 1):
        if index > MAX_EVENTS:
            raise ValueError('event count limit')
        event = json.loads(line)
        actual = event.pop('sha256')
        if (event['schema_version'] != VERSION or event['run_id'] != manifest['run_id'] or
                event['seq'] != index or event['previous_sha256'] != previous or
                type(event['elapsed_ns']) is not int or event['elapsed_ns'] < last_time or
                digest(canonical(event)) != actual):
            raise ValueError('event integrity mismatch')
        datetime.fromisoformat(event['at'])
        validate(event, states)
        states[event['task_id']] = event['kind']
        previous, last_time = actual, event['elapsed_ns']
        event['sha256'] = actual
        events.append(event)
    sealed = (path / 'seal.json').exists()
    if sealed:
        seal = json.loads((path / 'seal.json').read_bytes())
        if seal != {'run_sha256': run_hash, 'events': len(events), 'last_sha256': previous}:
            raise ValueError('seal mismatch')
    elif not allow_unsealed:
        raise ValueError('unsealed run')
    return {'run': manifest, 'events': events, 'sealed': sealed,
            'summary': summarize(events, states)}


def summarize(events, states):
    responses = [e['data'] for e in events if e['kind'] == 'response_received']
    costs = [Decimal(d['generation_cost_usd']) for d in responses if 'generation_cost_usd' in d]
    return {'tasks': len(states), 'completed': sum(v == 'task_completed' for v in states.values()),
            'uncertain': sum(v == 'task_uncertain' for v in states.values()),
            'deferred': sum(v == 'task_deferred' for v in states.values()),
            'incomplete': sum(v not in ('task_completed', 'task_uncertain', 'task_deferred') for v in states.values()),
            'reported_generation_cost_usd': str(sum(costs, Decimal(0))),
            'generation_cost_receipts': len(costs),
            'total_cost_usd': None, 'cost_scope': 'partial observations; missing costs are unknown'}
