# Proactivity v2 spine contract

Status: **G1 accepted with amendments; Phase 2 implementation authorized.**
Date: 2026-10-03. Branch: `lane/proactivity-v2-spine`.
Integration destination: `lane/proactivity-v2`; no PR to main from this lane.
Source baseline: `159df547f4dc4657af0c92675e99a0202949711a` (fetched main).

## 1. Scope and binding decisions

One backend-owned item ledger, feed, outcome API and Budget Authority serve all
v2 producers and clients. Producers retain their signal and generation logic.
No plugin framework, director, new scheduler, client budget, or second cost ledger.
Adding a producer means a registration row and its event-driven caller.

All v2 generation and delivery require server-resolved `proactivity_v2=true`.
Model-driven work is paid-only in practice: free/basic has a zero-dollar cap.
Mentor additionally requires its existing opt-in and `MENTOR_PIPELINE=v2` or `cohort` (server-side per-user selection).
Daily recap generation, scheduling, storage and routes remain outside this budget;
interesting-memory review remains unchanged. Neither becomes a v2 model producer
in this build. Task follow-ups never create, complete or modify a task themselves.

The integration owner owns old-path deletion, client cards, producer wiring and
rollout. Focus remains on its legacy desktop proxy path with existing proxy
quotas, outside the v2 budget, until a later port. Legacy mentor is the other
transitional exception. The guarantee is **every v2 producer is hard-capped**.
Daily recap stays outside both this budget and this ledger in this build.

### Review amendments G1 (accepted 2026-10-03)

Neo and Plus budget reference prices are $20. Producer targets may be provisional
(10% acted within 24h, $0.25 per acted item; negative-rate alert above 5%). Mentor
retains its existing push channel and chat thread; follow-ups start feed-only.
Server-observed replies/completions share the outcome reducer. Jev receives a
$0.042/M input, zero-output rate card and bounded request pricing. Focus and legacy
mentor are transitional exceptions. Follow-ups hook the existing action-item
reminder scheduler; spine adds no scheduler. These amendments supersede the
original measurement-before-enable restrictions below.

## 2. Reuse and deliberate differences

| Existing source | Reuse / boundary |
| --- | --- |
| `utils/llm/managed_spend_ledger.py` | Same `llm_gateway_attempts` event schema; do not introduce direct provider calls. Its best-effort background write is not budget authority. |
| `llm_gateway/gateway/accounting.py` | `rate_card_for`, normalized provider usage, `build_accounting_event`, `estimated_cost_micro_usd`; count every attempt, including errors. |
| `database/llm_gateway_accounting.py` | Immutable attempt IDs and create-once persistence; existing rollups are projections, never available balance. |
| `llm_gateway/gateway/jit_budget.py`, `executor.py` | Existing durable reservation and immediately-before-provider-call pattern. Port the narrow pattern into v2 ownership before the other lane removes JIT; no runtime dependency on retired JIT modules. |
| `routers/chat.py`, plan catalog | Dollars already have quota unit `cost_usd`. Keep proactivity a separate daily allowance, not a debit against Architect monthly chat. |
| `config/plan_catalog.json` and generator | Canonical plan IDs, paid status, aliases and a generated budget policy; no Stripe request at admission. |
| `database/redis_db.py` | Shared lazy connection and atomic/token-owned Lua conventions. Do not reuse expiring notification leases as refundable money reservations. |
| `utils/notification_dispatch.py` | Existing typed dispatch boundary and FCM transport; add one v2 notification kind. |
| `utils/llm/proactive_notification.py` | Preserve the additional nine-per-day interruption ceiling as a v2 push ceiling; it does not replace dollar admission. |
| `utils/other/notifications.py`, `models/daily_summary.py`, `routers/users.py` | Reuse typed list/detail response and linked-object conventions; leave recap accounting and local-day scheduling alone. |

## 3. Producer registry

Source: `backend/config/proactivity_v2_producers.json`; a small validated loader,
not generated classes per producer. Each row has these required fields:

- `name`, `version`, `enabled`, `paid_only`, `signal`, `trigger`, `dedupe_scope`.
- `max_calls_per_user_utc_day` (provider attempts, including rejected generations,
  gate calls, retries and prefilters), `max_calls_per_item`, `gateway_lane`.
- `max_request_bytes`, `max_output_tokens`, `expected_micro_usd_per_delivery`,
  `measurement_status`, `measurement_reference`.
- `min_acted_24h_rate`, `max_micro_usd_per_acted_item`, `kill_min_deliveries`,
  `evaluation_window_days`, `push_earned`, `push_evidence_reference`.

Rows may be enabled with `measurement_status=provisional` and numeric bars:
`min_acted_24h_rate=0.10`, `max_micro_usd_per_acted_item=250000`.
Provisional expected micro-USD/delivery: mentor 60000 (2026-10-03 reconstruction),
follow-ups 2000. Negative rate alerts above 5% but is not a kill input. Measured
benchmark/baseline evidence replaces provisional values via a versioned change.
Missing numeric targets still reject enablement; provisional rows obey the same
>=200 mature-delivery kill latch.

| Name | Signal / event trigger | Identity | Initial safety ceilings | Estimate, target and kill criterion |
| --- | --- | --- | --- | --- |
| `conversation_mentor_v2` | Newly eligible conversation segment revision after existing deterministic debounce; existing mentor opt-in; no polling timer | conversation ID + eligible revision + producer version | 60 provider calls/user/UTC day, at most 6/item (producer amendments below); text request <=32,768 bytes, output <=2,048 tokens/call | Provisional estimate 60000 micro-USD; 10% acted, 250000 micro-USD/acted; kill below configured acted rate OR above configured cost/acted after >=200 mature deliveries. |
| `commitment_followup` | Due/overdue transition of an already-extracted, still-open action item, hooked by producer lane into `routers/action_items.py::_schedule_action_item_reminder`; a repeated scan is not a new event | action-item ID + due revision + transition kind + producer version | 9 calls/user/UTC day, exactly <=1/item; text request <=8,192 bytes, output <=512 tokens | Provisional estimate 2000 micro-USD; 10% acted, 250000 micro-USD/acted; same >=200 mature-delivery kill rule. |

These call ceilings are proposed conservative engineering backstops, not measured
quality targets. Gateway lane is initially the existing `omi:auto:proactive-notification`
text lane, with producer-specific accounting feature tags. Model identity comes
from the resolved route, not a price duplicated in the producer registry. Additional
paid prefilters consume this same allowance; no Jev/direct-provider budget escape.
No model retry for either producer in the initial contract; a later retry needs a
new reserved attempt and counts against both ceilings.

## 4. One item ledger and retention

Canonical path: `users/{uid}/proactivity_items/{item_id}`, on the customer-data
Firestore project. Use the customer client explicitly on backend and gateway;
never infer authority from a compute project's default credentials.

`item_id` is the first 32 hex characters of SHA-256 over a canonical tuple of UID,
producer, version and source event identity. The source identity is not prompt
text. Claim/create is transactional and exactly once across all surfaces. An
item is created before its first model call, including evaluations that ultimately
say nothing. Thus silent, failed and suppressed work is still cost-attributable.
Pure admission denials before any claim emit telemetry only, not an empty item.

Fields (storage timestamps are Firestore UTC timestamps; amounts are integers):

| Group | Fields / values |
| --- | --- |
| Identity | `schema_version=1`, `item_id`, `producer`, `producer_version`, `source_kind`, `source_id`, `source_revision`, `source_event_id`, `source_surface` (`server`, `ios`, `android`, `macos`, `windows`), `account_generation` |
| Lifecycle | `created_at`, `updated_at`, `expires_at`, `state` (`claimed`, `ready`, `silent`, `failed`, `suppressed`), bounded `terminal_reason`, `claim_token` |
| Model attempts | bounded `attempts` map keyed by server call ID: step, request/attempt IDs, UTC budget day, reserved/charged/priced micro-USD, rate-card ID, state (`reserved`, `settled`, `unknown`, `released`), reservation token hash |
| Mentor measurement | optional `usefulness_score`, one finite numeric Jev probability in [0,1]; no judge state, transcript, rationale, question or trace |
| Item cost | `reserved_micro_usd`, `charged_micro_usd`, `estimated_cost_micro_usd`, `cost_status` (`pending`, `estimated`, `indeterminate`, `none`); numeric priced subtotal is never presented as a complete total when indeterminate |
| Content | encrypted `content` containing bounded title (120 characters), body (1,000 characters), linked object kind and ID; no transcript, OCR, full prompt or model trace |
| Delivery | `feed_available_at`, `delivered` boolean, `delivered_at`, `delivery_channel` (`none`, `feed`, `push`), `delivery_surface`, `push_state` (`not_earned`, `eligible`, `claimed`, `accepted`, `failed`, `unknown`, `suppressed`) |
| Outcome | `acted_24h` boolean, `first_action`, `first_action_at`, `negative` boolean, `negative_kind`, `negative_at`, `dismissed` boolean, bounded per-action first-event ID and server time |

Internal absent timestamps/references are omitted, not sentinel dates. This does
not imply nullable HTTP fields. Lifecycle updates read and write transactionally;
never overwrite an earlier delivery/action with a later device's observation.
A source no longer owned/visible to the user is not served. Source deletion clears
its content/target and suppresses delivery; account deletion recursively removes
items and budget days and fences late gateway/outcome writes with account generation.
Use the existing encryption and account-deletion boundaries, with explicit tests.
Client Firestore rules deny direct access; reads/writes go through authenticated API.

Retention: `expires_at = created_at + 90 days` for item records and budget day
records. Feed exposes previously delivered ready items for 30 days; an item with no
confirmed exposure is eligible only until creation+24h. First exposure after that
deadline is rejected, so an unseen stale card cannot enter a mature cohort. TTL is asynchronous cleanup, never admission or
visibility authority. Declare TTL deployment requirements for these collection
groups; coordinator provisions them before launch, not this lane. No payload
backfill. Content-free gateway attempts keep their existing retention policy.

### Firestore write budget

For an item with N model attempts and O distinct first outcomes:

- One item create; reserve writes item + day (2N); settle writes item + day (2N).
- One item terminal/content write; first confirmed delivery one item write;
  each first outcome one item write (O). Repeats are read-only.
- Optional push adds two item writes (claim + result) and one durable day-counter
  write, not one per device.
- A successful mentor usefulness judge adds one first-score item write; identical
  score retries are read-only. A first timeout adds one outcome write to retain its
  event ID, with no exposure, action, dismissal or negative metric effect.
- Existing gateway accounting adds one immutable attempt and one best-effort
  user-day rollup write per attempt (2N), already present today.
- Total nominal spine writes: **3 + 4N + O** without push; add **3** for push and **2N** existing
  accounting writes. Example: one call, feed rendered and acted = 8 spine writes
  plus 2 existing accounting writes. Silent item = 2 + 4N spine writes.
- Disabling adds one user-preference write. Producer-health refresh/kill adds one
  control document write per evaluation, amortized across items. TTL deletes are
  additional billed deletes. Transaction retries add reads, not extra logical writes.

These costs must be reported alongside model cost when judging economics; the
binding dollar cap specifically covers model attempts priced by the gateway.

## 5. Budget Authority

### Cap policy

Add a validated `proactivity_v2_budget` object to `backend/config/plan_catalog.json`
and emit it into `plan_catalog_generated.py`. It contains `fraction_basis_points=1000`,
`days_per_month=30`, and budget reference monthly price in cents per canonical
plan. These are David's budget reference prices, not a new checkout price source
(the catalog correctly makes Stripe authoritative for billed amounts).

`daily_cap_micro_usd = floor(monthly_cents * 10000 * 1000 / 10000 / 30)`.
Compute with integers (equivalently `monthly_cents * 1000 // 30`).

| Canonical plan | Reference monthly cents | Daily cap (micro-USD) | USD/day |
| --- | ---: | ---: | ---: |
| `basic` (`free` alias) | 0 | 0 | 0 |
| `operator` | 4900 | 163333 | 0.163333 |
| `architect` | 19900 | 663333 | 0.663333 |
| `unlimited_v2` | 2999 | 99966 | 0.099966 |
| `unlimited` (Neo) | 2000 | 66666 | 0.066666 |
| `plus` | 2000 | 66666 | 0.066666 |

Future unpriced paid plans use the *computed minimum* known paid cap and emit
`record_fallback(area='proactivity_v2', from_mode='plan_price',
to_mode='lowest_known_paid_cap', reason='price_pending', outcome='recovered')`.
No special allowance for developers, BYOK, trials, client-supplied plans or
unknown entitlements. Unknown plan/store failure denies. Resolve active canonical
plan server-side; expired plans use basic. A lower cap immediately stops new work
if existing charges exceed it; it does not erase spend. Upgrades allow only the
new cap minus the same day's existing charges. No separate per-device balance.

Reset at **00:00 UTC**, not user timezone: stable across devices, travel, timezone
edits and DST, aligns with gateway `date` and avoids balance-reset manipulation.
This is a calendar-day allowance, not a rolling 24h limit. Reservations belong
to their admission day even if settlement crosses midnight. A subsequent provider
call after midnight must reserve in the new day. No carryover.

### Python interface (internal only)

```python
class BudgetAuthority:
    def reserve(self, *, uid: str, item_id: str, producer: str,
                call_id: str, envelope: AttemptEnvelope) -> Reservation: ...
    def settle(self, *, reservation: Reservation,
               event: AccountingEvent) -> bool: ...
    def release_unsent(self, *, reservation: Reservation) -> bool: ...
```

`AttemptEnvelope` is constructed by gateway from the fully enriched provider
request: actual provider/model, bounded input/output, price-card ID and request
fingerprint. No caller-supplied dollar estimate. `Reservation` binds UID, account
generation, item, producer, call ID, day, nonce and reserved micro-USD. Duplicate
reserve returns an explicit already-reserved/terminal result without a capability
to call the provider again. Typed denials: `disabled`, `producer_disabled`,
`not_paid`, `budget_exhausted`, `call_limit`, `duplicate`, `unpriced`, `unavailable`.
No public reserve, settle, plan, cost or producer-selection endpoint.

### Durable balance, Redis keys and races

`users/{uid}/proactivity_budget_days/{YYYY-MM-DD}` contains `charged_micro_usd`,
`priced_micro_usd`, per-producer call counts, `blocked`, policy version,
`account_generation`, timestamps and expiry. Charged means settled actual plus
full worst-case holds. It is the *only durable balance*, not a second item ledger.

Redis key: `proactivity:v2:{<sha256(uid)>}:admission:<day>:<item_id>:<call_id>`.
Value: random owner token; `SET NX PX 30000`; token-checked Lua release. The hash
braces keep a user's keys in one cluster slot. This is a duplicate-work lease,
not money authority. There is deliberately **no Redis-only dollar counter**.
Use the shared connection but propagate failures rather than a fail-open wrapper.
Redis loss/restart can only lose this optimization, never spent dollars.

1. Gateway rechecks flag, registry health, user preference, paid plan and deletion
   fence. It acquires the Redis lease; errors deny before any provider call.
2. Firestore transaction reads account/plan, day, item and producer control before
   any writes. Checks identity, no existing call ID, per-item/day call ceilings,
   and `charged + worst_case <= current_cap`; writes hold to item and day together.
3. Only the unique newly committed reservation authorizes the current execution
   to enter the provider boundary. A duplicate handler, expired Redis lease or
   retried Firestore commit never authorizes another execution. No provider work
   inside a transaction callback. An uncertain commit response means do not call.
4. Settle atomically replaces the full hold with the trusted event estimate and
   records attempt ID on the item. Repeat identical settlement is a no-op;
   conflicting cost/attempt identity is denied and alerted. Failed calls with
   priced usage still debit actual cost. Call counts are never refunded.
5. A crash, timeout, cancellation, missing usage or missing settlement leaves the
   full hold. Mark unknown where possible and stop further calls for that item.
   Lease expiry never refunds money. `release_unsent` is allowed only by the
   owning gateway execution that can prove the provider boundary was not entered;
   it cannot be called by a client or a watchdog after a crash.
6. Firestore/Redis unavailability denies new work; settlement still attempts its
   durable Firestore transaction if Redis is down. If it fails, the hold remains.
   No in-memory allowance, direct provider fallback, or delayed best-effort debit.

Firestore serializes simultaneous calls across producers/instances/devices; Redis
is not a distributed lock correctness assumption. A missing day is initialized
transactionally; a missing item after an attempt is not recreated. Live day docs
must never be TTL-deleted. In case of durable-store restore/corruption, keep the
flag off until current-day balances are conservatively restored or UTC resets.
This extra durable write cost is deliberate: an evicted/reset Redis counter would
otherwise mint another full daily allowance, violating the hard cap.

### Worst-case pricing and gateway enforcement

Reserve inside `executor.py` immediately before each provider attempt, after route
resolution/enrichment. Use existing rate cards; round the worst-case reservation
**up** to integer micro-USD. Settle with the existing accounting event's rounded
`estimated_cost_micro_usd`, not a second estimator and not invoice claims.

Initial producers allow text-only, nonstreaming, one provider attempt per call,
no tools, images, web search, persistent cache creation, provider SDK retries,
route fallback or direct SDK path. Output bounds include reasoning tokens: the pinned OpenAI model requires explicit `max_completion_tokens`; legacy `max_tokens` requests are rejected before admission. Bound
the complete serialized request plus provider framing with the supported model's
conservative token upper bound; reject models whose framing/tokenization cannot
be bounded. Price all input as uncached, at the applicable highest context tier;
no speculative cache savings or Flex discount in the reservation. The existing
JIT UTF-8 byte method is a precedent, not permission to ignore provider framing.

Actual estimate above hold is an invariant failure: retain actual spend, block the
user day and producer, emit critical telemetry. It cannot undo a provider charge;
preventing it requires hermetic bounds/route tests and refusing unsupported model
changes, not merely detecting overruns. Missing price cards deny before inference.

## 6. Gateway attribution and producer-facing seam

Trusted internal metadata: producer, item ID, call ID, producer version. Gateway
accepts these only from authenticated backend service calls, verifies them against
the existing claimed item, and rejects partial metadata. Public proxies must not
forward client-provided proactivity headers. Producer calls use:

```python
item = await claim_item(uid=uid, producer=name, source=source_event)
result = await run_proactivity_model(item=item, step="phrase", request=request)
# This function is gateway-only and propagates typed denied/unknown results.
await publish_item(item=item, content=content, target=target)
```

`claim_item` checks registry/flag/opt-in, source ownership and deterministic source
identity; `publish_item` rechecks them and refuses pending/unknown cost, deleted
sources, expired items or an already-terminal claim. A silent model result closes
the same item with cost, without a card. Mentor step names are `gate`, `generate`,
`critic`, `prefilter`, `usefulness` and `dedupe`; commitment uses `phrase`. Jev steps use
`omi:auto:jev-decisions`, priced as provider `openrouter`, model `typesafe/jev-1.13`
at 42000 micro-USD/M input tokens and zero output. Reserve the serialized Jev
request UTF-8 byte length plus bounded chat framing as input; only text requests
with bounded messages/schema are admitted. No cache discount is assumed. No producer-specific base classes.

Use existing accounting `feature` with allowlisted values
`proactivity_v2_conversation_mentor_v2` and `proactivity_v2_commitment_followup`.
`request_id` is a stable UUID per call, distinct from item ID; all attempts retain
it. The ledger's bounded attempts map links those UUIDs to item and step. Existing
`route_artifact_id`, configured/actual model and attempt ID identify the lane.
Thus grouping `llm_gateway_attempts` by feature alone attributes producer dollars;
a join is needed only for item outcomes. No new generic lane-tag schema is required.

PR #20184's owner retains desktop proxy lane attribution. Do not edit
`desktop_gemini_gateway.py`, `desktop_proxy.py` or its feature normalization in
this lane. On integration, consume its agreed tag vocabulary if it supersedes
the existing feature mechanism; do not install a competing desktop tag. Keep
v2 feature values distinct from the legacy shared `desktop_proactivity` tag.

V2 settlement must persist the same immutable attempt event synchronously (or
retain the hold and deny publication on failure). Existing asynchronous gateway
sink can retry the identical attempt ID safely. Best-effort rollup failure does
not lose the event. `LLM_GATEWAY_ACCOUNTING_ENABLED=false` denies v2 admission.

## 7. Public HTTP and generated clients

Routes live in `routers/proactivity.py`, Firebase authenticated using
`get_current_user_uid`. UID comes only from auth. No producer invocation route.
All HTTP fields are typed and non-null; optional request fields have non-null
defaults. Unknown request keys and invalid enum values are rejected. All timestamps
are UTC RFC3339 with `Z`. No arbitrary dictionaries, raw JSON casts or nullable
success responses. Transport failures use the client's typed error path.

### GET /v1/proactivity/feed

Operation ID `get_proactivity_feed`. Query `limit=20` (1..50), `cursor=""`.
Return `ProactivityFeedResponse`:

```json
{
  "schema_version": 1,
  "enabled": true,
  "items": [{
    "id": "0123456789abcdef0123456789abcdef",
    "producer": "commitment_followup",
    "created_at": "2026-10-03T09:00:00Z",
    "title": "Follow up on your commitment",
    "body": "Your saved action item is ready to revisit.",
    "target": {"kind": "action_item", "id": "synthetic-task-id"},
    "acted": false,
    "dismissed": false,
    "feedback": "none"
  }],
  "next_cursor": "",
  "has_more": false,
  "server_time": "2026-10-03T09:01:00Z"
}
```

Target kinds initially `conversation` or `action_item`; opening uses the existing
canonical detail route. No arbitrary deep-link URL. `feedback` is
`none|thumbs_up|thumbs_down`. Producer is a bounded string on the response so a
future producer row does not require an enum release on every client.

Descending `(created_at, document_id)` keyset pagination over ready items in the
last 30 days; unexposed candidates older than 24h are omitted. Opaque versioned cursor is validated and scoped to auth UID; never
client-controlled Firestore paths. Read at most 50 candidates/page, skip inaccessible
sources, and advance by last scanned document (a page can be empty with `has_more`).
Reads do not claim exposure. Flag false returns `enabled=false`, empty items;
flag/provider/store error returns 503, never a success-shaped empty feed.
No budget balances or cost fields on feed cards.

### POST /v1/proactivity/items/{item_id}/outcomes

Operation ID `record_proactivity_outcome`. `ProactivityOutcomeRequest`:

```json
{
  "event_id": "123e4567-e89b-42d3-a456-426614174000",
  "action": "opened",
  "surface": "ios",
  "channel": "feed"
}
```

Actions: `shown`, `opened`, `accepted`, `thumbs_up`, `replied`, `thumbs_down`,
`producer_disabled`, `dismissed`, `timeout`. Surface: `ios|android|macos|windows`;
channel: `feed|push`. Client UUID is for replay correlation, not money authority.
Server receive time is authoritative; no client clock or backdated metric credit.

Response `ProactivityOutcomeResponse`:

```json
{"item_id":"0123456789abcdef0123456789abcdef","recorded":true,"acted_24h":true,"negative":false}
```

Missing/foreign/expired item = 404, invalid event = 422, conflicting reuse of an
event ID = 409, storage unavailable = 503. Same event retry or same action from a
second device returns `recorded=false` and current aggregate flags. Store at most
one first event per action (10), not an unbounded event subcollection. For ready
unexpired items, outcomes remain accepted while the rollout flag is off: rollback
must not erase measurement or prevent opt-out. No new delivery is authorized.

`shown` means card actually rendered, not fetched, push accepted or app opened.
First `shown`, or a valid positive action that implies exposure, sets delivery
once. `opened` is sent after the linked object successfully opens, not a click
on a missing object. `accepted`/`replied` are sent only after the underlying
canonical action succeeds; this endpoint does not perform those actions.
`timeout` retains its first event ID and server timestamp in the same bounded
per-action map: first receipt returns `recorded=true`, retries/other timeout IDs
return `recorded=false`. Reusing the retained timeout UUID for another action (or
another action's UUID for timeout) returns 409. It has no exposure or value effect
and never records dismissal, negative feedback or engagement. Explicit `dismissed` hides a card but is not a
negative metric. First positive action within [delivery, delivery+24h] makes
`acted_24h=true` permanently. A later thumbs-down/disable also records a negative;
never rewrite historical positive evidence. Outcomes can be both acted and negative.
Offline events received after 24h are retained as actions but not credited within
24h; clients retry the same event ID, scoped to the signed-in account.

`producer_disabled` atomically sets
`users/{uid}/proactivity_preferences/{producer}.enabled=false` and records the
item negative; it wins admission and push rechecks. Feed hides that producer's
items. Re-enable/settings UI is outside this spine; any future re-enable must be
an explicit user action, never rollout state or process restart.

### Server-observed outcomes

Internal `record_server_outcome(item_id, action)` runs in the authenticated owner
context (explicit `uid` at the database boundary), never as an HTTP route. It uses
the same transactional first-event reducer, with source/surface `server` and a
deterministic event ID. The first user message in the mentor thread within 24h
of item delivery is `replied`; canonical completion of the linked follow-up task
is `accepted`. Producer lanes attach these hooks and supply the owner/item mapping.
Push transport acceptance supplies a server delivery anchor for this legacy
channel, separately marked `server_push`; it does not fabricate client exposure.
Server-observed positive action confirms exposure if no client receipt exists;
cohort reporting distinguishes server-observed and client-observed evidence.

### Generated boundary and ownership

Add `/v1/proactivity` to the app-client OpenAPI exporter. Generate from Pydantic
models into `docs/api-reference/app-client-openapi.json`, Dart
`app/lib/backend/schema/gen/proactivity_wire.g.dart`, and Swift
`Desktop/Sources/Generated/OmiApi.generated.swift`. Extend generator target lists,
never hand-edit outputs. Dart uses generated DTOs inside a thin typed HTTP adapter;
Swift uses generated client functions through existing auth configuration.
Shared fixture `contracts/parity/proactivity_v2.json` covers feed, outcomes,
unknown producer names, malformed/null fields and UTC times on both clients.

The integration/client lane owns cards, deep-link dispatch, local outbox, sign-out
purge, rendering tests, localization and addressability. It must call this exact
outcome endpoint on mobile and desktop. No second platform-specific outcome route,
local durable insight feed or notification-to-chat transcript is added by spine.

## 8. Feed first; earned interruption only

Publishing makes the item available in the feed and costs no additional model call.
Delivery/value denominator is confirmed exposure, not availability or FCM success.
Report availability, first exposure, transport acceptance and action separately.

Mentor starts `push_earned=true`, evidence `legacy mentor channel, grandfathered 2026-10-03; subject to kill rule`. It still obeys the aggregate nine/day ceiling and every recheck. The mentor producer lane continues writing to its existing mentor chat thread.
Follow-ups start `push_earned=false`. New promotion requires >=200 mature,
confirmed feed deliveries meeting that producer's measured thresholds, an evidence
reference and coordinator-approved config change. There is no automatic promotion.
A kill automatically revokes push and model admission.

Even after promotion: require current master flag, producer health, user opt-in,
notification permissions/preferences, source validity, no previous exposure/action,
and aggregate <=9 pushes/user/UTC day across v2 producers. Local quiet hours and
existing notification suppressions apply; denied push leaves the feed intact.
Redis push key `proactivity:v2:{<sha256(uid)>}:push:<day>` uses atomic bounded
reserve with expiry next UTC midnight+48h; a matching durable day counter in the
same item/day transaction is authoritative, so cache loss cannot resend 9 pushes.
Push reservation is not refunded after an ambiguous transport result.

Transaction claims an item's push once before `dispatch_notification_async`.
FCM acceptance is `push_state=accepted`, never confirmed delivery. Transport timeout
is `unknown` and is not automatically retried: exactly-once FCM delivery cannot be
promised. Payload carries item ID and target identity; generic notification copy
avoids exposing encrypted advice on the lock screen. Client fetches authenticated
feed content and records exposure/open using that ID. No direct FCM calls by producers.

## 9. Measurement, flags and telemetry

Per producer, primary value = unique acted-within-24h items / unique delivered
items, with delivered items counted only after their full 24h opportunity. Cost
per acted = **all producer model spend, including silent/failed generation**, in
the same evaluation cohort / acted items. Do not divide only successful card cost.
When acted=0 cost/acted is undefined/infinite, not zero. Any unpriced/unknown cost
makes the verdict ineligible for passing; show priced subtotal and held ceiling.

Evaluation uses seven complete UTC creation days ending >=48h ago. Publication
expires at creation+24h, so every exposure's 24h window has matured. Query all item
cost and booleans for that creation cohort, not just the last 200 successes.
At >=200 delivered items, below target acted rate OR above target cost/acted kills
the producer. Below 200 is `collecting`, never proof of earned push. Negative rate
is reported separately; a user's disable takes effect immediately.

`proactivity_producer_controls/{name}` stores version, `enabled|killed`, verdict,
cohort bounds, totals, checked time, and reason. Admission refreshes stale (>60s)
health via bounded Firestore aggregate queries (COUNT/SUM, no content scan),
transactionally latches a kill, then denies. Query/store failure denies new model
work rather than using an indefinitely stale passing verdict. No new cron/workflow.
A late metric correction never silently re-enables a killed row; changed thresholds
or enablement require explicit coordinator action with new version/evidence.

| Control | Authority / default |
| --- | --- |
| `proactivity_v2` | Server PostHog exposure flag; absent/unknown/error = off for generation and push; no UID bypass. |
| `MENTOR_PIPELINE` | Server env `legacy|v2|cohort`, default legacy; cohort resolves the same server-side `proactivity_v2` flag/client/cache as admission: true selects v2, false/unknown/error selects unchanged legacy; invalid denies mentor invocation. Mentor owner implements exclusive dispatch; v2 failure never falls back to legacy automatically. |
| Producer registration / health | Provisional targets permit enablement; durable kill overrides registry enabled. |
| User producer preference | Explicit false wins every admission/publication/push check. |
| `LLM_GATEWAY_ACCOUNTING_ENABLED` | Must be true for v2; existing sink semantics unchanged for other traffic. |

Server flag resolution caches both true and false per UID for **300 seconds**
per process, with a **60-second** failure cache and a 4,096-entry LRU bound.
Concurrent same-user misses share one lookup. Errors still select legacy for
cohort mentor and deny v2 admission; a content-free warning records exception
type and HTTP status at most once per minute per process. Realtime mentor
validates the env value first, then runs its existing shared paid/opt-in,
buffering and debounce admission. Only admitted messages resolve a cohort flag;
`legacy`/`v2` env selection makes no flag lookup on this dispatch path (v2's
separate generation/publication/push admission still requires the flag).

Structured events: `proactivity_v2_admission`, `proactivity_v2_budget_reserved`,
`proactivity_v2_budget_settled`, `proactivity_v2_item_terminal`,
`proactivity_v2_feed_exposed`, `proactivity_v2_push_terminal`,
`proactivity_v2_outcome`, `proactivity_v2_producer_killed`,
`proactivity_v2_budget_invariant_failed`. Dimensions: producer/version, plan,
surface/channel, bounded result/reason, cap/reserved/charged/priced micro-USD,
cost status and policy version. Logs can include opaque item/call/attempt IDs;
metrics labels cannot. No source content, titles, bodies, source IDs, prompts,
credentials or freeform exception text in analytics. Telemetry delivery failure
never refunds spend. Money/outcome truth is Firestore, not analytics arrival.

## Enablement prerequisites

This section is the deployment checklist for the integrated spine, producers and
clients. The PR provisions no cloud resources, changes no live flags and enables
no cohort. Keep v2 off until the coordinator verifies all of these prerequisites.

### Customer-data Firestore indexes and retention

Deploy the generated `firestore.indexes.json` to the customer-data project used
by `get_customer_firestore_client()` on every participating host. Wait for READY;
file presence or a green query fake is not evidence of a deployed index. The
registry `backend/database/firestore_index_registry.py` owns these five indexes:

| Registry name | Scope | Ordered fields (A ascending, D descending) |
| --- | --- | --- |
| `proactivity_feed_state_created` | collection `proactivity_items` | state A, created_at D, __name__ D |
| `proactivity_producer_cohort` | collection group `proactivity_items` | producer A, created_at A, acted_count A, charged_micro_usd A, delivered_count A, negative_count A, unknown_count A, __name__ A |
| `proactivity_followup_source_outcomes` | collection `proactivity_items` | source_id A, producer A, state A, created_at D, __name__ D |
| `proactivity_mentor_delivered_history` | collection `proactivity_items` | producer A, state A, delivered A, delivered_at D, __name__ D |
| `proactivity_mentor_recent_outcomes` | collection `proactivity_items` | producer A, state A, created_at D, __name__ D |

Enable Firestore TTL on `expires_at` for collection groups `proactivity_items`
and `proactivity_budget_days`; both write 90-day retention timestamps. TTL
policies are separate deployed resources, not implied by the index manifest.
Do not add TTL to producer controls/preferences or monetary corruption latches;
keep the existing gateway-attempt retention policy. The 24-hour first-exposure
limit and 30-day delivered-feed window are enforced in code, independently of TTL.

### One-shot commitment queue and authenticated callback

Provision a Cloud Tasks HTTP queue in `SYNC_TASKS_PROJECT` / `SYNC_TASKS_LOCATION`.
Set `COMMITMENT_FOLLOWUP_TASKS_QUEUE` to its queue ID,
`COMMITMENT_FOLLOWUP_TASKS_HANDLER_URL` to the exact deployed HTTPS URL ending in
`/v1/commitment-followup-jobs/run`, and `COMMITMENT_FOLLOWUP_TASKS_INVOKER_SA` to a
dedicated OIDC service-account email. The URL is also the token audience; the
handler checks this exact audience and identity, with no public-auth bypass.
Grant enqueue permission on the queue and act-as on that service account to each
enqueuing runtime. Permit the Cloud Tasks service agent to mint its OIDC token,
and grant the configured invoker access to the target service (Cloud Run Invoker
when hosted on Cloud Run). Verify task headers, identity and retry delivery against
the deployed handler before enabling a cohort. Use bounded dispatch/concurrency
and retry settings; duplicate named tasks and callbacks are idempotent. No cron is
needed: due dates beyond 30 days use deterministic 28-day hops without model work.
Initial enqueue failure preserves the canonical task; stale/closed/deleted task
revisions cannot publish a follow-up. Missing queue bindings keep scheduling off.

### Environment and flags on every host

| Host / role | Required bindings before cohort enablement |
| --- | --- |
| Backend API (including desktop-backend wherever feed/outcome routes are served) | Customer-data Firestore identity; shared Redis `REDIS_DB_HOST` / `REDIS_DB_PORT` / credentials; plain `PROACTIVITY_V2_POSTHOG_TOKEN` and matching `PROACTIVITY_V2_POSTHOG_HOST`; integrated routes and registry. |
| Mentor production on listen/backend and pusher | Same customer-data/Redis/PostHog bindings; `MENTOR_PIPELINE=cohort` for a per-user rollout (true `proactivity_v2` selects v2; false/unknown/error retains legacy), or `v2` only for a host whose mentor users are all enabled; working authenticated `OMI_LLM_GATEWAY_URL`/gateway service bindings. Pusher is a separate image/release: enabling only backend does not switch it. |
| Task create/update/reminder hosts and commitment callback worker | All five queue/project/location bindings above, plus the same PostHog, customer-data and gateway bindings on the worker. Propagate enqueue bindings to every host that invokes reminder scheduling, not just the callback host. |
| LLM gateway | `LLM_GATEWAY_ACCOUNTING_ENABLED=true`; customer-data Firestore, shared Redis and PostHog bindings; **the same `MENTOR_PIPELINE=cohort` (or host-wide `v2`) selection as mentor hosts for admission here too**; existing Luna and System One/Jev provider credentials and the committed routes/rate cards. No direct-provider fallback. |
| Mobile, macOS, Windows | Updated generated clients and consumers, ordinary authenticated backend routing, existing notification preferences/permissions. No local flag or UID bypass grants server admission. Live listen sockets carry identity-only v2 wakeups; all desktop content is fetched through the feed. Offline sockets catch up through foreground/active polling. |

V2 flag lookup uses **only** `PROACTIVITY_V2_POSTHOG_TOKEN`, stripped and
required to start with `phc_`. This is the Omi project's public client token
(project **302298**, already committed in
`desktop/macos/Desktop/Sources/PostHogManager.swift`), bound as a plain value,
with zero new Secret Manager references. `PROACTIVITY_V2_POSTHOG_HOST` defaults
to `https://us.posthog.com`, including when unset or whitespace-only.
The shared `POSTHOG_PROJECT_API_KEY` is intentionally `disabled`: **do not
repoint it**, `POSTHOG_API_KEY`, or generic `POSTHOG_HOST` to enable v2. JIT
rollout flags and backend capture telemetry keep their existing configuration.
Missing, blank, `disabled`, or non-`phc_` dedicated tokens fail closed with
`flag_unavailable`; diagnostics contain no token and are rate-limited to once
per 60 seconds per process. There is no shared-key fallback in dev, local,
test, or production.

Bind the dedicated public token on **pusher, backend-listen, llm-gateway,
backend, backend-sync, backend-sync-backfill, backend-integration, and
desktop-backend** in both serving environments. The gateway budget executor
calls `utils.proactivity.ensure_admitted`, so it needs its own binding even
when the producer already resolved the flag. Desktop-backend serves the
feed/outcome routes and deploys through separate workflows. Local `.env`
users must set the dedicated variable to opt in; offline/emulator setups
leave it unset and fail closed without contacting PostHog.

Create the PostHog **`proactivity_v2`** boolean flag in the same project used by
these server/gateway clients, initially **disabled / zero-percent**. Its registry
entry is a declaration, not creation or enablement. Absent, unknown or failed flag
resolution denies v2 generation and push; do not use a user-ID bypass. Verify all
hosts resolve the same bounded cohort before increasing exposure. Allow up to
300 seconds for cached flag results to reflect an enablement or rollback change,
and 60 seconds before retrying a failed lookup (see rollback notes below).
No creation or flag update is performed by this PR.

The rollout defaults remain off: `proactivity_v2` absent/false,
`MENTOR_PIPELINE=legacy`, and empty commitment queue bindings. Producer registry
rows are enabled behind those gates, not globally active switches. Once v2 is
explicitly enabled, the mentor draft-usefulness judge defaults to **shadow**;
this is an internal measurement mode, not a rollout flag. Its prefilter is disabled,
safety escalation suppresses, follow-ups remain feed-only, and mentor push remains
subject to opt-in, quiet hours, durable ceilings and health. Do not describe every
internal configuration value as false. Follow-up enablement also requires the
coordinator's baseline/quality gates and client card-to-target acceptance. Legacy
mentor push routing remains unchanged; v2 generic pushes retain `/chat/mentor` for
released clients while v2 feed cards target the source conversation.

## 10. Migration, compatibility and rollback

1. Coordinator reviews this contract; only then resume spine implementation.
2. Add flag-gated registry/cap policy, durable budget and item storage, gateway hook,
   routes, generated clients and hermetic fixtures. Provision indexes/TTL through
   existing repository mechanism before enablement; this lane does not deploy.
3. Integrate after #20184 vocabulary settles. Its required one-week baseline and
   mentor pre-PR/benchmark remain coordinator gates, not claims from unit tests.
4. Producer lanes adopt claim/model/publish and remove any v2 unbudgeted path.
   Mentor flip exclusively selects legacy or v2. Integration owner supplies both
   client feed consumers and outcome instrumentation, then deletes agreed old paths.
5. Flag off initially. Enable bounded cohort only with provisional or measured producer rows,
   readiness checks and actual mobile/macOS feed-to-object/action verification.

Rollback: disable the PostHog `proactivity_v2` flag. Unsetting
`PROACTIVITY_V2_POSTHOG_TOKEN` also fails closed once the new environment reaches
fresh processes; the SDK client and flag results are process-cached, so changing
a file or a live process environment alone is not an immediate kill switch.
Never change the shared PostHog secret as part of rollback. Cached enabled results expire within
**300 seconds per process** before new v2 generation/push stops and feed reads
return disabled. Enablement/ramp changes have the same maximum cache latency;
flag failures deny immediately on the next uncached check and retry after
**60 seconds**. Allow this rollback window when checking all serving hosts;
for an urgent mentor-only rollback, explicitly set `MENTOR_PIPELINE=legacy`
on every mentor host (effective once that env change reaches the process).
In-flight calls retain reservations and settle; publication rechecks the cached
flag and suppresses after disable becomes visible.
Feed returns disabled, outcomes for existing items still work. Coordinator may
explicitly flip mentor to legacy. A failed cohort flag lookup selects legacy
before invoking v2; once v2 is invoked, failures never retry through legacy. Preserve
ledger/budgets/attempt IDs until TTL; no historical rewrite or refund-on-rollback.
No old ledger backfill. Released clients continue existing routes while the
integration owner handles retirement using `contracts/client-compat/` policy.
Deleting a route used by a released client needs that lane's compatibility proof.

## 11. Exact planned file ownership

Phase 1 changes **only this file**. Phase 2 spine additions:

- `backend/config/proactivity_v2_producers.json`
- `backend/config/proactivity_v2.py` — registry validation and generated cap access
- `backend/models/proactivity.py` — typed HTTP DTOs
- `backend/database/proactivity.py` — items, transactions, feed/outcomes/preferences/health
- `backend/database/proactivity_budget.py` — durable day authority and Redis leases
- `backend/utils/proactivity.py` — claim, gateway-only model, publish, rollout, dispatch
- `backend/llm_gateway/gateway/proactivity_budget.py` — narrow executor adapter
- `backend/routers/proactivity.py`
- `backend/tests/unit/test_proactivity_v2_budget.py`
- `backend/tests/unit/test_proactivity_v2_ledger.py`
- `backend/tests/unit/test_proactivity_v2_gateway.py`
- `backend/tests/unit/test_proactivity_v2_routes.py`
- `backend/tests/unit/test_proactivity_v2_metrics.py`
- `backend/tests/integration/test_proactivity_v2_budget_emulator.py` — real contention and source purge proof
- `contracts/parity/proactivity_v2.json`
- `app/lib/backend/http/api/notifications.dart` — transport adapter added to existing notification API module, no card
- `app/lib/backend/schema/gen/proactivity_wire.g.dart` — generated
- `app/test/backend/proactivity_contract_test.dart`
- `desktop/macos/Desktop/Tests/ProactivityWireTests.swift`

Phase 2 spine modifications:

- `backend/database/action_items.py`, `backend/database/conversations.py` — canonical deletion clears derived ledger content; source visibility also fences reads/writes

- `backend/llm_gateway/config/cost_rate_cards.yaml` — Jev input pricing

- `backend/config/plan_catalog.json`, `backend/scripts/generate_plan_catalog.py`,
  `backend/config/plan_catalog_generated.py` — validated cap policy/projection
- `backend/llm_gateway/gateway/executor.py`,
  `backend/llm_gateway/routers/openai_compatible.py`,
  `backend/llm_gateway/routers/systemone.py`, `backend/llm_gateway/gateway/providers.py`
  — trusted metadata, reserved provider boundary, same immutable event settlement
- `backend/utils/llm/gateway_client.py` — bounded nonstreaming v2 call, no fallback
- `backend/utils/notification_dispatch.py` — v2 kind through existing transport
- `backend/main.py`, `backend/route_policy_manifest.yaml`,
  `backend/utils/rate_limit_config.py` — authenticated route/rate-limit registration
- `backend/database/firestore_index_registry.py`, `firestore.indexes.json`,
  `backend/tests/support/firestore_query_driver_registry.py` — feed/cohort indexes
  and real-builder query drivers; TTL prerequisites documented here
- `firestore.rules`, `backend/services/users/account_deletion.py` — explicit
  server-only collections/deletion coverage where existing recursive coverage lacks it
- `backend/scripts/export_openapi.py`, `docs/api-reference/app-client-openapi.json`,
  `backend/scripts/generate_dart_models.py`,
  `backend/scripts/generate_swift_openapi_types.py`,
  `desktop/macos/Desktop/Sources/Generated/OmiApi.generated.swift`
- `config/feature-flags.yaml`, `backend/docs/feature-flag-registry.md` — declarations
  (mentor flag entry co-owned with mentor lane; merge rather than duplicate)
- `backend/tests/unit/test_plan_catalog_contract.py` — cap policy generator coverage
- `backend/docs/proactivity_v2/CONTRACT.md` — reviewed clarifications and validation evidence

No `.github/` workflow additions. If live generator output ownership includes
another required derived file, list it in the reviewed contract before building
rather than hand-editing or bypassing its drift guard. Shared gateway/deletion
files must be integrated against the deletion lane's current diff; preserve the
v2 attempt hook when JIT qualification code is removed.

Other lanes own producer source hooks, prompts, model selection experiments,
`MENTOR_PIPELINE` dispatch, client UI, old-path removal and deployment manifests.
Those are not covertly added to this spine patch.

## 12. Verification and review gates

Phase 1: source review, arithmetic check, `git diff --check`, `make preflight`,
normal commit/pre-push hooks and exact remote SHA verification. No product tests
are claimed for a documentation-only change.

Phase 2 hermetic acceptance, using `backend/test.sh` with
`BACKEND_UNIT_TEST_FILE_LIST` for selected suites:

- Concurrent producers/instances cannot reserve past cap; exact-boundary and
  one-micro-dollar denial; aliases/pending prices/unknown plan/free/plan changes.
- Midnight/DST/timezone edits, Redis lease expiry/flush/down, Firestore errors,
  ambiguous commits, crash before/after provider, idempotent/conflicting settle,
  missing usage, priced failures and over-reservation circuit break.
- Production gateway executor calls a fake provider only after real admission;
  retries/fallback/SDK retries cannot escape; framing/output/route price envelopes,
  immutable event equality and per-producer attribution for every attempt.
- Duplicate source event and cross-device delivery/action, late/negative/timeout
  events, disable vs publish race, source/account deletion and sign-out replay.
- Full-cost numerator including silent items, cohort maturity, zero acted,
  >=200 kill latch, unavailable health, push never earned by insufficient samples.
- Firestore strict transaction fake enforces reads-before-writes. Emulator
  contention tests cover true transaction conflicts; no lenient fake-only proof.
- Feed pagination/ties/ownership, null rejection, typed outages, generated Dart
  and Swift parsing against the same parity fixture; no raw JSON client adapters.

Use the existing OpenAPI runner (`backend/scripts/openapi_runner.sh`), generator
freshness and released-client compatibility gates, route policy inventory,
Firestore query/index guard, feature-flag registry and plan catalog checks.
`make preflight` discovers applicable checks; no baseline increases/skip hatches.
Flutter adapter tests use `app/test.sh`; Swift compile includes Tests via
`xcrun swift build --build-tests --package-path desktop/macos/Desktop`, then the
focused wire test suite. Integration owner runs full changed component suites.

For the later cards, the client lane must also satisfy addressability/journey
catalog, localization, UX shared primitives, generated response consumption,
changelog and visual interaction evidence. A backend feed returning 200 does not
prove cards render or navigation succeeds. Relevant invariants: `INV-UI-2`,
`INV-UI-3`, `INV-6` if opening chat, and the task suggestion-only and universal
memory/task authority contracts for follow-ups. PR metadata is generated with
`scripts/pr-preflight --suggest` and validated by the integration owner; spine
opens no PR and performs no merge, production reads, flag change or deployment.

## Review decisions needed before Phase 2

G1 accepted: durable Firestore balance with Redis lease (hard-cap protection
against Redis loss), UTC day, 90-day retention/write count, initial call ceilings,
confirmed-exposure metric semantics, seven-day mature cohort and provisional
producer defaults. Measurement lanes replace provisional estimates/thresholds
with evidence; coordinator owns Focus's legacy exception and assigns
TTL/index deployment. These are concrete design choices for this requested
contract checkpoint, not additional implementation approval stages.

### Implementation boundary clarifications

The v2 metadata is parsed in the existing authenticated chat/systemone routers,
not gateway main. Jev's provider adapter must preserve absent usage as unknown
instead of synthesizing zero tokens. These are necessary additions to the exact
file list for G1 prefilter coverage. Existing Firestore rules already deny all
user subcollections; the existing recursive account wipe includes v2 rows.
No new rules or deletion framework is required. Initial push quiet hours are
22:00–08:00 in the stored user timezone; unknown timezone suppresses push.

Canonical deletion hooks call `purge_source_items` after deleting the source, with transactional source rechecks so a concurrent publication cannot retain derived content. Soft-deleted sources are immediately hidden at every ledger boundary; canonical action-item retirement also purges content. Each affected item adds one privacy-cleanup write. The emulator proof uses `backend/test.sh` with the integration marker and a loopback-only Firebase project.

Server completion of a feed-only follow-up requires an existing confirmed exposure; an independently completed task cannot manufacture exposure or value credit. The first completion is retained without credit; later retries cannot turn that pre-exposure completion into an acted item.

Validation-driven file addition: `backend/scripts/support/find_stripe_entitlement_mismatches.py` defers the Firestore import until its executable entrypoint, so reading catalog-derived constants does not load the cloud SDK inside a fast unit test. The support scanner behavior is unchanged and is not invoked against any account data.

Gate-driven placement adjustment: the Flutter transport lives in the existing reachable notification API module, avoiding a new unreachable module before the producer/UI lanes integrate. Wire shape and API class are unchanged. Existing Firestore registry and canonical deletion modules receive narrow additions; line-count declarations explain reuse instead of introducing parallel registries or an unrelated split.

The existing `backend/tests/unit/test_delete_conversation_cascade.py` fake now recognizes the empty proactive-item cleanup query. Actual matching-item cleanup is tested through the canonical action-item delete API against the emulator.

`app/changelog/unreleased/20261003-proactivity-v2-spine.json` records this internal-only transport change; this build adds no client card or enabled user-facing flow.

The shared OpenAPI generator also owns these required derived TypeScript files:
`desktop/windows/src/renderer/src/lib/omiApi.generated.ts`,
`web/app/src/lib/omiApi.generated.ts`,
`web/admin/lib/services/omi-api/omiApi.generated.ts`, and
`web/personas-open-source/src/lib/omiApi.generated.ts`.
They are regenerated by `backend/scripts/generate_ts_openapi_types.py`; no UI or
transport behavior is introduced in those clients.

The minimal settlement return is `bool`: true permits publication, false retains
an unknown hold or signals over-reservation; identity/store faults raise. No extra
settlement DTO is needed by either producer. Feed/outcome HTTP abuse limits reuse
the existing first-party limiter's fail-open behavior; they cannot create model
work. Budget admission and push reservations remain fail-closed.

Mentor pushes retain `navigate_to=/chat/mentor`, which released clients already
route, along with the v2 item/target identity. The producer owns the actual mentor
chat message; generic lock-screen copy is not materialized as a second chat message.

A confirmed low acted rate at >=200 deliveries latches the kill even when cost usage is incomplete; unknown usage cannot defer that independently provable kill. Unknown cost still cannot produce a passing cost verdict. Missing provider usage retains the whole reservation and denies publication. Changes to provider usage parsing are limited to Jev; other provider surfaces retain their existing behavior.


### Producer integration extensions (2026-10-03)

The producer lane needs up to six mentor attempts per item: optional prefilter,
then gate/draft/critic/usefulness/dedupe. The registry raises only that item ceiling
from three to six (five before the draft-judge follow-up); the 60/day and durable
dollar caps stay unchanged. `usefulness` and `dedupe` are Jev steps on the existing
budgeted systemone route. Quality fail-open never bypasses
typed gateway admission denial or an unsettled hold. Terminal reasons add
`duplicate`, `safety_escalation`, `source_changed`, and `usefulness_judge`.

Draft usefulness defaults to `shadow`, with threshold 0.5 for explicit `enforce`.
The score is written once through `record_usefulness_score(item, score)` under the
item's claim token and account-generation/deletion fence, before terminal publication.
Identical score writes are read-only; changing an existing score conflicts.
The only new measurement field is numeric `usefulness_score`. Outcome reducers
preserve it so mature `acted_24h` and independent `negative` evidence join on the
same item; no extra measurement ledger or public field is introduced.

An optional internal publication `source_guard` checks the follow-up's observed
open status/due revision inside the existing transaction; it never writes tasks.
Producer history/outcomes use three declared serving indexes. The existing
client-local reminder scheduling boundary also enqueues one-shot Cloud Tasks due
wakes; no polling cron is added. Producer details and remaining coordinator decisions are in `PRODUCERS.md`;
the integrated deployment checklist is the Enablement prerequisites section above.

Final review accounting/delivery/recovery contract: v2 settlement requires complete raw
billable input and output counts, non-negative integers, valid cache/reasoning
subsets and consistent totals when reported. Incomplete/invalid receipts keep the
full reservation as unknown and reject publication; legacy accounting stays unchanged.
Mentor replies require a confirmed persisted chat-message/item association or prior
confirmed exposure, never feed availability or FCM acceptance alone. Follow-up
pre-claim infrastructure failures return 503; five-minute abandoned claims may
resume only without a durable attempt, otherwise reconcile failed with money retained
and no provider replay. See PRODUCERS.md for callback recovery and cohort selection.
