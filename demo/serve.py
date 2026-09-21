#!/usr/bin/env python3
"""Serve only the replay's explicit asset list on loopback; never the repository."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = {name: (ROOT/'web'/name, mime) for name, mime in
          [('index.html','text/html; charset=utf-8'), ('style.css','text/css'),
           ('app.js','text/javascript'), ('replay.json','application/json')]}
for name in ('archivo-400.woff2', 'archivo-600.woff2', 'mark.svg'):
    ASSETS['assets/'+name] = (ROOT.parent/'site/assets'/name,
                             'image/svg+xml' if name.endswith('.svg') else 'font/woff2')


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        name = self.path.split('?', 1)[0].removeprefix('/') or 'index.html'
        if name not in ASSETS:
            self.send_error(404)
            return
        path, mime = ASSETS[name]
        try:
            body = path.read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=4174)
    args = parser.parse_args()
    with ThreadingHTTPServer(('127.0.0.1', args.port), Handler) as server:
        print(f'Replay: http://127.0.0.1:{server.server_port}', flush=True)
        server.serve_forever()
