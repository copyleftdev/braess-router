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

CI builds a separate package from its four-task synthetic discovery-policy run,
verifies it before upload, and verifies it again after downloading the validation
artifact. No real corpus is involved in that workflow. CI also installs the
pinned Pillow dependency in a temporary virtual environment before running the
Python suite so optional image tests execute there.

## Submitted-image execution packages

Freeze image-input provenance and scans without inventing a review finding:

```sh
python3 demo/package_replay.py build-execution RECORDING EXACT_REFERENCE \
  INSPECTOR_BUNDLE TASK_ID NEW_PACKAGE
python3 demo/package_replay.py verify NEW_PACKAGE
```

This mode uses the same verified association as the private viewer. It includes
`image-link.json`, the scan inspector assets, replay, route analysis, viewer and
fonts. It excludes the submitted reference file and its prompt, raw provider
answers and credentials. The second assembly checks all frozen evidence bytes,
including scan assets, before the final package manifest is written. Both
packaging modes retain create-only output and the same 192 MiB bound.

The actual two-page image transport recording produced a 16-file private package.
Its desktop/mobile submitted-page navigation checks pass against the frozen
server. Unit tests also relocate a package, remove original recording/reference/
inspector inputs, verify the remaining bundle, reject a changed packaged image,
and refuse mismatched reference bytes before creating output. These checks prove
portability and byte identity, not model understanding or review accuracy.
