# Frozen private replay

Package a recorded review once its sources and optional inspector bundle exist:

```sh
python3 demo/package_replay.py build CORPUS PREPARED/tasks.json RUN NEW_PACKAGE \
  --inspector INSPECTOR_BUNDLE
python3 demo/package_replay.py verify NEW_PACKAGE
python3 -m http.server 4181 --bind 127.0.0.1 --directory NEW_PACKAGE
```

Open `http://127.0.0.1:4181`. Omit `--inspector` for text-only reviews. Use a new
directory for each package. A failed build can leave partial files; a completed
`package.json` and successful verification identify a finished bundle. The server
serves that private directory, not the repo. Keep it loopback-only and stop it
with Ctrl-C after inspection.

The packager verifies the sealed recording and source-linked review associations,
reproduces optional scans through the association verifier, freezes the viewer
and fonts, and generates route analysis. A second assembly checks associations
did not change during preparation. The final manifest records run identity,
synthetic/live scope, file hashes, types and sizes, and packager source hash.
Verification checks file bytes, bounds, paths, symlinks and unexpected files.
Hashes are not signatures: rewriting both manifest and files defeats this
integrity guarantee.

No credentials, raw provider responses, budget databases or native corpus objects
are copied. Quotes, notes, metadata and optional rendered scans remain private.
Publication approval remains false. Packaging performs no inference and does not
establish semantic accuracy, complete billing, OCR accuracy or native redaction.

The package can move to another directory or machine and be served without the
original corpus or checkout. `route-metrics.json` supports downstream analysis;
the browser derives visible-clock comparisons from `replay.json`. Frozen viewer
files do not change with the repository. Make a new package for a new renderer
or run; preserve previous packages for film provenance.

The current one-task, two-page OCR fixture passed the source-navigation check
against its frozen package at desktop and mobile sizes:

```sh
BRAESS_REPLAY_URL=http://127.0.0.1:4181 node demo/test_source_navigation.cjs
```

Set `PLAYWRIGHT_MODULE` if needed. This fixture-specific test verifies exact
source boxes, quote text, tampered association rejection, rewind/page-change
clearing and overflow. It does not evaluate live review quality.
