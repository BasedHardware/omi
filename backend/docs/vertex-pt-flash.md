# Vertex Provisioned Throughput reservation state

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
declared reservation states, overflow ladder, reachability table, the capacity
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

The 429 to a `dedicated` request is consistent with both no order and a saturated
order. It cannot prove either. Only explicit PT traffic metadata teaches active state. Note the message reads lowercase `provisioned throughput` where
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

## Reservation state and automatic cutoff

Orders are declared in `backend/config/vertex_reservations.py`: model, dedicated
location, optional location override, **exclusive order identity**, unknown-state
capacity, overflow mode and thinking level. Both current entries describe the
same single 5-GSU order: 2.5 Flash at **us-central1**, 3.8 Flash at the declared
target location (default `us`). They are not two concurrent orders. A second
purchased order must have a different identity before serving it.

`ReservationState` shares bounded evidence through Redis across Cloud Run
instances and gateway pods. Production desktop-backend uses `DESKTOP_REDIS_*`,
so gateway chart bindings use its existing password secret. Before rollout,
provision `<env>-omi-reservation-runtime-config` in the gateway namespace with
`REDIS_DB_HOST` and `REDIS_DB_PORT` matching desktop-backend exactly (dev uses
its desktop `REDIS_DB_*` configuration). These are non-secret ConfigMap values,
not new Secret Manager entries. The chart references are mandatory: a missing
ConfigMap prevents a new pod starting. Host/port values and connectivity could
not be inspected under this task's no-production-access rule. Do not substitute
the backend's separate Redis pool. Keys include the compute project and all declared order locations,
expire after 48 hours idle, and contain only per-model timestamps, counters,
states and probe leases. No user/request identity or content is stored.
Transactions use WATCH/CAS with three attempts and a 300ms whole-operation bound;
Redis time owns ordering. Missing, malformed or unavailable storage cannot
confirm inactivity. Local positive dedicated evidence can still serve prepaid
capacity during an outage, but no local negative evidence can refuse a client.

State is `active`, `inactive`, or `unknown`, with its reason and observation
timestamps. No order-list/control-plane API is called. An authenticated paid
request can lease **one** synthetic `Reply OK.` dedicated probe for one declared
model; each model has a fleet-wide 600-second lease. One-second probe deadline,
16 output tokens, no automatic shared recovery for these synthetic probes.
Normal requests also publish strict dedicated successes immediately. No startup
poller or orphan background worker; no demand means no inference. Demand in
*any* declared model probes all entries, including an inactive/refused old lane,
so the detector can recover after refusal without forwarding user content.

Automatic inactivity requires **all** of:

1. At least four spaced capacity-signature failures spanning at least 1,800
   seconds; no dedicated success since the first failure.
2. No gap over 900 seconds between failures, and the newest failure no older
   than 900 seconds. Errors other than the capacity signature reset continuity.
   Failures closer than 300 seconds count once (tolerates probe completion jitter).
3. Positive `PROVISIONED_THROUGHPUT` success on another model declared as the
   **same exclusive order**, newer than the failure-window start and no older
   than 900 seconds.

A 429 of any wording, or arbitrarily many saturated-order failures alone, never
satisfies condition 3. A no-order 429 is still indistinguishable from saturation.
This detector's additional evidence is the positive exclusive-order move, not
an error-message heuristic. Safety is conditional on the single-order declaration
being true; duplicate/concurrent orders mislabeled as one invalidate that proof.
The policy makes no impossible claim that inference errors alone prove absence.
Any strict 2xx + PT trafficType response resets all failures and restores active
immediately. Missing traffic metadata and 3xx responses never teach state, even
where legacy wire handling still accepts the body. Active positive evidence
expires to unknown after 24 hours; expired negative evidence also stops refusal.
Typical detection under steady traffic takes 30–40 minutes, not the exact instant
Google fulfils the change. If the new endpoint is wrong or never answers dedicated,
cutoff waits rather than risking a false disablement.

### Declared actions

`POLICIES` defines lane dispositions; `policy()` resolves model defaults.
`vertex_pt_routing.py` remains pure and accepts state/protected-model inputs.
Both gateway and direct kill-switch paths consume it. There is no promotion latch
that implicitly revokes another model. More than one active/protected model is
excluded from overflow/fallback ladders, including during ambiguous transitions.

| Lane / requested model | Active | Inactive | Unknown |
| --- | --- | --- | --- |
| Identified macOS legacy 2.5 task loop | Dedicated | Refuse | Dedicated |
| Windows tasks/focus, macOS dictation/suggestions, unknown desktop, explicit backend 2.5 | Dedicated | Same model shared | Dedicated |
| 3.8 new extraction | Dedicated | Same model shared | Same model shared, bounded discovery |
| Client-pinned Lite, Pro remap, BYOK | Existing policy | Existing policy | Existing policy |

Refusal is the shipped tool loop's normal zero-task terminator, with bounded
refusal headers; it never invokes a provider or charges metering. It neither
prompts an update nor stops future normal capture requests. Observe mode increments
`omi_vertex_reservation_policy_total{action="would_refuse"}` and serves normally;
enforce mode records `action="refuse"`. Decisions use closed model/state/lane/action
labels. `vertex_reservation_transition` records state/reason/time on shared state
changes; `vertex_reservation_policy` and `vertex_reservation_probe` record routing
and synthetic usage without content or raw User-Agent. Gateway decisions also log
which capacity the state selected. Storage fail-open uses standard fallback telemetry.

[Client audit, lane costs, release tags, rollout dependency and smoke limits](vertex-reservation-lane-audit.md).
Default enforcement will suppress a capable current build's **flag-off** old loop
too. Complete the eligible macOS flag ramp before effective cutoff, or explicitly
hold observe mode. This PR does not override client consent/cohort flags.

### Next year's move: 3.8 Flash to model X

Add X to `RESERVATIONS` with the same order identity and its explicitly approved
location; keep 3.8 declared so it remains observable. Set the desired unknown and
overflow actions; declare the affected lane's inactive action in `POLICIES`.
Add the normal model allowlist, price, thinking and gateway-lane declarations if X
is a new served model, and test its wire contract. Keep distinct orders distinct.
No new transition, storage, lease or detector code is needed. After old clients
retire, remove their policy/model declaration and corresponding tests together.
Never discover `global` automatically.

### Operator runbook

Before the move: provision the shared-store ConfigMap described above, then
deploy the password/chart bindings and both serving images;
verify both services see the same project/location-scoped evidence. Confirm the
order's location and approve global residency separately if required. Finish the
eligible macOS pipeline ramp or hold observe mode. Watch bounded probe events:
old dedicated success; target capacity errors until fulfilled. Missing store or
target positive evidence means no automatic cutoff.

On the day: target PT successes make it active independently. Old dedicated errors
still use the original 3.1 Flash-Lite overflow during the confirmation window
(the brief's suspected quality change is real). After sustained evidence,
old becomes inactive; tagged macOS legacy loops stop spending, preserved lanes
stay 2.5 shared, and new extraction stays dedicated. Follow the refusal count and
state transition events; no operator must watch the moment of fulfilment.

False detection: set `OMI_VERTEX_RESERVATION_STATES` to
`{"gemini-2.5-flash":"active"}` on **both** services, or set the BFF's
`OMI_VERTEX_LEGACY_TASK_MODE=observe` to restore service immediately. `inactive`
forces the reverse direction; `unknown` returns conservative defaults; `auto`
or removing an entry uses evidence again. These JSON overrides beat the existing
single-order `OMI_VERTEX_PT_MODEL` pin and are read at request boundaries.
Invalid JSON fails open to unknown and emits a bounded error. Do not erase the
shared evidence to clear a false detection: the first real dedicated success
clears it transactionally. A missing/wrong shared binding, endpoint or permission
must be repaired before treating unknown as evidence of no order.

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
| `OMI_VERTEX_RESERVATION_STATES` | JSON model → `active`/`inactive`/`unknown`/`auto`; highest priority, read per request; invalid configuration becomes unknown. |
| `OMI_VERTEX_LEGACY_TASK_MODE` | `enforce` default; `observe` counts would-refuse but serves normally. |
| `OMI_VERTEX_PT_MODEL` | Pins the reservation model, beating auto-detection in both directions. Must name a declared company-paid anchor (`gemini-2.5-flash`, `gemini-3.8-flash`, `gemini-3.1-flash-lite`, `gemini-2.5-flash-lite`); anything else — in particular a Pro or image-output model — fails the request closed instead of serving it (SCA-481). |
| `OMI_GEMINI_OVERFLOW_MODEL` | Pins the overflow model. Rejected at resolution time if it equals the reservation or names anything outside the declared company-paid anchors (SCA-481); the request then keeps its own error instead of overflowing. |
| `OMI_GEMINI_OVERFLOW_ENABLED` | `false` disables cheaper overflow ladders; existing-model full reservations return 429. Gateway target discovery/full-capacity attempts retain same-model shared recovery to preserve extraction precision. |
| `OMI_VERTEX_PT_TARGET_LOCATION` | Dedicated target order location. Default US multi-region; regional/global require an explicit declared order location. Global requires residency sign-off. Shared target traffic retains its residency default. |
| `OMI_VERTEX_GLOBAL_LOCATION` | Multi-region for families with no regional endpoint. Default `us`. Setting `global` widens data residency worldwide — see above before flipping it. |

## Keeping the reservation for work that must be Flash

The 13,450 tok/s cap can burst to exhaustion, so the proxy keeps low-value
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

Dedicated attempts send `X-Vertex-AI-LLM-Request-Type: dedicated`; shared attempts send
`X-Vertex-AI-LLM-Request-Type: shared`. Only strict 2xx responses reporting
`usageMetadata.trafficType=PROVISIONED_THROUGHPUT` establish active evidence.
