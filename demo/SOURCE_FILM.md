# Private source-navigation film

`record_source_film.cjs` captures an existing, sealed synthetic OCR review at
`http://127.0.0.1:4180`. Start `serve.py` with the matching review corpus,
prepared tasks, recorded run, and evidence bundle as described in
[REVIEW_LINK.md](REVIEW_LINK.md). The capture expects one task and one finding
with verified image regions. It does not invoke inference providers.

With Playwright Chromium, FFmpeg, and ffprobe installed:

```sh
node demo/record_source_film.cjs artifacts/source-film-NEW
```

To record a [frozen private package](PACKAGE.md) served on another loopback port:

```sh
BRAESS_REPLAY_URL=http://127.0.0.1:4181 \
  node demo/record_source_film.cjs artifacts/source-film-NEW
```

Only an HTTP origin on `127.0.0.1` is accepted. The manifest hashes the actual
served HTML, JavaScript, CSS, fonts and mark as well as the replay and evidence
assets, before and after recording. Those served hashes identify the viewer in
the film; local source hashes separately identify the checkout and capture code.

If Playwright is installed outside normal module resolution, set
`PLAYWRIGHT_MODULE` to its module directory. The destination must not exist.
The capture writes a 1920 × 1080 WebM, H.264 MP4, and `capture.json` containing
source, served evidence, and video hashes. Keep this directory private: the
video includes original document content. No public export is produced.

The sequence follows the recorded route, visible route comparison, decision metadata, provisional
finding, matching scan and transcript, source-pixel zoom, and rewind that
clears the finding association. Assertions check finding visibility and image
regions, browser errors, horizontal overflow, unchanged input hashes, and
output dimensions and duration. These checks do not establish transcription
accuracy, legal correctness, or real-provider behavior.

`capture_elapsed_ms` starts after initial page readiness. It excludes loading
pre-roll and is a scene-order aid, not an exact video presentation timestamp.
It is separate from both recorded observer time and gateway offsets. Playback
at 0.01× is intentional so the short local fixture can be inspected.

The first private draft was 35.76 seconds. Its MP4 decoded without errors, and
the source-navigation frame was visually inspected. The manifest records zero
external provider calls, synthetic provider responses, unevaluated semantic
accuracy, and no publication approval. This is footage of verified source
navigation; direct vision inference and audio review remain separate work.
That draft predates the **Across the routes** section. Its recorded renderer
hashes identify the earlier UI; capturing the current page requires a fresh
output directory and produces a separate manifest.

The second private draft records the frozen package with the comparison section:
39.76 seconds at 1920 × 1080. Its full MP4 decoded without errors; extracted
comparison and scan/transcript frames were visually inspected. All 15 served
asset hashes matched the package manifest, and both video hashes matched the
capture manifest. A private `package-verification.json` binds those manifests.
The route cohort contains one scripted result; this footage establishes neither
production performance nor semantic accuracy. No provider calls occurred.

## Submitted-image film mode

For a frozen execution package containing one task and exactly two submitted
pages, add `--image-input`:

```sh
BRAESS_REPLAY_URL=http://127.0.0.1:4184 \
  node demo/record_source_film.cjs artifacts/image-film-NEW --image-input
```

This sequence visits the image receipt, each submitted scan page and native-pixel
view, then demonstrates that rewind clears the association. It waits for each
selected image to decode, checks its height against the bound page metadata,
and refuses finding boxes in this input-only scene. The capture hashes
`image-link.json` instead of `review-links.json`; the remaining asset-stability,
loopback, synthetic-scope and encoding checks still apply. OCR finding mode
remains the default. Both modes produce `source-replay.mp4`, `source-replay.webm`
and a scope-labeled `capture.json`. Neither mode evaluates model understanding.

The current private image-input draft is 39.84 seconds at 1920 × 1080. Its full
MP4 decoded without errors, and extracted frames showed the correct first and
second source pages with their transport labels. All 15 captured served-asset
hashes match the frozen package; both video hashes match the capture manifest.
The separate private package-verification record binds the package and capture
manifests. It remains synthetic-provider demonstration footage, with zero
external provider calls and no publication approval.
