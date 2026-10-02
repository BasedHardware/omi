# Vertex Provisioned Throughput: 2.5 Flash to 3.8 Flash

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


## Where the policy runs since the gateway move (2026-08)

Company-paid desktop `generateContent` / `streamGenerateContent` /
`embedContent` now hop the LLM gateway (`OMI_LLM_GATEWAY_FEATURE_MODE=gateway`):
`routers/desktop_proxy.py` stays the BFF (auth, trial paywall, redis metering,
body limits, model allowlist) and translates Gemini JSON ↔ the gateway's
OpenAI surface (`utils/llm/desktop_gemini_gateway.py`). The PT policy itself —
pin, promotion latch, overflow ladder, reachability table, the capacity
header, and the regional vs multi-region host split — lives in the gateway's
`VertexGeminiProvider` (`backend/llm_gateway/gateway/providers.py`), driven by
the same `backend/utils/llm/vertex_pt_routing.py` this document describes:
there is no second policy. The desktop proxy keeps its in-process copy only
for the `FEATURE_MODE=off` kill-switch path. The gateway deployment must
therefore keep `GOOGLE_CLOUD_PROJECT` and `GCP_LOCATION` set on the
`llm_gateway` service too, and the operator env pins
(`OMI_VERTEX_PT_MODEL`, `OMI_GEMINI_OVERFLOW_MODEL`,
`OMI_GEMINI_OVERFLOW_ENABLED`, `OMI_VERTEX_GLOBAL_LOCATION`) apply to the
**gateway** process once feature mode is on.
## Model prices (Vertex list snapshots)

| Model | Input $/1M | Output $/1M |
| --- | ---: | ---: |
| `gemini-2.5-flash-lite` | 0.10 | 0.40 |
| `gemini-3.1-flash-lite` | 0.25 | 1.50 |
| `gemini-2.5-flash` | 0.30 | 2.50 |
| `gemini-2.5-pro` | 1.25 | 10.00 |
| `gemini-3.8-flash` | 1.50 | 7.50 |

Legacy prices were captured 2026-08-18; 3.8 prices are the authorized
2026-10-02 benchmark snapshot. Reservation fees are separate.

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

**Moved order location is not established.** On-demand 3.8 Flash was verified
on `locations/us` in the authorized 2026-10-02 benchmark. Dedicated requests
use `OMI_VERTEX_PT_TARGET_LOCATION`, defaulting to the existing US multi-region.
Set it to the order's declared region, `us`, or `global` before migration.
Only target-model dedicated attempts use that location; shared target attempts
stay on the existing US endpoint. A regional dedicated publisher 404 retries
US shared without marking the whole model unavailable. No request discovers
`global` automatically. A global order requires explicit residency approval:
its dedicated requests can be served worldwide. Order discovery/control-plane
access was outside the authorized experiment; regional/global dedicated
successes are hermetic tests, not evidence of a live order.

## Fallback chains and learned reachability

Every model the proxy can route to declares its fallback chain as data, in
`MODEL_FALLBACKS` in `backend/utils/llm/vertex_pt_routing.py`:

| Model | Falls back to |
| --- | --- |
| `gemini-3.8-flash` | `gemini-3.1-flash-lite`, `gemini-2.5-flash-lite` |
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
- **Never upward in price.** Each chain is non-increasing in input and output
  price (`PRICE_PER_MTOK_IN`, `PRICE_PER_MTOK_OUT`), so a degraded request
  cannot cost more than the one it replaces. This is also why
  `gemini-2.5-flash-lite` is terminal: it is the floor of the ladder and the
  model the desktop clients pin directly. A lane admitted to a costlier model
  on behalf of a cheaper origin has a second ceiling — see "Moving a lane onto
  PT".
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

The table is historical evidence for 2.5 and 3.1 Flash-Lite; those lanes retain
`thinkingBudget`. New 3.8 Flash requests use `thinkingLevel: low`, verified on
`us` in the 2026-10-02 benchmark. The BFF preserves that level through the
gateway wire. `model_payload()` adapts each actual attempt: 3.8 always uses
low; a fallback to 2.5 replaces the level with budget 1024 (minimal becomes 0).
This avoids sending unsupported 3.x thinking levels to a 2.5 fallback.

## Migrating the reservation to `gemini-3.8-flash`

`PT_MODEL_TARGET` is 3.8 Flash. No code deployment is required when the order
moves, provided its location is already declared as above.

Capacity is explicitly selected with `X-Vertex-AI-LLM-Request-Type`
(`dedicated` or `shared`); implicit spillover would hide double billing.

1. Before migration, old-client 2.5 Flash stays on regional **dedicated**
   capacity. New 3.8 requests ask for dedicated target capacity at most once
   per instance per 600 seconds. An absent-order PT 429 or publisher 404 retries
   the same target on US **shared** capacity. Other failures do not promote.
2. Only a successful dedicated target response latches `_pt_target_ready`.
   Successful shared requests, generic 429s, 401s and 5xx responses prove
   nothing about an order. Both streaming and nonstreaming providers observe
   the actual model and capacity. The latch is process-local, so rollout is
   gradual as instances receive 3.8 traffic; there is no startup probe.
3. After promotion, new 3.8 requests use dedicated target capacity at its
   declared location. Old-client 2.5 requests keep **2.5 Flash**, regional,
   but now **shared/on-demand**. Pro remains the existing 3.1 Flash-Lite remap;
   client-pinned 2.5 Flash-Lite and BYOK remain unchanged. Remapping old Flash
   to 3.8 shared would raise both input/output prices, so it is disallowed.
4. Reserved overflow uses shared 3.1 Flash-Lite then 2.5 Flash-Lite, subject to
   reachability, live-reservation exclusion, and the lane's starting price
   ceiling. Old 2.5 overflow never probes the more expensive target. Price
   ceilings also apply to operator overrides and cross-family fallbacks.

Before migration 3.8 PayGo is incremental alongside the existing fixed fee.
After migration old-client 2.5 PayGo becomes incremental at $0.30/$2.50 per
million input/output tokens; 3.8's dedicated usage has prepaid marginal cost.
This workload alone does not fill the order. Moving other lanes remains a
separate evaluation and cost decision. Converting/cancelling an order is an
operator commercial action, not a routing effect.

`test_screen_task_vertex_transition.py` pins absent-order/shared behavior,
dedicated promotion at declared US/regional/global locations, old-client
pricing, thinking adaptation, and bounded metadata. Existing proxy/provider
contracts pin direct kill-switch and streaming recovery. No real order was
queried or changed by this PR.

## Never move dedicated traffic off a reservation early

Moving `gemini-2.5-flash` onto an on-demand model *before* the replacement
order is live pays the flat reservation fee for idle capacity **and** full
on-demand for every token — strictly worse than either alone. This is why the
capacity transition is gated on observed target capacity. Old Flash is never
remapped to the more expensive target.
`test_flash_stays_on_the_current_reservation_until_target_capacity_exists`
holds that gate.

## Moving a lane onto PT

The reservation is a flat prepay, so a latency-tolerant lane that today runs
PayGo on a cheaper model can be admitted to `gemini-2.5-flash` at ~$0 marginal
cost while the order is idle. That admission is a cost trap the moment the
reservation is full: the flash overflow ladder prefers `gemini-3.1-flash-lite`
PayGo ($0.25 in / $1.50 out), 3.75x the output price of `gemini-2.5-flash-lite`
($0.10 / $0.40).

A lane that moves declares its **origin model** in `LANE_OVERFLOW_ORIGINS`
(`FEATURE_PT_OVERFLOW_ORIGIN` in `model_config.py`), keyed by feature name.
The gateway stamps that origin onto the route (`pt_overflow_origin`); the
desktop kill-switch reads the same table by the requested model. Overflow and
fallback candidates are then kept only when both `PRICE_PER_MTOK_IN` and
`PRICE_PER_MTOK_OUT` are at or below the origin
(FC-degraded-fallback-exceeds-origin-price). No lower origin declared means the serving anchor is the ceiling. Do not change a feature's
route without declaring the origin in the same change.

Before moving any lane, re-read the hourly headroom table (C020, weekdays
2026-09-12…09-23 UTC). Every hour had at least ~8,490 tok/s free of the 13,450
tok/s cap, and flash-lite's steady load fits after the output-burn conversion
(lite burns 4x, flash 9x). Its bursts do not: a ~25k lite-unit burst is on the
order of 50k flash units, above the cap. Bursts must keep a
`gemini-2.5-flash-lite` overflow. The move itself stays eval-gated, per lane,
and is not this policy.

## Overflow is resolved against the live reservation

`OVERFLOW_PREFERENCE` is a ladder, not a pin, and
`resolve_overflow_model()` never returns the model that currently holds prepaid
capacity. If an operator declares a Lite model as the reservation, overflow steps past
it automatically. The default 3.8 target is never an overflow candidate. Pinning overflow to
`gemini-3.1-flash-lite` would, after promotion, dump degraded traffic onto the
budget the quota exists to protect — that is
`FC-degraded-fallback-consumes-protected-budget` (PR #10686), and the guard is
`test_overflow_never_targets_the_live_reservation`.

## Operator overrides

These knobs are read per request, so a bad promotion can be corrected without
shipping code.

| Env | Effect |
| --- | --- |
| `OMI_VERTEX_PT_MODEL` | Pins the reservation model, beating auto-detection in both directions. Must name a declared company-paid anchor (`gemini-2.5-flash`, `gemini-3.8-flash`, `gemini-3.1-flash-lite`, `gemini-2.5-flash-lite`); anything else — in particular a Pro or image-output model — fails the request closed instead of serving it (SCA-481). |
| `OMI_GEMINI_OVERFLOW_MODEL` | Pins the overflow model. Rejected at resolution time if it equals the reservation or names anything outside the declared company-paid anchors (SCA-481); the request then keeps its own error instead of overflowing. |
| `OMI_GEMINI_OVERFLOW_ENABLED` | `false` disables overflow entirely; a full reservation then returns 429 to the client. |
| `OMI_VERTEX_PT_TARGET_LOCATION` | Dedicated target order location. Default US multi-region; regional/global require an explicit declared order location. Global requires residency sign-off. Shared target traffic retains its residency default. |
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
(macOS) and the Windows assistant model pins. Flag-off task extraction stays on
`gemini-2.5-flash`; `screen_task_jev_gate` enables the one-call 3.8 path
([pipeline contract](../../desktop/macos/docs/screen-task-pipeline.md)). Flash-Lite measurably fails its prompt contract there
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
