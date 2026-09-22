# FastMetal adapter

`braess-fastmetal` maps Braess routes to fixed FastMetal model IDs. It shares the
OpenRouter adapter's bounded HTTP handler, durable reservations, restart checks
and hash-verified PNG references. It does not retry uncertain upstream requests.

## Start

Copy `config/fastmetal.live.example.json`, choose fixed models and output limits,
and set a private, persistent `journal_path`. The example allows four calls.
Provide `FASTMETAL_API_KEY` in the process environment; never put it in JSON.

```sh
braess-fastmetal --config config/fastmetal.live.example.json --init
braess-fastmetal --config config/fastmetal.live.example.json
```

POST `/generate/general`, `/generate/coding` or `/generate/reasoning` on loopback
port 8084 with `{"route":"general","request":"Summarize this text…"}`.
Responses contain `answer` and `execution`; receipts preserve model, token usage,
finish reason, optional reasoning-token count and `reported_cost_jpy`.
The journal stores reservations and receipts, not prompts, answers or reasoning.
Health, readiness, inspection and uncertainty behavior match
[the existing adapter](OPENROUTER.md). Call limits are not monetary limits.

For FastMetal-hosted Jev, use `config/gateway.fastmetal.live.example.json` and
`eval/fastmetal-rubric.json`, with the same environment variable. Start the
adapter before the gateway. Configure the gateway's optional durable budget and
request journal as described in [operations](OPERATIONS.md) for restart-safe
Jev accounting; its example alone has an in-memory Jev call cap.

The decision request uses `typesafe/jev-1.13`; responses must match the observed
`typesafe/jev-1.13-20260917` pin. A future provider version requires explicit
review. Encoded requests reserve room for the expanded model name within the
8,192-byte upstream limit. Policy thresholds and fallback remain unchanged.

## Model selection and settings

Use actual IDs from authenticated `GET https://api.fastmetal.ai/v1/models`, not
provider-prefixed slugs from the public catalog. Discovery returned 85 IDs;
that is an account snapshot, not a permanent capability list. The public
catalog and account API are different inventories. `owned_by` is not evidence
of the actual serving provider. Pricing and modality support must be checked
for the selected model before raising call limits.

The example uses `gpt-4.1-nano` for general/coding and `gpt-oss-20b` for reasoning.
These are inexpensive contract-test choices, not workload-quality rankings.
Automatic aliases `auto` and `random-free` are rejected to keep routes explicit.
FastMetal routes omit OpenRouter's provider-routing object.

Optional per-route settings:

```json
{"reasoning":{"mode":"effort","effort":"low"},"output_format":"json_object"}
```

Reasoning also accepts `{"mode":"disabled"}` or
`{"mode":"budget","max_tokens":128}` within the route's output-token cap.
Support depends on the selected model. JSON-object output must parse as an
object; truncated or invalid JSON leaves the reservation unresolved.

## Observed contracts

Focused synthetic probes on 2026-09-22 verified:

| API case | Observed response | Adapter behavior |
| --- | --- | --- |
| Text and image input | Chat completion with string content and usage | Supported; images use local verified bundles |
| Structured JSON schema | JSON serialized in content | Adapter offers JSON object mode; no schema interface |
| Reasoning | Completion tokens include reasoning tokens | Preserve counts; omit reasoning text |
| Tool call | Null content and `tool_calls` | Reject; no tool execution loop |
| Streaming | SSE chunks, final usage, `[DONE]` | Not exposed; adapter always requests non-streaming |
| Invalid model | HTTP 400 error object | Sanitized failure, no automatic retry |
| Jev decisions | Typed answers and pinned model | Existing policy validation and fallback |

Chat cost was absent from `usage` and present in `X-Litellm-Response-Cost`.
Its values matched the documented JPY token prices in the tested text cases.
Receipts label this separately as JPY and never copy it into the legacy USD
`usage.cost` field. A missing header means unknown cost, not zero. Balance
updates lagged successful responses. These observations are not an invoice or
a guarantee for every model. The discovery demo's existing USD ledger is not
extended by this adapter.

The overview advertises `/quotas`, but the probed endpoint returned 404.
`GET https://api.fastmetal.ai/key/info` returned working balance information;
its response may contain credentials and must not be logged. Only sanitized
spend/budget fields were retained locally.

Five sanitized live chat fixtures live under `src/generation/fixtures/`.
They retain response shapes while removing identifiers and reasoning text.
Offline tests cover currency separation, model mismatches, invalid usage,
tool rejection, routing parameters, durable restart accounting and call caps.
They approximate observed contracts; they cannot prove perfect provider parity.

## References and scope

The review covered the 23 linked English documentation pages, including
OpenAI-compatible endpoints, Anthropic compatibility, reasoning, decisions,
video, model listing, balances, MCP and integration guides. This companion
implements the bounded generation and Jev paths; it is not a general SDK for
Anthropic messages, legacy completions, video generation or paid MCP tools.

- [API overview](https://fastmetal.ai/docs/api/overview)
- [Models](https://fastmetal.ai/docs/api/models) and [pricing](https://fastmetal.ai/pricing)
- [Chat completions](https://fastmetal.ai/docs/openai/chat-completions)
- [Reasoning](https://fastmetal.ai/docs/api/reasoning)
- [Jev structured decisions](https://fastmetal.ai/docs/api/decisions)
- [Balance endpoint](https://fastmetal.ai/docs/synthetic/quotas)

## Free MCP discovery

`braess-fastmetal-discover` captures model pricing, capabilities and balance over
FastMetal's [MCP endpoint](https://fastmetal.ai/docs/guides/mcp). It performs an
initialization exchange, enumerates tools, and calls only `list_models`, optional
`get_model`, and `quota`. Authentication uses the same `FASTMETAL_API_KEY`.

```sh
braess-fastmetal-discover --output /private/path/fastmetal-snapshot.json \
  --model gpt-4.1-nano --model gpt-oss-20b
```

The parent directory must exist. The output is create-only and private (0600 on
Unix); an existing file or symlink is refused before any requests. A failed run
can leave an empty or incomplete file, which is not a valid snapshot. Use a new
path for a new observation. Store snapshots outside the public repository:
model details are public metadata, but account balances are private.

The versioned JSON snapshot contains start/completion timestamps, source,
negotiated protocol, tool names, a sorted model catalog, requested model details,
and three numeric quota fields: `balance`, `max_budget`, `spend`. Currency is
JPY. Unknown fields, raw account responses, session identifiers and credentials
are excluded. Missing model metadata stays unknown; data policies are provider
claims, not independently verified guarantees. A snapshot is an observation,
not a price lock, model-quality evaluation, or permission to change a route.

The client supports the observed MCP `2025-03-26` protocol, JSON and SSE response
bodies, optional session headers, and bounded tool pagination. Limits are:

| Resource | Bound |
| --- | --- |
| Entire discovery | 60 seconds |
| Each HTTP request | 15 seconds, including connection establishment |
| Each response | 2 MiB |
| Tools / pages | 256 / 4 |
| Catalog models / selected model details | 512 / 8 |
| SSE data events per response | 128 |

There are no automatic retries, redirects, proxy inheritance, arbitrary tool
calls, paid inference or route mutations. An incompatible protocol, schema or
result fails with a static error code. `--mock-url` permits only literal loopback
HTTP addresses and never forwards credentials; it exists for offline fixtures.

A live initialization and free discovery run on 2026-09-22 returned 12 tools,
including `decide`, while the documentation listed eleven. The catalog returned
85 models. MCP initialization succeeded where the earlier isolated call had
returned 403; the cause of that earlier rejection was not established. Paid MCP
tools remain outside this companion: generation and Jev decisions continue
through the journaled HTTP adapters.
