# Observed Jev contract

The compact [fixture corpus](../eval/provider-contract.json) preserves seven
responses to synthetic inputs observed against `jev-1.13.0`. Each case contains
its request JSON, authentication-presence flag, HTTP status, content type, exact
UTF-8 response and hash. Source-manifest hashes tie these fixtures to the retained
experiment archives. No API keys, production inputs or account identifiers are
included. CI makes no provider calls.

| Input | Observed status | Response shape |
| --- | --- | --- |
| Custom router: object state, Choice + Noul | 200 | Typed answers, model and usage |
| Array state, structured instructions, Choice + Noul + Score | 200 | Typed answers; Score includes legend and probabilities |
| Missing model | 422 | `detail` array, including submitted input |
| Missing Authorization header | 403 | `detail` object with authentication error |
| Choice without instructions | 200 | Choice answer, model and usage |
| Empty Choice criteria | 400 | `detail` string |
| Null state | 422 | `detail` array; state reported as missing |

The [API reference](https://docs.typesafe.ai/api) describes instructions as required
and lists 401 for missing/invalid authentication. These particular observations
accepted omitted instructions and returned 403 for an absent header. They do not
establish guarantees for other inputs, keys or future provider versions. Braess
retains its explicit rubric requirements.

The latest expansion used exactly three requests, no retries, and small synthetic
inputs. The unexpected successful response reported 281 input tokens and 31 output
tokens. Reported usage is not an invoice or proof that rejected requests are free.
The earlier experiment used four requests; no load was generated to induce limits.

## Verification and limits

```sh
python3 scripts/provider_contract_e2e.py artifacts/provider-contract \
  --binary target/release/braess-router
```

This checks exact status/body/content-type replay for all seven inputs. Unknown
requests or unobserved mock credentials receive a local 501; that is fixture behavior,
not a prediction about TypeSafe. The fixture cannot infer responses for arbitrary
inputs or reproduce timing, TLS, real authentication, rate limits or overload.

A separate gateway check sends the captured router request and verifies the observed
success, billing dispatch, usage and completed accounting. For error handling it
injects each captured error response into that valid request. It checks a sanitized
502, no handler dispatch, one spent reservation and one retained unresolved attempt.
Error injection tests gateway behavior; it does not claim that a valid router
request naturally produces the malformed-input error captures.

Provider bodies are never forwarded to callers. Error responses can echo submitted
content and have multiple shapes; a single universal `detail` schema would be wrong.
These finite observations do not prove complete provider compatibility or workload
accuracy. Broader behavior must be measured rather than inferred from this corpus.
