# Demand-driven processing (plan v3, step 1)

All controls are default off in the composed runtime manifest and checked-in GKE
values. `DEMAND_PROCESSING_ENABLED` also requires an explicit UID allowlist or a
nonzero deterministic `DEMAND_PROCESSING_PERCENT`. Lazy work and the agent tool
have independent switches. The day-merge switch enables aggregate shadow logs
only. No configuration is applied by this change.

Explicit `client_state` intent is held in Redis: a 90-second lease per surface,
unioned across devices, and `last_surface_open_at` retained for seven days. Phone
foreground and Mac main-window visibility are reported every 30 seconds and on
state changes, including when there is no recording socket. The client reporters
require `DEMAND_PROCESSING_SURFACE_REPORTING_ENABLED=true` (Dart define on mobile,
process environment on Mac); server flags alone do not activate client reporting.
Mac activation and ordinary authenticated/background requests are not open intent.

The existing `conversation-finalization`, fresh sync and backfill Cloud Tasks
queues retain their OIDC workers and durable job/token fences. Redis indexes only
opaque obligations and scheduling metadata. Dispatch occurs immediately for open
surfaces, after four minutes for a recent surface, and after 59 minutes for dormant
surfaces. The final minute is processing headroom, not a demonstrated completion
SLO. Ready work drains tiers 0, 1, 2; 59-minute debt escapes starvation. Priority
waits create scheduled wakeups without consuming processing attempts. Already
running work is not preempted. Queue-age gauges use scrape-time Redis reads and
return NaN when the dependency is unavailable. Redis loss uses eager recovery;
Firestore jobs and outbox reconciliation retain the obligation.

Visible notes and speaker resolution use the existing pipeline. Invisible memory,
summary vectors and task persistence use the existing sync reprocess outbox, in a
separate effects slot for the same conversation. Visible completion blind-writes
that slot without a new Firestore read. Closed-surface settlement waits to the 59-minute deadline from
the indexed obligation; open intent, Process Now and the tool wake it immediately.
The worker reloads the current settled row and uses the existing canonical memory,
task-suggestion and vector writers. An effective-input checkpoint suppresses a
completed replay without regenerating notes. Provider failures remain retryable.
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
Redis indexes are not a historical discovery database. Existing durable recovery
continues to own unindexed or pre-rollout debt; no Firestore discovery scan was
added to surface or tool requests.

The daily-summary hook is a flag-controlled stub: it logs aggregate link-only and
candidate counts without reading extra documents or mutating conversations. Unknown
engagement is protected. A future executor must consume #21836's authoritative
call link and recheck opened/edited/shared/acted receipts transactionally before
any rewrite. This PR does not qualify cross-device or ambiguous merging.

## Config trains and acceptance

1. Deploy the default-off image and verify runtime manifest/flag parity. Preserve
   existing queue identity, audience, reconcile and BYOK behavior. Test the lazy
   outbox in a Firestore-emulator environment (its existing runtime ownership
   rule permits production or emulator, not shared remote dev persistence).
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
4. Admit 1%, then 5% for at least three hours including busy load. Qualify visible
   tier 0 <=1 minute, tier 1 p95 <=5 minutes, tier 2 <=60 minutes; newest 20 minutes
   visible <=2 minutes and newest hour <=4 minutes on simultaneous opens. Include
   a warm-capacity and backlog receipt. Stop on quality, live p95, ceiling or
   catch-up regression. Only then consider 25%, 50%, 100% in separate trains.
5. Enable the day-merge shadow hook separately. It has no rewrite executor.

Rollback sets the percent to zero and clears the allowlist, then disables client
reporting and lazy/tool admission. Keep the master scheduler switch on while the
indexed and durable queues drain, so priority cleanup and metrics remain active;
only then turn it off. Retain queue workers and existing durable sweeps. No historical
content repair, GPU/HPA change, production enablement or cost saving is claimed.

Firestore optimization remains separately owned. Relevant multiplier pointers are
`utils/sync/pipeline.py`, `utils/sync/reprocess.py`, and the existing finalization
reconciler; this change adds no surface-open Firestore lookup or discovery query.
