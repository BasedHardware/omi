# Demand-driven processing (plan v3, step 1)

All controls are default off in the composed runtime manifest and checked-in GKE
values. `DEMAND_PROCESSING_ENABLED` also requires an explicit UID allowlist or a
nonzero deterministic `DEMAND_PROCESSING_PERCENT`. Lazy work and the agent tool
have independent switches. No configuration is applied by this change.

Explicit `client_state` intent is held in Redis: a 90-second lease per surface,
unioned across devices, and `last_surface_open_at` retained for seven days. Phone
foreground and Mac main-window visibility are reported on state changes, with 30-second renewals while
open, including when there is no recording socket. The client reporters
require `DEMAND_PROCESSING_SURFACE_REPORTING_ENABLED=true` (Dart define on mobile,
process environment on Mac); server flags alone do not activate client reporting.
Only an explicit boolean `surface_open` is intent. Released listen frames that
contain only `foreground` and `transcript_visible` remain telemetry, even with all
server flags on. Mac activation and ordinary authenticated/background requests
are not open intent. Both reporters retain state changes during an in-flight
request and drain the latest state immediately afterward; Mac rechecks visibility
after URL/header preparation. Failed closes remain owed for the next 30-second
heartbeat, including while closed, instead of waiting for the 90-second lease.

The existing `conversation-finalization`, fresh sync and backfill Cloud Tasks
queues retain their OIDC workers and durable job/token fences. Redis indexes only
opaque obligations and scheduling metadata. Finalization is dispatched immediately
for every tier. Sync append reprocessing retains its existing trailing-edge
`SYNC_REPROCESS_SETTLE_SECONDS` (600 seconds in production), including tier 0,
open/tool priority promotion, Redis failure and durable worker claims. Each append
extends the same outbox obligation instead of causing another processing pass;
continuous appends retain the 59-minute ceiling. This content-settlement boundary
is separate from priority admission. Keep warm capacity: tiers
order ready work only under contention and never impose an idle-capacity timer.
Future lazy enrichment does not block ready visible work. Ready work drains tiers
0, 1, 2; 59-minute debt escapes starvation with one minute of processing headroom,
not a demonstrated completion SLO. Priority
waits create scheduled wakeups without consuming processing attempts. A wait
behind ready higher-tier work re-checks every `BLOCKED_WAIT_SECONDS` (30), one
named Cloud Task per wait, clamped to its ceiling escape (at most 5 seconds past
it, inside the one-minute headroom). Already
running work is not preempted. Queue-age gauges use scrape-time Redis reads and
return NaN when the dependency is unavailable. Redis loss uses eager recovery
for finalization/effects and retains sync's ordinary settle deadline;
Firestore jobs and outbox reconciliation retain the obligation.

Visible notes and speaker resolution use the existing pipeline. Invisible memory,
summary vectors and task persistence use the existing sync reprocess outbox, in a
separate effects slot for the same conversation. Visible completion blind-writes
that slot without a new Firestore read. Closed-surface settlement waits to the 59-minute deadline from
the indexed obligation; open intent, Process Now and the tool wake it immediately.
The worker reloads the current settled row and uses the existing canonical memory,
task-suggestion and vector writers. An effective-input checkpoint suppresses a
completed replay without regenerating notes. Provider failures remain retryable. Request-scoped BYOK work stays eager in
the live authenticated context; credentials never enter the outbox and a
deferred task never substitutes platform keys for those requests.
Daytime merge decisions are unchanged; survivor vectors join lazy work. Its
existing maximum gap is 60 minutes, so the completion ceiling takes precedence
at the boundary: a legitimate later merge creates a new effective revision.
This boundary needs qualification; no claim of one invocation for unknown future
audio is made.

`process_recent_conversations` is shared by app chat, Telegram/Linq's shared chat
core and hosted MCP. Its owner comes from authenticated/injected execution context,
never a tool argument. It promotes at most 20 indexed obligations from the last six
hours, once per 30 seconds per owner. Its response reports progress with
`ready=false`; no indexed debt is not proof that all historical work is complete.
A surface's closed-to-open edge wakes at most `OPEN_PROMOTE_LIMIT` (20) of the
newest indexed obligations from the last 48 hours; older debt keeps its tier and
its ceiling.
Redis indexes are not a historical discovery database. Existing durable recovery
continues to own unindexed or pre-rollout debt; no Firestore discovery scan was
added to surface or tool requests.
Desktop workers use their existing explicit production/development release
channel when `OMI_ENV_STAGE` is absent, preserving separate Redis namespaces.

The end-of-day merge hook is omitted under David's updated 2026-10-16 rulings.
Daytime conservative smart merge stays unchanged. Lazy pyannote refinement is
approved for a later qualified lane; this PR retains the existing speaker path
and does not add GPU capacity or a speaker-refinement executor.

## Config trains and acceptance

1. Deploy the default-off image and verify runtime manifest/flag parity. Preserve
   existing queue identity, audience, reconcile and BYOK behavior. Test the lazy
   outbox in a Firestore-emulator environment (its existing runtime ownership
   rule permits production or emulator, not shared remote dev persistence).
   Desktop backend config trains update the composed manifest and both inline
   deploy-workflow declarations together; runtime contract tests enforce parity.
2. Enable client reporting for the owner; enable the scheduler with an owner-only
   allowlist and zero percent. Check lease expiry, independent-device close,
   socket-free opening, pending promotion and unchanged audio retention. Watch
   `omi_demand_processing_total{outcome}` and
   `omi_demand_processing_queue_age_seconds{tier}` alongside existing finalization
   journey latency, durable oldest age, retries and dead letters.
3. Enable lazy enrichment, then the tool, as separate owner trains. Verify notes,
   speaker labels, canonical memory, task suggestions and vector retrieval against
   synthetic/evaluator fixtures; exercise concurrent append/merge, Process Now,
   duplicate deliveries, Redis outage and worker restart. Compare memory/notes
   calls per effective settled revision and outbox repair/unbound counters.
4. Admit 1%, then 5%, with at least 30 minutes of clean sentinel readouts on the
   watch metrics at each step (David's 2026-10-16 ruling 11). Qualify visible
   tier 0 <=1 minute, tier 1 p95 <=5 minutes, tier 2 <=60 minutes; newest 20 minutes
   visible <=2 minutes and newest hour <=4 minutes on simultaneous opens. Include
   a warm-capacity and backlog receipt. Stop on quality, live p95, ceiling or
   catch-up regression. Only then consider 25%, 50%, 100% in separate trains.

Rollback sets the percent to zero and clears the allowlist, then disables client
reporting and lazy/tool admission. Keep the master scheduler switch on while the
indexed and durable queues drain, so priority cleanup and metrics remain active;
only then turn it off. Retain queue workers and existing durable sweeps. No historical
content repair, GPU/HPA change, production enablement or cost saving is claimed.

Firestore optimization remains separately owned. Relevant multiplier pointers are
`utils/sync/pipeline.py`, `utils/sync/reprocess.py`, and the existing finalization
reconciler; this change adds no surface-open Firestore lookup or discovery query.
