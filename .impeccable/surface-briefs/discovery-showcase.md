# Public discovery showcase

Documented 2026-09-21. Mode: Experience with an Operate evidence inspector.
Scope: `site/index.html#discovery` and `site/discovery/index.html`.
This is an ordinary extension of the precision traffic instrument. `DESIGN.md`
and `.impeccable/design.json` remain the established authority and are unchanged.

## Direction and observed surface

The public introduction explains discovery before asking visitors to interpret
routing. The landing section leads with “Discovery in motion. Follow the
decisions.” A short workflow explanation and replay action sit beside three
numbered, ruled steps: choose the review, follow the branch, inspect the record.
Its two columns use an 80px gap and collapse to one at 750px. Supporting prose
is 16px on desktop and 14px on mobile; the scope statement is 12px.

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

## Evidence and finish

Source checked for this documentation pass: the landing HTML/CSS, public replay
HTML and recording, generator, `scripts/check_site.py`, `scripts/test_site.py`,
`scripts/test_discovery_site.cjs`, Pages workflow, and existing product, design
and discovery-replay brief. The documenter did not rerun backend execution or
browser checks.

The supplied fresh finish reviewer examined six intentional captures and returned
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
checks before allowlist staging. The implementation owner reports all 10 Python
site tests, generator freshness and JavaScript syntax checks passed. Chromium
checks also passed at both sizes against 18 staged files under `/braess-router/`,
covering the interactions and request/error/overflow assertions above. That run
used the temporary precursor of the committed browser script; subsequent changes
only made the module/origin configurable and ensured the capture directory
exists. All six captures were opened by the owner and reviewer. These are
supplied execution results, not independent documenter test runs.

Small inherited diagram annotations remain a nonblocking reviewer limitation.
Detector palette/type drift was preexisting and is outside this ordinary
extension; it does not authorize a design-system refresh. No new shipping raster
assets were introduced; the six PNGs are review evidence. This brief completes
the documentation portion of the reviewed showcase slice; it does not assert
that a remote Pages deployment has occurred.
