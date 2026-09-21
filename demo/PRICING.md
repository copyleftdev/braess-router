# Text-pilot pricing evidence

On 2026-09-21, public provider metadata was saved under ignored
`artifacts/pricing-source-v1`, with source URLs, retrieval time and SHA-256 hashes.
No inference request or credential was used. Availability and prices must be
refreshed before dispatch; this is a planning snapshot.

| Candidate | Endpoint | Input / million tokens | Output / million tokens |
| --- | --- | ---: | ---: |
| Jev 1.13.0 | Direct TypeSafe | $0.042 | $0 |
| Gemini 2.5 Flash Lite | Google Vertex EU | $0.10 | $0.40 |
| Gemini 2.5 Flash | Google Vertex EU | $0.30 | $2.50 |

Sources: [TypeSafe models](https://docs.typesafe.ai/models),
[Flash Lite endpoint metadata](https://openrouter.ai/api/v1/models/google/gemini-2.5-flash-lite/endpoints),
[Flash endpoint metadata](https://openrouter.ai/api/v1/models/google/gemini-2.5-flash/endpoints).
These are candidate bindings for protocol testing, not evidence that either model
is adequate for legal review. The two generation candidates also advertise media
input, but the current adapter accepts text only. Jev itself accepts text only.

The captured generation endpoints report 1,048,576 context tokens and 65,535
completion tokens. The quote uses `google-vertex/eu`, not the base slug.
[OpenRouter's provider-selection documentation](https://openrouter.ai/docs/guides/routing/provider-selection)
explains that a base slug can match multiple endpoint variants. The specific EU
endpoints reported status 0 and support for `max_tokens` at capture time. This
does not prove account access or future availability.

## Reservation scenario

```sh
python3 demo/pricing_quote.py PRIVATE_SOURCE_DIRECTORY NEW_QUOTE.json
```

The source directory contains the captured endpoint JSON, TypeSafe models page
and `sources.json` with observed time, URLs, hashes and manually reviewed direct
Jev rates. The utility checks source hashes and age (at most 24 hours), model and
endpoint identity, text capability, available status, token-cap support, bounded
capacities and known pricing dimensions. Unknown charges, ambiguous endpoint
matches and nonfinite or binary-float rates fail closed. A source hash binds the
saved evidence; it does not authenticate the publisher or automate human review
of TypeSafe's documentation.

This deliberately avoids tokens-per-character assumptions. For each candidate it
prices the full advertised input capacity, full completion capacity, a separate
full-capacity reasoning allowance, cache-read/write allowances, any listed request
fee, one full 64k-input Jev decision, and a 25% margin. The requested output limits
remain 1,024 and 2,048 tokens; the reservation scenario uses the larger provider
capacities. [Reasoning may consume billed output](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens),
so the quote does not assume that a visible-output cap alone bounds all work.

The captured scenario yields **$0.954718017 per task** when reserving for the more
expensive route before Jev chooses, or **$1.909436034 for two tasks**. This is an
intentionally inflated admission reservation, not an expected charge or a
provider-guaranteed invoice ceiling. It excludes account-level fees and cannot
prevent changed pricing or undocumented billing behavior. No live invoice has
been reconciled against these candidates.

`pricing_quote.py` is an offline planner. Its result does not create a ledger,
select a pilot allowance or permit dispatch. It assumes the existing direct
TypeSafe gateway; OpenRouter's separate Decisions transport is not implemented.
A [two-task plan](PILOT.md) now binds this catalog to explicit configurations.
Execution-time enforcement, complete billing reconciliation and a selected
allowance remain before the paid fleet pilot.

Tests cover exact decimal arithmetic, separate reasoning allowance, refusal of
base provider slugs, unavailable endpoints, unknown charges, unsupported token
limits, stale/future evidence and changed snapshots. Synthetic test prices and
documents are not provider observations.
