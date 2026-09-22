# Public discovery showcase

Documented 2026-09-21. Mode: Experience with an Operate evidence inspector.
Scope: `site/index.html#discovery`, its narrated film embed and
`site/discovery/index.html`.
This is an ordinary extension of the precision traffic instrument. `DESIGN.md`
and `.impeccable/design.json` remain the established authority and are unchanged.

## Direction and observed surface

The public introduction explains discovery before asking visitors to interpret
routing. The landing section leads with “Discovery in motion. Follow the
decisions.” A short workflow explanation sits beside three
numbered, ruled steps: choose the review, follow the branch, inspect the record.
Its two columns use an 80px gap and collapse to one at 750px. Supporting prose
is 16px on desktop and 14px on mobile; the scope statement is 12px.

The ordinary film extension follows those steps with “Watch the walkthrough.”
The full-width, 16:9 video uses native controls, inline playback,
`preload="none"` and no autoplay. Its 74-second, 1920×1080 walkthrough has
ElevenLabs George narration and 21 default English WebVTT caption cues.
Transcript and video-download links remain available without JavaScript.
“Now follow a task yourself.” places the interactive replay action below the
film, replacing its earlier position beside the introductory steps.

Graphite rules separate the film and its next action. The heading is 24px,
supporting details 13px, and the next-action prompt 20px (18px on mobile).
At 750px the film heading, details and next-action rows stack; the video keeps
its aspect ratio. These are surface-specific treatments within the existing
visual system.

The destination begins “A document arrives. Which review next?” and defines
discovery as finding material that matters in a document collection. Three guide
columns establish the recorded experiment, explain candidate versus outcome
paths, and state what validation establishes. They become one column at 750px;
guide prose is 13px/1.75 with regular-weight 16px lead-ins. These are local
surface measurements, not additions to the system token scale.

Both surfaces retain self-hosted Archivo, near-black and porcelain, graphite
rules, square actions and the flat instrument composition. The destination
inherits the shared replay canvas, recorded-time controls, task list, route
scores, gateway timing and pale metadata pane. Dashed branches mean candidate
routes; the solid path means the recorded outcome. A crossed endpoint denotes a
preference held by the gate. Explicit labels and task outcomes repeat the visual
meaning. Each task takes one outcome path; the diagram does not imply that all
candidate handlers ran. Playback starts paused at the final frame; Start rewinds
the evidence. Spatial paths remain illustrative, independently of measured
event and gateway timestamps.

## Recording and public boundary

The published recording is the approved synthetic discovery export for run
`38d474c2-6304-47d2-86c1-2e6603731b88`: four tasks, 15 events and a final observer
time of 53,222,372ns. Standard review passes source-span validation; deeper review
returns evidence that fails validation and remains uncertain; the third task
returns local fallback; the fourth is deferred before dispatch by budget
admission. The completed count is two because local fallback is a completed
task, not a second validated review.

The router and adapter executed locally with scripted Jev and reviewer responses
and synthetic documents. This is not a semantic or legal accuracy evaluation.
Source-span validation checks evidence structure. Two synthetic generation
receipts report $0.000002; total cost remains unknown rather than reconciled
spend. The public page makes no model calls and contains no private documents.
It does not publish the private source inspector, private pilot recordings,
original source documents or credentials.

`scripts/build_discovery_site.py` owns the generated HTML, CSS and JavaScript in
`site/discovery/`, drawing the shared viewer from `demo/web/`. It adds the public
intro, search metadata and project-relative asset URLs, and removes the private
source-inspector section and its assets. Edit the shared viewer or generator and
regenerate; do not maintain a separate public viewer implementation. The
generator does not copy `replay.json`. That approved dataset is independently
pinned by SHA256 in `scripts/check_site.py`; changing it requires publication
review. Pages stages an explicit public asset allowlist, not the demo directory.

The film and its poster derive from the same reviewed public synthetic
four-task replay. The poster is an actual Chromium page capture, not a generated
image. Four new shipping assets in `site/discovery/media/`—`walkthrough.mp4`,
`poster.png`, `walkthrough.vtt` and `transcript.txt`—are explicitly allowlisted
and SHA-256 pinned. They supersede the earlier showcase's no-shipping-raster
description: the poster now ships. Raw captures, source audio, API keys,
receipts and alternate exports remain outside the publication list. Visitors
make no provider calls; the narration does not turn the scripted-provider
demonstration into a reviewer-quality claim.

## Evidence and finish

Source checked for the original showcase documentation pass: the landing HTML/CSS, public replay
HTML and recording, generator, `scripts/check_site.py`, `scripts/test_site.py`,
`scripts/test_discovery_site.cjs`, Pages workflow, and existing product, design
and discovery-replay brief. The documenter did not rerun backend execution or
browser checks.

The original showcase finish reviewer examined six intentional captures and returned
**SHIP, no material fixes required**:

- Landing section: [desktop](../review/showcase-home-desktop.png) and
  [mobile](../review/showcase-home-mobile.png).
- Public introduction: [desktop](../review/showcase-intro-desktop.png) and
  [mobile](../review/showcase-intro-mobile.png).
- Replay instrument: [desktop](../review/showcase-flow-desktop.png) and
  [mobile](../review/showcase-flow-mobile.png).

Browser test coverage at 1440px and 390px includes landing-to-replay navigation
under the GitHub Pages project subpath, four tasks and final counts, uncertain
and deferred selections, rewind, playback, no page/HTTP errors, no horizontal
overflow and same-origin requests only. Static tests exercise stale generated
output, unauthorized recording changes, subpath assets and publication metadata.
The Pages workflow runs static tests, generator freshness and JavaScript syntax
checks before allowlist staging. For that original slice, the implementation owner reported all 10 Python
site tests, generator freshness and JavaScript syntax checks passed. Chromium
checks also passed at both sizes against 18 staged files under `/braess-router/`,
covering the interactions and request/error/overflow assertions above. That run
used the temporary precursor of the committed browser script; subsequent changes
only made the module/origin configurable and ensured the capture directory
exists. All six captures were opened by the owner and reviewer. These are
supplied execution results, not independent documenter test runs.

Small inherited diagram annotations remain a nonblocking reviewer limitation.
Detector palette/type drift was preexisting and is outside this ordinary
extension; it does not authorize a design-system refresh. That original slice
introduced no shipping raster assets; its six PNGs remain review evidence.

For the film extension, the documenter checked the landing HTML/CSS and site
README against the supplied implementation and review results. A fresh reviewer
inspected both [desktop](../review/film-embed-desktop.png) and
[mobile](../review/film-embed-mobile.png) captures and returned **SHIP, no
material fixes required**. The implementation owner reports all 11 site tests
passed, with 22 files in the public staging set. Desktop and mobile browser
checks passed native playback, no MP4 fetch before playback, no horizontal
overflow, no page or asset errors, no external calls, and navigation from the
film's replay action to all four tasks. These are supplied results, not
independent documenter test runs. The two film review captures are not shipping
assets. This brief records the reviewed local implementation; it does not
assert that a remote Pages deployment has occurred.
