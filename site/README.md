# Braess landing page

A static, credential-free site. From the repository root:

```sh
python3 -m http.server 4173 --bind 127.0.0.1 --directory site
```

Open http://127.0.0.1:4173. Deploy **only the contents of `site/`** to any static host. No build, API key, analytics or external font request is needed. This directory is excluded from the Rust crate's explicit package inclusion list.

The replay presents a systematic sample of historical synthetic outcomes, with illustrative timing. Normal/pressure/recovery counts cover the complete 29,767-record run. `traffic-data.json` includes source SHA256 hashes, scope, counts and samples; `traffic-data.js` embeds that same data for offline/file previews. Endpoint pool geometry explains the architecture and does not claim measured endpoint distribution.

Controls support keyboard use and reduced-motion preferences. The canvas is decorative to assistive technology; equivalent explanatory text and counts remain in HTML. Offscreen/background animation stops. No live provider calls are made.

Typography: self-hosted Archivo by Omnibus-Type, SIL Open Font License; see `assets/OFL-Archivo.txt`. All visual marks and motion are code-native; no generated raster assets ship.

## GitHub Pages

Published at https://copyleftdev.github.io/braess-router/. The Pages workflow validates every site change in pull requests and deploys from `main` after merge. `scripts/check_site.py` stages an explicit public asset list, excluding repository documents, design notes, screenshots, and credentials. Deployment uses GitHub’s short-lived token; no additional secret is required.

Search and agent-discovery artifacts, crawl-policy scope, validation and account follow-through are documented in [SEO.md](SEO.md).

### Discovery showcase

`discovery/index.html` introduces a four-task synthetic discovery recording. The shared viewer is generated from `demo/web` with `python3 scripts/build_discovery_site.py`; run it after shared viewer changes. `--check` and the Pages validator reject stale copies. The build excludes the private source inspector.

`discovery/replay.json` was produced by `demo/export_replay.py --profile discovery` from the verified `discovery-policy-v2` fixture. Its exact SHA-256 is pinned in `scripts/check_site.py`; replacing it requires reviewing a new allowlisted synthetic export. The explicit staging list excludes private corpus, recordings, findings, credentials and films. The showcase makes no provider calls.

Browser regression: stage into a directory under `/braess-router/`, serve its parent locally, then run `BRAESS_SITE_URL=http://127.0.0.1:4190/braess-router/ node scripts/test_discovery_site.cjs` with Playwright available (`PLAYWRIGHT_MODULE` can name its installed module). It checks the public entry link, all four tasks, uncertain/deferred outcomes, playback/reset, no remote requests, asset errors and mobile overflow. Screenshots stay in ignored `.impeccable/review/`.
