#!/usr/bin/env python3
"""Generate the public discovery shell from the shared replay viewer; no private inputs."""
import argparse
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def assets():
    source = ROOT / 'demo/web'
    html = (source / 'index.html').read_text()
    html = html.replace('content="noindex"', 'content="index, follow"')
    html = html.replace('<title>Recorded decisions — Braess Router</title>', '''<title>Discovery showcase — Braess Router</title>
<meta name="description" content="Explore four synthetic discovery tasks through Braess Router: review routes, fallback, validation and budget deferral in a recorded execution.">
<link rel="canonical" href="https://copyleftdev.github.io/braess-router/discovery/index.html">''')
    html = html.replace('/assets/', '../assets/')
    html = html.replace('<link rel="stylesheet" href="inspector.css"><script src="inspector.js" defer></script>', '')
    html = html.replace('href="https://copyleftdev.github.io/braess-router/"', 'href="../index.html#discovery"')
    html = html.replace('/ recorded decisions', '/ discovery')
    start, end = html.index('<section class="intro">'), html.index('<section class="instrument"')
    html = html[:start] + '''<section class="intro"><h1>A document arrives.<br><span>Which review next?</span></h1><div class="scope"><p>Discovery means finding the material that matters in a collection of documents.</p><p>Here, a review workflow asks Braess to choose where each task goes. Follow the decision, the checks and the recorded result.</p><p id="scope">Loading the recorded run…</p><p class="run-id" id="run-id"></p></div></section>
<section class="showcase-guide" aria-label="About this discovery showcase"><p><strong>Four tasks. One recorded experiment.</strong> Scripted Jev decisions exercise standard review, deeper review and local fallback. A fourth task stops at its budget limit. The router and adapter ran locally; providers and documents are synthetic.</p><p><strong>Read the branches.</strong> Dashed paths show candidate routes; the solid path shows the recorded outcome. Choose a task, then use Start and Play replay to follow its events. Each task takes one outcome path.</p><p><strong>Inspect the result.</strong> One review passed source-span validation, one remained uncertain, one returned locally and one was deferred. Validation checks evidence structure, not legal accuracy. This page makes no model calls and contains no private documents.</p></section>
''' + html[end:]
    start, end = html.index('<section id="source-inspector"'), html.index('<footer>')
    html = html[:start] + html[end:]
    css = (source / 'style.css').read_text().replace("'/assets/", "'../assets/")
    css += '''\n/* Public discovery introduction; shared instrument remains unchanged. */
.scope>p+p:not(#scope):not(.run-id){font-size:14px;line-height:1.65;margin-top:16px;color:var(--muted)}
.showcase-guide{display:grid;grid-template-columns:1.1fr 1fr 1fr;gap:38px;padding:28px 0 38px;border-top:1px solid var(--line)}
.showcase-guide p{font-size:13px;line-height:1.75;color:var(--muted)}
.showcase-guide strong{display:block;color:var(--ink);font-weight:400;font-size:16px;margin-bottom:9px}
@media(max-width:750px){.showcase-guide{grid-template-columns:1fr;gap:22px}.intro{gap:28px}.brand span{font-size:13px}}
'''
    return {'index.html': html, 'style.css': css, 'app.js': (source / 'app.js').read_text()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for name, content in assets().items():
        path = ROOT / 'site/discovery' / name
        if args.check:
            if not path.is_file() or path.read_text() != content:
                raise SystemExit(f'Stale public viewer: {name}; run scripts/build_discovery_site.py')
        else:
            path.write_text(content)


if __name__ == '__main__':
    main()
