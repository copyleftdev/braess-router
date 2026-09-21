#!/usr/bin/env python3
"""Validate and stage only the public landing-page assets (standard library only)."""
import argparse
import json
import shutil
import struct
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urljoin

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site'
FILES = {
    'index.html', 'style.css', 'app.js', 'traffic-data.js', 'traffic-data.json',
    'assets/mark.svg', 'assets/archivo-400.woff2', 'assets/archivo-600.woff2',
    'assets/OFL-Archivo.txt', 'assets/social-card.svg', 'assets/social-card.png',
    'llms.txt', 'index.md', 'sitemap.xml',
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

    validate_discovery()
    print(f'PASS: {len(FILES)} publishable assets; {data["requests"]:,} recorded outcomes reconcile')


BASE = 'https://copyleftdev.github.io/braess-router/'


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.links = {}
        self.targets = []
        self.ids = set()
        self.title = ''
        self.jsonld = ''
        self.in_title = False
        self.in_jsonld = False
        self.headings = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if tag == 'h1':
            self.headings += 1
        if tag == 'meta':
            key = attrs.get('name', attrs.get('property'))
            if key in self.meta:
                raise ValueError(f'Duplicate metadata: {key}')
            self.meta[key] = attrs.get('content', '')
        if tag == 'link':
            self.links[attrs.get('rel')] = attrs
        self.in_title = self.in_title or tag == 'title'
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.in_jsonld = True
        for key in ('href', 'src'):
            if attrs.get(key):
                self.targets.append(attrs[key])

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        if tag == 'script':
            self.in_jsonld = False

    def handle_data(self, value):
        if self.in_title:
            self.title += value
        if self.in_jsonld:
            self.jsonld += value


def validate_discovery():
    page = Page()
    page.feed((SITE / 'index.html').read_text())
    if page.headings != 1 or 'Jev' not in page.title or 'Braess Router' not in page.title:
        raise ValueError('Missing page identity or single primary heading')
    if page.links.get('canonical', {}).get('href') != BASE:
        raise ValueError('Canonical URL differs from the project Pages URL')
    expected = {'og:url': BASE, 'og:site_name': 'Braess Router',
                'og:title': page.title, 'twitter:title': page.title,
                'og:image': BASE + 'assets/social-card.png',
                'twitter:image': BASE + 'assets/social-card.png',
                'twitter:card': 'summary_large_image',
                'robots': 'index, follow, max-image-preview:large'}
    for key, value in expected.items():
        if page.meta.get(key) != value:
            raise ValueError(f'Missing or inconsistent {key}')
    for key in ('description', 'og:description', 'twitter:description', 'og:image:alt', 'twitter:image:alt'):
        if not page.meta.get(key):
            raise ValueError(f'Missing {key}')
    for key in ('og:description', 'twitter:description'):
        if page.meta[key] != page.meta['description']:
            raise ValueError(f'Inconsistent description: {key}')
    for rel, href in [('alternate', 'index.md'), ('describedby', 'llms.txt'), ('sitemap', 'sitemap.xml')]:
        if page.links.get(rel, {}).get('href') != href:
            raise ValueError(f'Missing discovery link: {rel}')
    if page.links['alternate'].get('type') != 'text/markdown':
        raise ValueError('Markdown alternate must declare its media type')
    for value in page.targets:
        parsed = urlsplit(urljoin(BASE, value))
        if parsed.scheme != 'https':
            raise ValueError(f'Non-HTTPS target: {value}')
        if parsed.netloc == urlsplit(BASE).netloc:
            if not parsed.path.startswith('/braess-router/'):
                raise ValueError(f'Link escaped project Pages base: {value}')
            name = parsed.path.removeprefix('/braess-router/') or 'index.html'
            if name not in FILES:
                raise ValueError(f'Link leaves published asset set: {value}')
            if name == 'index.html' and parsed.fragment and parsed.fragment not in page.ids:
                raise ValueError(f'Unknown page fragment: {value}')
    graph = json.loads(page.jsonld)
    if graph.get('@context') != 'https://schema.org':
        raise ValueError('Invalid JSON-LD context')
    nodes = {n['@type']: n for n in graph['@graph']}
    if not {'WebSite', 'WebPage', 'SoftwareSourceCode'} <= nodes.keys():
        raise ValueError('Missing structured software identity')
    if nodes['WebPage']['url'] != BASE or nodes['WebSite']['url'] != BASE:
        raise ValueError('Structured URL disagrees with canonical')
    if nodes['SoftwareSourceCode']['codeRepository'] != 'https://github.com/copyleftdev/braess-router':
        raise ValueError('Incorrect source repository')
    if nodes['SoftwareSourceCode']['programmingLanguage']['name'] != 'Rust':
        raise ValueError('Incorrect programming language')
    sitemap = ET.parse(SITE / 'sitemap.xml')
    locations = [e.text for e in sitemap.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
    if locations != [BASE]:
        raise ValueError('Sitemap must list the canonical HTML page exactly once')
    image = (SITE / 'assets/social-card.png').read_bytes()
    if image[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', image[16:24]) != (1200, 630):
        raise ValueError('Social preview must be a 1200x630 PNG')
    guide = (SITE / 'llms.txt').read_text()
    markdown = (SITE / 'index.md').read_text()
    if not guide.startswith('# Braess Router\n') or BASE + 'index.md' not in guide:
        raise ValueError('Agent guide missing its identity or Markdown entry')
    if BASE not in markdown or 'historical' not in markdown.lower() or 'synthetic' not in markdown.lower():
        raise ValueError('Markdown mirror missing canonical or evidence scope')


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
