# Braess Router — Jev semantic routing in Rust

Canonical page: https://copyleftdev.github.io/braess-router/
Source repository: https://github.com/copyleftdev/braess-router
Maintainer: [copyleftdev](https://github.com/copyleftdev)

Braess Router is a bounded Rust semantic router powered by Jev and Poise. Jev selects a handler from your catalog; Poise selects an endpoint within that handler's pool. Uncertain decisions return a local fallback.

## How requests move

- **Jev selects.** Typed decisions choose a handler category. The demonstration has general, coding, and reasoning routes. These are example capabilities, not multiple Jev models.
- **Poise distributes.** Least-loaded endpoint selection operates inside the chosen pool; endpoint admission is bounded.
- **Braess holds the line.** Ingress, body sizes, deadlines, and admission have limits. Optional durable call reservations and unresolved-request accounting survive restart. There are no automatic upstream retries. A timeout does not establish that upstream work stopped or completed.
- **Fallback and rejection are different.** Uncertain decisions return locally. Requests rejected at validation or admission do not dispatch to a handler.

## Scope

This is an independent open-source project, not an official TypeSafe AI product. The current scope is single-server alpha with loopback-only handlers. There is no distributed account quota or production-accuracy guarantee. Read the [acceptance requirements](https://github.com/copyleftdev/braess-router/blob/main/docs/ACCEPTANCE.md) before treating an alpha as an accepted v1 release.

## The traffic visualization

The page illustrates a historical local experiment with synthetic Jev and handler fixtures. It does not call a provider API. Normal, pressure, and recovery controls show measured outcome totals; moving particles are a systematic sample with illustrative timing. Pool geometry explains the architecture and does not assert measured per-endpoint distribution.

| Phase | Concurrency | Requests | Dispatched | Local fallback | Rejected |
| --- | ---: | ---: | ---: | ---: | ---: |
| Normal | 4 | 2,765 | 1,660 | 553 | 552 |
| Pressure | 16 | 24,236 | 1,618 | 536 | 22,082 |
| Recovery | 4 | 2,766 | 1,660 | 554 | 552 |

The 29,767 outcomes describe this historical experiment, not live Jev latency or current production capacity. The [downloadable JSON](https://copyleftdev.github.io/braess-router/traffic-data.json) includes full phase counts, 720 sampled outcomes, and hashes of the original request and summary artifacts. It does not contain the complete raw request corpus.

## Explore and build

- [Source code and quick start](https://github.com/copyleftdev/braess-router)
- [Operator guide](https://github.com/copyleftdev/braess-router/blob/main/docs/OPERATIONS.md)
- [Deployment](https://github.com/copyleftdev/braess-router/blob/main/docs/DEPLOYMENT.md)
- [Recovery and configuration migration](https://github.com/copyleftdev/braess-router/blob/main/docs/RECOVERY.md)
- [Jev documentation](https://docs.typesafe.ai/introduction)
- [Poise source](https://github.com/copyleftdev/poise-rs)

License: MIT OR Apache-2.0. Choose either license. [Support copyleftdev](https://tokentip.to/@copyleftdev).
