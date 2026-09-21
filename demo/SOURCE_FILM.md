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
