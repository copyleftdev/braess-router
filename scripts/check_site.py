#!/usr/bin/env python3
"""Validate and stage only the public landing-page assets (standard library only)."""
import argparse
import json
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site'
FILES = {
    'index.html', 'style.css', 'app.js', 'traffic-data.js', 'traffic-data.json',
    'assets/mark.svg', 'assets/archivo-400.ttf', 'assets/archivo-600.ttf',
    'assets/OFL-Archivo.txt',
}


def validate():
    for name in FILES:
        path = SITE / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(SITE.resolve()):
            raise ValueError(f'Missing or unsafe public asset: {name}')
    data = json.loads((SITE / 'traffic-data.json').read_text())
    embedded = (SITE / 'traffic-data.js').read_text().removeprefix('window.BRAESS_TRAFFIC = ').strip().removesuffix(';')
    if json.loads(embedded) != data:
        raise ValueError('Downloaded and embedded replay datasets differ')
    if sum(phase['requests'] for phase in data['phases']) != data['requests']:
        raise ValueError('Recorded phase totals do not reconcile')
    for phase in data['phases']:
        for key in ('statuses', 'outcomes'):
            if sum(phase[key].values()) != phase['requests']:
                raise ValueError(f'{key} do not reconcile in phase {phase["phase"]}')
        if any(sample['outcome'] not in phase['outcomes'] for sample in phase['samples']):
            raise ValueError('Sample contains an unrecorded outcome')

    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            for key, value in attrs:
                if key not in ('src', 'href') or not value or value.startswith('#'):
                    continue
                parsed = urlsplit(value)
                if parsed.scheme or parsed.netloc:
                    if parsed.scheme != 'https':
                        raise ValueError(f'Non-HTTPS external URL: {value}')
                elif parsed.path not in FILES:
                    raise ValueError(f'Link leaves published asset set: {value}')

    Links().feed((SITE / 'index.html').read_text())
    print(f'PASS: {len(FILES)} publishable assets; {data["requests"]:,} recorded outcomes reconcile')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path)
    args = parser.parse_args()
    validate()
    if args.stage:
        args.stage.mkdir(parents=True, exist_ok=False)
        for name in sorted(FILES):
            dest = args.stage / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SITE / name, dest)
        print(f'Staged public assets in {args.stage}')


if __name__ == '__main__':
    main()
