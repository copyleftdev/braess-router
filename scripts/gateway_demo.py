#!/usr/bin/env python3
"""Run a local synthetic Jev+handler demo; never calls a provider."""
import argparse
from pathlib import Path
import threading
from gateway_e2e import gateway

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='new directory for configuration and logs')
    parser.add_argument('--binary', type=Path, default=Path('target/release/braess-router'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    with gateway(args.binary.resolve(), args.output.resolve(), 'demo', deadline_ms=2000,
                 admission_limit=8, max_jev_calls=1000) as (url, fixtures):
        print(f'Synthetic mock gateway: {url}/route', flush=True)
        print('POST JSON {"request":"coding"}; also try general, reasoning, uncertain.', flush=True)
        print('Ctrl-C stops the gateway and fixtures. No real model inference occurs.', flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
