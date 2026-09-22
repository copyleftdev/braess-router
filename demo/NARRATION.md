# Discovery showcase narration

Draft for the public four-task synthetic showcase at `site/discovery/index.html`.
Target: approximately 75–90 seconds, calm and precise. Timings below are editorial
estimates, not measured speech durations or gateway latency. The first generated voice is ElevenLabs George (`eleven_multilingual_v2`),
with a 0.95 speed setting and character-level alignment. Use a fresh capture of this public surface: existing film drafts use
older viewers or private source imagery and do not match this storyboard.

| Beat | Screen action | Narration |
| --- | --- | --- |
| 1 · Set the scene | Show the discovery introduction. Keep the synthetic scope visible. | Discovery begins with documents, and a question: what needs closer review? This demonstration follows four synthetic tasks through Braess Router. The router runs locally; Jev and reviewer responses are scripted. |
| 2 · Explain the choice | Select task one. Frame the router and labeled candidate branches. | Jev proposes a review route. Braess checks that decision against policy before dispatch. Dashed branches show the candidates. The solid path shows the recorded outcome. |
| 3 · Standard review | Rewind and play. Then show task one's validation event and recorded route. | The first task takes standard review. Its returned evidence passes source-span validation. That checks the supporting text, but does not establish legal accuracy. |
| 4 · Keep uncertainty visible | Select task two; show its uncertain state and failed validation event. | The second task takes deeper review, but its evidence fails validation. The work remains uncertain, so it cannot silently count as a successful review. |
| 5 · Return locally | Select task three; frame the fallback outcome. | The third task returns through local fallback, without dispatching to a reviewer. A completed fallback is a different outcome from a validated review. |
| 6 · Respect the budget | Select task four; show deferred status and absent routing decision. | The fourth task reaches its budget limit before dispatch. It stays deferred. There is no model decision to show. |
| 7 · Close on the evidence | Return to the final counts and event record. End on the public replay link. | Two tasks completed, one remained uncertain, and one was deferred. Explore the replay to inspect each decision and the events behind it. |

## Production

Use an ElevenLabs stock or account-authorized voice. Generate narration from this
public script only; do not upload source documents, credentials, private findings
or private film footage. Confirm pronunciations of Braess and Jev in the selected
voice before the final render.

ElevenLabs' text-to-speech endpoint with timestamps returns audio and alignment:
https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps

Save the generated audio and alignment, then derive captions and measured scene
holds from them. Keep narration time separate from the recording's event clock.
Capture each corresponding UI state with enough reading time; do not invent extra
dispatches or animate model calls that did not occur. Assemble an MP4 with voice,
an external WebVTT caption track and a readable transcript. Audio starts only on
visitor playback. Do not regenerate speech when only the picture edit changes.

Before publication, verify the final film's frame/scene alignment, intelligibility,
proper-name pronunciation, caption synchronization and all four outcomes. Preserve
source, audio and output hashes in an ignored artifact manifest. Only the reviewed
public film and caption assets should enter the Pages staging allowlist.

## First narrated cut

The authorized generation used one request and 1,102 reported character credits.
The spoken script ends at 72.493 seconds; the edit adds a 1.5-second closing hold.
Dollar cost was not reported. Generated audio, alignment and receipts remain in
ignored `artifacts/narrated-showcase-v1/`; no credentials are copied there.

Rebuild captions without a provider call:

```sh
python3 demo/caption_narration.py artifacts/narrated-showcase-v1
```

Serve the staged public site under `/braess-router/` on loopback port 4190, then
render from the saved scene timings (Playwright and FFmpeg required):

```sh
node demo/render_narrated_film.cjs artifacts/narrated-showcase-v1 NEW_FILM_DIRECTORY
```

`PLAYWRIGHT_MODULE` may name an installed module; `BRAESS_FILM_URL` may select a
different loopback URL. The renderer verifies all four public viewer files
against repository hashes, checks task outcomes, records seven scenes at 1080p,
then assembles them with normalized narration. It never generates speech or
calls routing providers. The script refuses an existing output directory.

Completed local deliverables: `artifacts/narrated-showcase-delivery-v1/` contains
a switchable-caption MP4, a burned-caption MP4, WebVTT, transcript, poster and
SHA-256 verification manifest. Both MP4s passed full FFmpeg decode at 1920×1080.
Seven scene states were captured and inspected; narration uses the original
provider timing. The switchable-caption version, poster, WebVTT and transcript are now
staged under `site/discovery/media/` for Pages publication after merge. Proper-name pronunciation still needs a listening judgment.
