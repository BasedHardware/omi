# Vertex Provisioned Throughput for Gemini 2.5 Flash

We bought **5 GSU Provisioned Throughput** for `gemini-2.5-flash` in
`us-central1` so company-paid Flash text is reserved and cheaper than Gemini
API list price.

**Vertex PT: 5 GSU gemini-2.5-flash us-central1, expires ~2027-05-28.**

- SKU: `Vertex AI: Provisioned Throughput 1 Year`
- Cap: 13,450 tok/s
- First billing row: 2026-05-28
- **Expires ~2027-05-28** (1-year SKU; confirm in Cloud Console → Vertex →
  Provisioned Throughput — Commerce API was disabled, so do not invent a more
  precise date)
- Flat ~$290.32/day even when traffic is elsewhere

PT and EDP apply **only on Vertex publisher**, not AI Studio
(`generativelanguage.googleapis.com`).

## Never send company-paid Flash to AI Studio

Server-paid `gemini-2.5-flash` `generateContent` / `streamGenerateContent` must
go to:

`{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/publishers/google/models/gemini-2.5-flash:generateContent`

using ADC / Workload Identity. **Never** `generativelanguage.googleapis.com`
and **never** `?key=` for that path. Missing `GOOGLE_CLOUD_PROJECT` must fail
closed — that omission is what moved Flash off Vertex on 2026-08-04 and
double-paid (reservation + API list).

The model pin is `VERTEX_PT_MODEL` in `backend/routers/desktop_proxy.py`,
sourced from `ptr.PT_MODEL_CURRENT` in
`backend/utils/llm/vertex_pt_routing.py`. Changing the company-paid Flash
default without updating that pin, this note, and the contract tests in the
same commit is the regression.

BYOK Gemini stays on the user's key / AI Studio, and is never remapped: the
user pays for the model they asked for.

## Model prices (Vertex list, captured 2026-08-18)

| Model | Input $/1M | Output $/1M |
| --- | ---: | ---: |
| `gemini-2.5-flash-lite` | 0.10 | 0.40 |
| `gemini-3.1-flash-lite` | 0.25 | 1.50 |
| `gemini-2.5-flash` | 0.30 | 2.50 |
| `gemini-2.5-pro` | 1.25 | 10.00 |

**`gemini-3.1-flash-lite` is not the same price class as
`gemini-2.5-flash-lite`** — it is 2.5x input and 3.75x output. It is cheaper
than `gemini-2.5-flash` and far cheaper than `gemini-2.5-pro`, which is why it
absorbs overflow and Pro. Promoting the client-pinned Lite lanes
(`ModelQoS.lightweight`, Windows `memory/goals/insight`) onto it would be a
large cost regression, not a saving. Those pins are deliberately untouched and
`test_client_pinned_flash_lite_is_never_promoted` holds that boundary.

## Gemini 3.x is multi-region only; regional URLs 404

**This was the production defect in #11826.** `_vertex_url()` built one
regional URL for every model:

```
https://{loc}-aiplatform.googleapis.com/v1/projects/{p}/locations/{loc}/publishers/google/models/{m}:{action}
```

Gemini 3.x has no regional endpoint, so that URL can never work for it. Every
3.x request 404d, which reads exactly like a project access gap and is not one.

Measured 2026-08-18 on `based-hardware` with credentials that can invoke
inference:

| Endpoint | `gemini-3.1-flash-lite` |
| --- | --- |
| `aiplatform.googleapis.com` + `locations/us` | **200** ON_DEMAND |
| `aiplatform.googleapis.com` + `locations/global` | **200** ON_DEMAND |
| `aiplatform.googleapis.com` + `locations/us` + `dedicated` | **429** provisioned throughput |
| `us-central1` / `us-east5` / `us-west1` / `europe-west4` / `asia-northeast1` | **404** |
| `eu-aiplatform.googleapis.com` + `locations/eu` | **404** |

The host is always plain `aiplatform.googleapis.com` — `us-aiplatform.googleapis.com`
is not a valid host (400 `Invalid hostname`). Only the `locations/{loc}` path
segment changes.

The 429 to a `dedicated` request is the "no PT order for this model" answer,
which is what we expect while we own no 3.1 order. It also proves the capacity
header is honored on the multi-region endpoint, so the auto-detect probe below
works there. Note the message reads lowercase `provisioned throughput` where
the regional endpoint uses title case; the matcher casefolds, and must keep
doing so.

### Why `us` and not `global`

`MULTI_REGION_LOCATION` is `us`, overridable with `OMI_VERTEX_GLOBAL_LOCATION`.
Both `us` and `global` answer, but **`global` may serve a request from anywhere
in the world**, while `us` is the US multi-region. This path carries users'
personal conversations, transcripts and memories, and every other server-paid
Gemini call in this service runs in `us-central1`. `us` preserves that
residency posture; `global` silently widens it. That is a deliberate operator
decision, not something a routing change should make on its own — do not
"simplify" `us` into `global`.

### The reservation model must stay regional

`gemini-2.5-flash` **also** returns 200 on `locations/us` and
`locations/global` (trafficType=ON_DEMAND). Routing it there anyway would
bypass the 5 GSU **us-central1** Provisioned Throughput order and bill
on-demand while the reservation kept charging ~$290/day — paying twice for the
same tokens, which is the 2026-08-04 incident above.

So the endpoint rule is **by model family, never by what happens to answer**:

| Model | Host | Location |
| --- | --- | --- |
| `gemini-3.*` | `aiplatform.googleapis.com` | `us` (`OMI_VERTEX_GLOBAL_LOCATION`) |
| everything else | `{loc}-aiplatform.googleapis.com` | `GCP_LOCATION`, default `us-central1` |

`test_the_reservation_model_is_never_routed_off_its_region` holds that
boundary. Location is resolved **per model**, never once per process: a
fallback chain crosses families, so the reservation and the model absorbing its
overflow legitimately sit on different endpoints.

**Unresolved:** whether a Provisioned Throughput order for a 3.x model is
purchased as a multi-region order and how that would interact with the existing
regional `gemini-2.5-flash` order. Nothing in the code assumes an answer.

## Fallback chains and learned reachability

Every model the proxy can route to declares its fallback chain as data, in
`MODEL_FALLBACKS` in `backend/utils/llm/vertex_pt_routing.py`:

| Model | Falls back to |
| --- | --- |
| `gemini-2.5-pro` | `gemini-3.1-flash-lite`, `gemini-2.5-flash-lite` |
| `gemini-2.5-flash` | `gemini-3.1-flash-lite`, `gemini-2.5-flash-lite` |
| `gemini-3.1-flash-lite` | `gemini-2.5-flash-lite` |
| `gemini-2.5-flash-lite` | *(terminal)* |
| `gemini-embedding-001` | *(terminal)* |

**Reading this table correctly:** it lists chains for every model a client may
**request**, which is not the same as the set of models server-paid traffic is
ever **served** by. `gemini-2.5-pro` appears here because it stays
proxy-allowlisted and BYOK users pay for it on their own key — but no
server-paid request is dispatched as Pro. `_serving_model()` remaps it to
`gemini-3.1-flash-lite` before dispatch, and over the daily soft limit the
metering path demotes it to `gemini-2.5-flash-lite` first. Pro's chain is what
would happen if it were ever dispatched anyway, not a route in normal use.
`test_server_paid_traffic_never_dispatches_gemini_2_5_pro` asserts that across
both reservation states and both reachability states.

Three invariants, each enforced by a test rather than by convention:

- **Never onto the reservation.** The live PT model is filtered out of every
  chain at resolution time, at both PT states
  (FC-degraded-fallback-consumes-protected-budget). Degraded traffic must not
  consume the budget the quota exists to protect.
- **Never upward in price.** Each chain is non-increasing in output price
  (`PRICE_PER_MTOK_OUT`), so a degraded request cannot cost more than the one
  it replaces. This is also why `gemini-2.5-flash-lite` is terminal: it is the
  floor of the ladder and the model the desktop clients pin directly.
- **Never onto itself.** A chain never contains its own head, so a dead model
  cannot retry itself.

**Reachability is learned only from real `generateContent` attempts.** There is
deliberately no startup probe. The metadata endpoint
`GET .../publishers/google/models/{m}` is not an oracle — it 404s for
`gemini-2.5-flash-lite`, which works fine — and burning one inference call per
model per instance is unaffordable on Cloud Run, which churns instances
constantly. When an attempt comes back "publisher model not found", the proxy
latches that model for `_PT_PROBE_TTL_SECONDS` and skips it, then re-tries once
the TTL lapses, so a routing fix or a serving change recovers with no deploy.
BYOK responses never teach this table: they come from AI Studio on the user's
own key, so one user must not be able to latch a model dead for the fleet.

A generic 429 (`Quota exceeded for requests per minute`) is backpressure and
never triggers a fallback. Only a PT-exhaustion 429 or a model-unavailable 404
does.

## Thinking contract, measured

Run 2026-08-18 via `backend/scripts/probe_gemini_thinking_contract.py`:

| Model | Config | thoughts | output |
| --- | --- | ---: | ---: |
| `gemini-2.5-flash-lite` | `thinkingBudget: 0` | 0 | 225 |
| `gemini-2.5-flash-lite` | `thinkingBudget: 1024` | 863 | 300 |
| `gemini-2.5-flash-lite` | `thinkingLevel: minimal` | **HTTP 400 — not supported** | |
| `gemini-2.5-flash` | `thinkingBudget: 0` | 0 | 309 |
| `gemini-2.5-flash` | no config | 516 | 213 |
| `gemini-3.1-flash-lite` | `thinkingBudget: 0` | 0 | 64 |
| `gemini-3.1-flash-lite` | `thinkingBudget: 1024` | 278 | 77 |
| `gemini-3.1-flash-lite` | `thinkingLevel: minimal` | 0 | 75 |
| `gemini-3.1-flash-lite` | `thinkingLevel: high` | 603 | 76 |
| `gemini-3.1-flash-lite` | no config | 0 | 64 |

The 3.x rows were measured on the multi-region endpoint once the routing fix
made those models reachable.

**This table deleted a branch rather than justifying one.** `gemini-3.1-flash-lite`
*honors* `thinkingBudget` — budget 0 really is 0 thoughts, budget 1024 spends
278 — and 2.5 models *reject* `thinkingLevel` with HTTP 400
(`thinking_level is not supported by this model`). So `thinkingBudget` is the
one option both families accept and `thinkingLevel` is the one that works on
neither universally. An earlier revision split on family from documentation
rather than measurement and had the direction backwards. `ptr.thinking_config_for()`
is now a single path, and a fallback that crosses families needs no body
rewriting at all.

It also shows why the proxy injects a budget: `gemini-2.5-flash` with no
thinking config spent 516 thinking tokens on a trivial prompt, all billed as
output.

## Migrating the reservation to `gemini-3.1-flash-lite`

Requested 2026-08-18; PT orders provision in ~10 business days. **No deploy is
needed when it lands.** The proxy detects it and promotes itself:

1. Company-paid text asks the reservation for `dedicated` capacity via the
   `X-Vertex-AI-LLM-Request-Type` header. Without that header Vertex silently
   spills over-cap requests onto pay-as-you-go; with it, an over-cap request
   returns 429 `Exceeded the Provisioned Throughput` instead.
2. On that 429 the proxy overflows to `gemini-3.1-flash-lite`. If a capacity
   probe is due (`_PT_PROBE_TTL_SECONDS`, 600s) the first overflow attempt asks
   for `dedicated`. That single request **is** the auto-detection: if the new
   order exists it succeeds, and if it does not it 429s and falls through to
   the on-demand call the proxy would have made anyway. Detection therefore
   costs nothing and only happens when the old reservation is already full.
3. A successful probe latches `_pt_target_ready` and logs
   `desktop_proxy pt_promotion`. From then on `gemini-2.5-flash` requests are
   served by `gemini-3.1-flash-lite` on prepaid capacity.

The positive observation is latched rather than TTL'd on purpose: a PT purchase
is long-lived, and expiring it would flap the serving model every time overflow
stopped re-probing. A vanished order still degrades safely — requests 429 and
overflow absorbs them.

The latch is **per Cloud Run instance**, held in process memory. Promotion
therefore rolls out gradually: each instance switches the first time it
overflows and probes successfully, so expect a mixed fleet for a while rather
than a single cutover instant. Grep the logs for
`desktop_proxy pt_promotion` to see how far it has spread, and set
`OMI_VERTEX_PT_MODEL` if you need every instance on one model immediately.

**Retire the old order when promotion happens.** The `gemini-2.5-flash` order
bills a flat ~$290.32/day until ~2027-05-28 whether or not traffic uses it, so
once traffic moves to `gemini-3.1-flash-lite` the old reservation is paid-for
and idle. Promotion is a code-side cutover; converting or cancelling the 5 GSU
`gemini-2.5-flash` order is a separate commercial action that has to be done in
Cloud Console, and until it is, both are billed.

## Never move dedicated traffic off a reservation early

Moving `gemini-2.5-flash` onto an on-demand model *before* the replacement
order is live pays the flat reservation fee for idle capacity **and** full
on-demand for every token — strictly worse than either alone. This is why the
flash remap is gated on observed capacity rather than shipped as a constant.
`test_flash_stays_on_the_current_reservation_until_target_capacity_exists`
holds that gate.

## Overflow is resolved against the live reservation

`OVERFLOW_PREFERENCE` is a ladder, not a pin, and
`resolve_overflow_model()` never returns the model that currently holds prepaid
capacity. Once `gemini-3.1-flash-lite` *is* the reservation, overflow steps
past it to `gemini-2.5-flash-lite` automatically. Pinning overflow to
`gemini-3.1-flash-lite` would, after promotion, dump degraded traffic onto the
budget the quota exists to protect — that is
`FC-degraded-fallback-consumes-protected-budget` (PR #10686), and the guard is
`test_overflow_never_targets_the_live_reservation`.

## Operator overrides

All four are read per request, so a bad promotion can be corrected without
shipping code.

| Env | Effect |
| --- | --- |
| `OMI_VERTEX_PT_MODEL` | Pins the reservation model, beating auto-detection in both directions. |
| `OMI_GEMINI_OVERFLOW_MODEL` | Pins the overflow model. Rejected at resolution time if it equals the reservation. |
| `OMI_GEMINI_OVERFLOW_ENABLED` | `false` disables overflow entirely; a full reservation then returns 429 to the client. |
| `OMI_VERTEX_GLOBAL_LOCATION` | Multi-region for families with no regional endpoint. Default `us`. Setting `global` widens data residency worldwide — see above before flipping it. |

## Keeping the reservation for work that must be Flash

The 13,450 tok/s cap is oversubscribed, so the proxy actively keeps low-value
work off `gemini-2.5-flash`:

- **Server-paid Pro is served by `gemini-3.1-flash-lite`** ($10.00 -> $1.50 per
  1M output). The remap happens after metering, so the two Pro paths stay
  distinct: within quota a request gets `gemini-3.1-flash-lite`, and over quota
  it still demotes to `gemini-2.5-flash-lite` and keeps the cheap tier for
  heavy users.
- **Over-quota demotion targets `gemini-2.5-flash-lite`**
  (`_QUOTA_DEMOTION_MODEL`), which is `shared`/on-demand on Vertex and never
  burns the PT. Demoting to `gemini-2.5-flash` instead was the 2026-08-17
  defect that silently dumped the Insight tool loop (~11% of the reservation)
  onto the saturated PT lane.
- **Server-paid requests are capped at 2048 output tokens**
  (`_SERVER_PAID_MAX_OUTPUT_TOKENS`). No shipped desktop client sends
  `maxOutputTokens`, so everything used to inherit the 8192 default while
  output burns down the reservation at 9x. Realistic per-lane budgets are
  64–1024 visible tokens plus a thinking budget of up to 1024 (thinking counts
  toward the output limit on 2.5 models). BYOK requests keep the 8192
  default/clamp.

The desktop clients pin the low-value lanes (memory extraction, LiveNotes,
goals, task dedup/prioritization, home suggestions, Windows insight) to
`gemini-2.5-flash-lite` directly — see `ModelQoS.Gemini.lightweight`
(macOS) and the Windows assistant model pins. Task extraction stays on
`gemini-2.5-flash`: Flash-Lite measurably fails its prompt contract there
(omi-knowledge-base, vertex-pt-flash-spend, 2026-08-17 overflow bakeoff).

## Durable runtime env

`desktop-backend` compose (`backend/deploy/runtime_env/_base.yaml` →
`desktop_backend`) and the Cloud Run deploy workflows must keep:

- `USE_VERTEX_AI=true`
- `GOOGLE_CLOUD_PROJECT` = `based-hardware` (prod) / `based-hardware-dev` (dev)
- `GCP_LOCATION=us-central1`

`GEMINI_API_KEY` remains only for BYOK / emergency leftover surfaces.

## Out of scope leftovers

Realtime token mint (`desktop_realtime.py`) and the omni Live websocket
(`omni_relay.py`) still use AI Studio. Vertex Live is not wired. Those are not
the high-volume Flash text bill.

Single `embedContent` uses Vertex `:predict` when a project is set.
`batchEmbedContents` stays on AI Studio (incompatible Vertex batch shape).

## How to verify after deploy

- Cloud Monitoring `consumed_token_throughput{request_type=dedicated, model=gemini-2.5-flash}` should move
- Gemini API Flash daily $ should drop
- PT SKU stays flat (~$290/day)
- Proxy logs: `provider_route=vertex_ai`, not `ai_studio`, for server-paid Flash

Incident: 2026-08-04 cutover. GitHub #6935 / SCA-323.
