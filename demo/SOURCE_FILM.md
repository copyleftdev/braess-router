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

If Playwright is installed outside normal module resolution, set
`PLAYWRIGHT_MODULE` to its module directory. The destination must not exist.
The capture writes a 1920 × 1080 WebM, H.264 MP4, and `capture.json` containing
source, served evidence, and video hashes. Keep this directory private: the
video includes original document content. No public export is produced.

The sequence follows the recorded route, decision metadata, provisional
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
