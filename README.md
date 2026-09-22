# Braess Router

[![Tip my tokens](https://tokentip.to/badge/copyleftdev.svg?logo=1)](https://tokentip.to/@copyleftdev)

A bounded Rust semantic router powered by **Jev** and **Poise**.
Jev selects a handler from your catalog; Poise selects an endpoint in its pool.
Uncertain decisions return a local fallback.

**Alpha · single server · loopback only.** This is a public development release,
not a claim of production accuracy or multi-replica coordination.
[Acceptance requirements](docs/ACCEPTANCE.md) track the remaining release work.

Explore the [interactive landing page](https://copyleftdev.github.io/braess-router/): a monochrome traffic
visualization using recorded synthetic outcomes, with normal-load, overload and
recovery views. [Run it locally](site/README.md) without credentials or a build step.

## Try it

Requires Rust 1.97.1 and Python 3.11+ on Linux.

```sh
cargo build --locked --release
python3 scripts/gateway_demo.py /tmp/braess-demo --binary target/release/braess-router
```

The demo prints its URL. POST `{"request":"coding"}` to `/route`; also try
`general`, `reasoning`, and `uncertain`. It uses synthetic fixtures and makes no
provider calls. Ctrl-C stops the demo. Use a new output directory for each run.

To run against your own services:

```sh
braess-router --config config/gateway.mock.json
```

Configure the endpoints first. For live Jev, use
[the live example](config/gateway.live.example.json) and provide
`TYPESAFE_API_KEY` in the process environment. Handler services remain loopback.

## Execute through OpenRouter

The optional `braess-openrouter` companion maps selected routes to explicit models
and providers, with durable call reservations and generation receipts.
[Setup and limits](docs/OPENROUTER.md). Text-only, non-streaming, no automatic retries.

## Execute through FastMetal

`braess-fastmetal` supports fixed model routes, bounded text or image-reference
requests, explicit reasoning settings and durable generation receipts. Jev can
also run through FastMetal. Costs are recorded separately in JPY.
`braess-fastmetal-discover` captures free MCP model, pricing and balance snapshots.
[Setup, observed API contracts and limits](docs/FASTMETAL.md).

## Guarantees and limits

- Bounded ingress, body sizes, deadlines, endpoint admission and uncertainty records.
- Optional durable call reservations and unresolved-request accounting across restart.
- Local rate enforcement, explicit fallback, no automatic upstream retries.
- Timeouts never prove that an upstream request stopped or completed.
- `/health` reports liveness; `/ready` reports local capacity, not upstream health.
- No distributed quota, public-network listener, or workload accuracy guarantee.

See [single-server deployment](docs/DEPLOYMENT.md).
Read the [operator guide](docs/OPERATIONS.md), [development guide](CONTRIBUTING.md),
and [release process](docs/RELEASING.md).
[Observed provider fixtures](docs/PROVIDER_CONTRACT.md) run offline in CI without API keys.

## Why Braess?

Dietrich Braess showed that adding a route can worsen traffic in a network.
The name is a reminder to measure routing choices rather than assume more paths
are better. TypeSafe named Jev after William Stanley Jevons: efficiency can increase
demand. Jev decides; Braess directs.

This project is independent of TypeSafe. Naming inspiration does not imply that
our endpoint policy optimizes global traffic equilibria.

Licensed under MIT OR Apache-2.0.
