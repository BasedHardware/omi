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
Mentor additionally requires its existing opt-in and `MENTOR_PIPELINE=v2`.
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
| `conversation_mentor_v2` | Newly eligible conversation segment revision after existing deterministic debounce; existing mentor opt-in; no polling timer | conversation ID + eligible revision + producer version | 60 provider calls/user/UTC day, at most 3/item; text request <=32,768 bytes, output <=2,048 tokens/call | Provisional estimate 60000 micro-USD; 10% acted, 250000 micro-USD/acted; kill below configured acted rate OR above configured cost/acted after >=200 mature deliveries. |
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
               event: AccountingEvent) -> Settlement: ...
    def release_unsent(self, *, reservation: Reservation) -> Settlement: ...
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
route fallback or direct SDK path. Output bounds include reasoning tokens. Bound
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
item = claim_item(uid=uid, producer=name, source=source_event)
result = await run_proactivity_model(item=item, step="phrase", request=request)
# This function is gateway-only and propagates typed denied/unknown results.
await publish_item(item=item, content=content, target=target)
```

`claim_item` checks registry/flag/opt-in, source ownership and deterministic source
identity; `publish_item` rechecks them and refuses pending/unknown cost, deleted
sources, expired items or an already-terminal claim. A silent model result closes
the same item with cost, without a card. Mentor step names are `gate`, `generate`,
`critic` and `prefilter`; commitment uses `phrase`. Jev prefilter uses
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
`timeout` is accepted as a no-write/no-value observation and never dismissal,
negative feedback or engagement. Explicit `dismissed` hides a card but is not a
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
| `MENTOR_PIPELINE` | Server env `legacy|v2`, default legacy; invalid denies mentor invocation. Mentor owner implements exclusive dispatch; v2 failure never falls back to legacy automatically. |
| Producer registration / health | Provisional targets permit enablement; durable kill overrides registry enabled. |
| User producer preference | Explicit false wins every admission/publication/push check. |
| `LLM_GATEWAY_ACCOUNTING_ENABLED` | Must be true for v2; existing sink semantics unchanged for other traffic. |

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

## 10. Migration, compatibility and rollback

1. Coordinator reviews this contract; only then resume spine implementation.
2. Add disabled registry/cap policy, durable budget and item storage, gateway hook,
   routes, generated clients and hermetic fixtures. Provision indexes/TTL through
   existing repository mechanism before enablement; this lane does not deploy.
3. Integrate after #20184 vocabulary settles. Its required one-week baseline and
   mentor pre-PR/benchmark remain coordinator gates, not claims from unit tests.
4. Producer lanes adopt claim/model/publish and remove any v2 unbudgeted path.
   Mentor flip exclusively selects legacy or v2. Integration owner supplies both
   client feed consumers and outcome instrumentation, then deletes agreed old paths.
5. Flag off initially. Enable bounded cohort only with provisional or measured producer rows,
   readiness checks and actual mobile/macOS feed-to-object/action verification.

Rollback: set `proactivity_v2=false`; all new v2 generation/push stops, in-flight
calls retain reservations and settle, publication rechecks flag and suppresses.
Feed returns disabled, outcomes for existing items still work. Coordinator may
explicitly flip mentor to legacy; never an automatic failure fallback. Preserve
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
- `contracts/parity/proactivity_v2.json`
- `app/lib/backend/http/proactivity.dart` — transport adapter only, no card
- `app/lib/backend/schema/gen/proactivity_wire.g.dart` — generated
- `app/test/backend/proactivity_contract_test.dart`
- `desktop/macos/Desktop/Tests/ProactivityWireTests.swift`

Phase 2 spine modifications:

- `backend/llm_gateway/config/cost_rate_cards.yaml` — Jev input pricing

- `backend/config/plan_catalog.json`, `backend/scripts/generate_plan_catalog.py`,
  `backend/config/plan_catalog_generated.py` — validated cap policy/projection
- `backend/llm_gateway/gateway/executor.py`,
  `backend/llm_gateway/gateway/request_context.py`, `backend/llm_gateway/main.py`
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
