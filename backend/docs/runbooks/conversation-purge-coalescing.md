# Conversation deletion owner scans

Owner: batch-custody / lead2. This is David's approved 2026-11-17 deletion-read
containment change, shipping separately from margin-40. No production action is
part of this change.

## Contract and readers

The backend-sync task consumer at
`POST /v1/conversations/deletion-batch-purges/run` calls
`database.batch_pipeline_conversation_purge_scans.run_job`. The reconciler still
reads `conversation_batch_purge_jobs` using `due_at` and dispatches ordinary
`batch_purge` payloads. Tombstone producers still arm that collection atomically
with deletion intent. Accepted-delete cascade jobs are unchanged. There is **no
new collection, task kind, route, index, backfill, TTL or independent dispatcher**.

A worker seals at most 16 fresh obligations belonging to one UID in a transaction.
Only the leader has `owner_scan` (epoch, token, immutable member identities,
generations, arm revisions and cursor). All members use the existing generation,
run_token and finite lease fields. Pending named tasks are invalidated by the
followers' new generations. Enrollment refuses live leases and nonempty legacy
progress. Existing partial runs finish on the legacy path; their cursors and
segment journals never move. Candidate lookup reads at most 16 owner obligations;
a singleton takes the legacy path. Multiple waves/overflow require more groups.

The two namespaces' owner pages, job-result lookups and owner-ID artifact fallback
are shared across members using the existing identity predicates. Discovery
persists each matching member's segment records before advancing the shared
cursor; bounded chunks are replayable. The dependent and parked passes finish
for every member before bindings are erased. Only then are the corresponding
segment records removed, exactly as in a legacy purge. This is why rollback needs
no extra association journal: before binding erasure the canonical per-member
journal is intact; after erasure every dependent was already erased or marked for
pending-write repair. A crash before journal removal replays the binding erase.

Every unit/checkpoint and final completion validates all member tokens,
generations, tombstones and arming revisions. A re-arm invalidates the group;
handback preserves the newly armed obligation. A post-seal arrival is never added
to an advanced cursor. Completion deletes all sealed member obligations in one
transaction only after both namespaces, shadow purges and segment work finish.
Missing tombstones (account wipe), conflicting ownership and unknown outcomes
never grant completion authority. Account gates, holds, short units, task/RPC
budgets, storage generation pins, pending-write repair, unknown-remote settlement,
WAL prefix re-listing, exactly-once capacity release and mirror refresh still use
the existing implementation. WAL originals are re-listed for each member on every
run, including a resumed cursor already past metadata.

## Switch, mixed versions and rollback

`CONVERSATION_BATCH_PURGE_COALESCING_ENABLED` is an `ops_kill`, default **on**.
`false`, `off`, `0` or `no` disable it, including under the global parser mode.
Only the backend-sync consumer reads it; the reconciler's protocol is unchanged.

Setting it off stops enrollment. At the next checkpoint/unit the shared worker
hands back members it still owns: clears delegation/run leases, leaves each
member's original empty legacy progress and its own remaining segment records,
and makes it due. The existing reconciler redrives ordinary per-conversation
execution. A delivery observing an off-state group can perform this handback too.
No member completes merely because handback or an HTTP acknowledgement happened.

An older binary understands every task and obligation. While leased it returns
`in_progress` or `superseded`; after the ordinary 300-second lease expires it
executes a full legacy scan from the untouched member cursor and journal. Its
new token/generation invalidates the group. A surviving new worker releases only
still-delegated members; it never revokes that old worker's lease. If an old leader
finishes and removes the inline group state, followers recover independently
through their finite leases. Thus binary rollback needs no protocol-aware probe
or journal transfer. Prefer switch-off and drain before reverting for efficiency;
an immediate binary rollback also retains erasure reachability. Rollback may
repeat owner scans, which is the intended cost tradeoff.

## Canary (release owner, separate train)

This PR does not deploy. Release/lead2 first deploy the reviewed image with the
switch off, then enable on one backend-sync canary revision for one full deletion
lookback window. Expand to all task-consumer revisions only after audits pass.
Existing older revisions can serve tasks safely, but reduce sharing while present.

Compare timestamped, aggregate deletion purge reads **per armed conversation**
for the same route, including owner pages, job-result gets, owner-ID fallback,
member-journal and coordination reads. Track actual group sizes using
`event=conversation_batch_purge_owner_scan_completed members=...`, completion age,
purge failures/retries, held outcomes and foreground account-gate latency. Do not
book unit-test page reductions as billed-read savings. Fresh-only eligibility,
singletons, separate waves, lease-expiry fallback and coordination overhead can
reduce the benefit. The supplied baseline is a planning input, not a new measure.

Stop and set the switch off if **any completed member has authorized rows/objects
remaining in an audit**, purge failures rise, unrelated erasures appear, or
completion age/gate latency regress. Audit both namespaces, nested/alias and
segment-only identities, corrupt-owner artifacts and exact WAL prefixes (all
object generations). Unknown storage answers remain failures, never audit proof.
Release/lead2 owns expansion or rollback on that train; margin-40 has no dependency
on this PR. No production reads or writes were needed to implement/test it.

## Scope-panel disposition

The initial scope panel's erasure, races, leases, holds, quota, shadow, mirror,
read-growth, bounds and rollback concerns are covered by the shared traversal,
existing erasure helpers and synthetic unit/emulator tests. Replacement-boundary
approval is supplied by David's explicit task approval; this adds no batch writer
schema or replacement coordination service. New collection/read-budget, TTL,
new task protocol/readiness and historical backfill proposals are unnecessary
because all state stays on existing obligations/journals. Live sharing factor,
read attribution, revision mix and savings remain canary questions; production
inspection is outside this task's authorized scope.
