#!/usr/bin/env python3
"""Serve only the replay's explicit asset list on loopback; never the repository."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = {name: (ROOT/'web'/name, mime) for name, mime in
          [('index.html','text/html; charset=utf-8'), ('style.css','text/css'),
           ('app.js','text/javascript'), ('inspector.js','text/javascript'),
           ('inspector.css','text/css'), ('replay.json','application/json')]}
for name in ('archivo-400.woff2', 'archivo-600.woff2', 'mark.svg'):
    ASSETS['assets/'+name] = (ROOT.parent/'site/assets'/name,
                             'image/svg+xml' if name.endswith('.svg') else 'font/woff2')


PRIVATE_ASSETS = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        name = self.path.split('?', 1)[0].removeprefix('/') or 'index.html'
        if name not in ASSETS and name not in PRIVATE_ASSETS:
            self.send_error(404)
            return
        try:
            if name in PRIVATE_ASSETS:
                body, mime = PRIVATE_ASSETS[name]
            else:
                path, mime = ASSETS[name]
                body = path.read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob:; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=4174)
    parser.add_argument('--evidence-bundle', type=Path, help='Explicit private OCR bundle; verified before serving')
    parser.add_argument('--recording', type=Path, help='Sealed private execution recording without source-review associations')
    for name in ('review-corpus','review-tasks','review-run'):
        parser.add_argument('--'+name,type=Path)
    args = parser.parse_args()
    review_args=(args.review_corpus,args.review_tasks,args.review_run)
    if args.recording:
        if any(review_args) or args.evidence_bundle:parser.error('recording cannot be combined with review inputs or an evidence bundle')
        from private_replay import execution_assets
        PRIVATE_ASSETS.update(execution_assets(args.recording))
    if any(review_args):
        if not all(review_args):parser.error('review-corpus, review-tasks and review-run are required together')
        from private_replay import assets
        PRIVATE_ASSETS.update(assets(*review_args,inspector=args.evidence_bundle))
    if args.evidence_bundle:
        from inspector_assets import load_bundle
        PRIVATE_ASSETS.update(load_bundle(args.evidence_bundle))
    with ThreadingHTTPServer(('127.0.0.1', args.port), Handler) as server:
        print(f'Replay: http://127.0.0.1:{server.server_port}', flush=True)
        server.serve_forever()
