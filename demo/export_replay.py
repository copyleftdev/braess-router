#!/usr/bin/env python3
"""Export a verified synthetic observer bundle; live exports require a future review gate."""
import argparse
from pathlib import Path
from recording import canonical, verify


def export(source, destination):
    data = verify(source)
    if data['run']['scope'] != 'synthetic':
        raise ValueError('live public export requires content review; not implemented')
    data['presentation'] = {'title': 'Gateway observation study',
                            'description': 'Real Braess execution with synthetic Jev and handlers. No legal corpus or real model inference.',
                            'timing': 'Measured client events; spatial paths are illustrative.',
                            'internal_decision_timing': 'not_observed',
                            'approval': 'synthetic protocol metadata only'}
    # Even synthetic identifiers are checked against the known smoke namespace.
    for event in data['events']:
        if event['task_id'] not in {f'task-{i}' for i in range(6)}:
            raise ValueError('unexpected task; review required before export')
        for key in ('document_id', 'family_id'):
            if key in event['data'] and event['data'][key] not in {f'fixture-{i}' for i in range(6)}:
                raise ValueError('unexpected source identifier')
    Path(destination).write_bytes(canonical(data) + b'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    export(args.source, args.destination)
