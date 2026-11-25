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
new task kind, route, index, backfill, TTL or independent dispatcher**.

The read-only `scripts/complete_half_deleted_conversations.py` diagnostic excludes
underscore-prefixed metadata IDs from pending-obligation totals, including any
readiness marker left by an earlier release.

A worker seals at most 16 fresh obligations belonging to one UID in a transaction.
Only the leader has `owner_scan` (epoch, token, immutable member identities,
generations, arm revisions and cursor). All members use the existing generation,
run_token and finite lease fields. Pending named tasks are invalidated by the
followers' new generations. Enrollment refuses live leases and nonempty legacy
progress. Existing partial runs finish on the legacy path. Legacy `progress_arm` binds
the cursor to its `armed_at`/`arm_revision` at claim. Each checkpoint, unit and
completion transaction verifies that arm; a re-arm preserves the obligation and
segment journals, clears the stale cursor and makes the next generation due.
A cursor without an arm stamp is conservatively rewound once at legacy claim;
a matching stamped cursor resumes intact. This also fixes the pre-existing
legacy re-arm completion gap on main, including switch-off fallback. Candidate lookup reads at most 16 owner obligations;
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

Active group renewals move `due_at` with `lease_until`: this preserves the
first time a member could actually be claimed while preventing a large active
group from filling the reconciler's bounded due page. A paused leader retains its
proof token but clears its active lease generation; that progress object cannot
write again. A legacy takeover changes the token and invalidates the saved scan,
even if the legacy worker subsequently releases its lease. Handback emits the
shared `record_fallback` event once per committed transition.

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

Release must enforce the rollback floor for every purge consumer. The workspace
tooling must read the authoritative `backend/deploy/release_floor.json` from
`BasedHardware/omi` main through the GitHub contents API and refuse admission
when the policy cannot be loaded or validated.
Use the floor-guarded workspace tooling for deploy and rollback admission. For
other manual traffic moves, verify the target against the product floor first.
The direct backend workflow checks the floor from product main for the requested
release, traffic repair, integration-only canary rollback, and failed-promotion
traffic restoration. Supply a floor-qualified retained revision when dispatching
an integration-only canary.
Keep renewing the readiness marker daily while marker-gated #25608 binaries
still serve, until every purge consumer runs the marker-free release.
Verify traffic, tagged revisions and queued revision-specific task targets before
rolling out the marker-free worker. Pre-floor binaries lack the arm-revision
completion fence and must stay out of service.

For emergency rollback, roll out the kill switch set to off to every revision
that receives purge tasks. Include tagged revisions and queued revision-specific
targets. Running revisions keep their environment until they are replaced or
drain. An off-state delivery can hand back a group still owned by its epoch and
token. Allow finite leases to expire and redrive any remaining obligations, then
verify handback and journal preservation. Handback preserves an old
takeover's nonempty cursor and each member journal without revoking a replacement
worker's lease. If a leader is gone, followers recover through finite leases.
A product revert restores the readiness gate. Release must write a fresh
readiness marker after re-verifying the consumer revision set to resume coalescing.

## Canary and owner

**Release is the canary executor and owns expansion or rollback.** Lead2 owns the
batch-custody contract and pre-merge review; margin-40 has no dependency on this
train. This PR does not deploy or inspect production.

After verifying all consumer targets against the release floor, enable one backend-sync canary
revision for a full deletion lookback window. Measure **deletion purge reads per
armed conversation**, origin
`http:/v1/conversations/deletion-batch-purges/run`, including coordination,
member-journal, owner-page, job-result and owner-ID fallback reads. Use timestamped
aggregate evidence and the 24 hours before canary as the comparison baseline.
Track group sizes, completion age and gate latency; local page-count reductions
are not billed-read savings.

Stop and switch off if **any** of these occurs:

- An audit finds any completed member with rows remaining (also audit artifacts,
  exact WAL prefixes/all generations and both namespaces).
- Purge failure rate **or dead-letter rate rises 20% or more** versus the 24 hours
  before canary. A zero baseline with any new failure/dead letter also stops.
- Reads per armed conversation are not falling versus that baseline after the
  full lookback window.

Expand only after a clean full window and completed-member audits. Fresh-only
eligibility, singletons, separate waves, rollback scans and coordination overhead
can reduce the gain. Unknown storage outcomes remain failures, never audit proof.
No production savings are claimed by this implementation.

## Scope-panel disposition

The initial scope panel's erasure, races, leases, holds, quota, shadow, mirror,
read-growth, bounds and rollback concerns are covered by the shared traversal,
existing erasure helpers and synthetic unit/emulator tests. Replacement-boundary
approval is supplied by David's explicit task approval; this adds no batch writer
schema or replacement coordination service. Paged scan collections, TTL, new task
protocols and historical backfills remain unnecessary: work stays on existing
obligations/journals. Live sharing factor, read attribution, revision mix and
savings remain canary questions.

## Remainder audit

Run `scripts/audit_conversation_purge_remainders.py` from the backend with
read-only ADC and explicit `--project`, `--start` and `--end`. The script
compares the half-open deletion-intent window with the immediately preceding
window of equal length. It checks current state. A tombstone's `deleted_at`
survives retries, and absence of an obligation gives no completion timestamp
or execution-path attribution. Firestore needs a collection-group index on
`deleted_conversations.deleted_at`. An unavailable index prevents enumeration.
Missing coverage is reported separately from observed remainder counts.
Content-free result ordering edges are an intended part of the purge contract.
Associations discarded with successful bindings and the Postgres mirror
require independent evidence.

The worker emits `conversation_batch_purge_owner_scan_audit` at WARNING
after a committed seal, completion, or handback. Join group events on
`epoch_hash` and sum `members` for groups with a completed outcome. Handback
counts describe the sealed group, including any members already taken over.
These records give group and member totals. They carry no member identities.
A process exit after the transaction commits and before logging, or a legacy
takeover after lease expiry, can leave a seal without a terminal event.
