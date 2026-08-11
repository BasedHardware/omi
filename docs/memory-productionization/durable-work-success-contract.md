# Atomic durable-work success contract

Status: P3 pre-registration, 2026-08-11

## Purpose

This contract closes the gap deliberately left by the pre-success durable-work
control port. A worker may declare success only when the terminal work revision,
the exact authoritative graph append (for non-empty work), the total formation
outcome (for formation), one structural success-link row, and the terminal
outbox event commit atomically.

It adds no worker, model, PostgreSQL client, pool, role grant, scheduler, route,
clock, or runtime default.

## Honest origin vocabulary

The existing frozen ledger migration names formation plus three operational
non-formation reasons: repair, manual liveness, and historical replay. Those
names cannot honestly describe measured durable jobs. A new checksummed
migration expands the closed vocabulary with:

- `promotion` for accepted provisional-to-canonical work;
- `identity_consolidation` for one adjudicated identity cluster; and
- `predicate_alignment` for one bounded predicate batch.

No existing migration byte changes. Formation remains `origin_kind=formation`
with its exact formation work id and total outcome. The three new values remain
`origin_kind=non_formation`. Relabeling any of them as repair or historical
replay is forbidden.

## Success request

The sealed success repository requires a current issued
`memories.work.execute` context and a strict leased job owned by the context
principal. A request binds:

- the complete leased job state and fence;
- one exact immutable staged normalized result for the accepted work;
- `successful` or `successful_empty`;
- exact response and result digests;
- either one complete validated `AuthoritativeLedgerAppend` or null; and
- a request digest over the job-state digest and all result coordinates.

`successful` requires a graph append whose request digest equals the work result
digest. Its origin must match the job kind exactly. Formation additionally
requires outcome owner, work id, input frontier, and response digest to equal
the accepted job. A non-empty append must declare graph derivation success.

`successful_empty` requires no graph append. It still records exact response and
result digests, a terminal work state, a success-link row, and an outbox event;
its result digest equals the staged normalized-result digest. It never becomes
absence, abstention, or deletion.

No public request selects DB time. The future adapter locks current authority,
work head, lease, graph head, and idempotency receipt, then derives the terminal
state with the transaction clock.

## Structural PostgreSQL linkage

The new inert migration:

1. expands the non-formation reason check without editing old bytes;
2. adds a generated, closed `origin_code` to graph commits and an owner-scoped
   unique origin coordinate;
3. adds exact success coordinates to work-state uniqueness;
4. adds `memory_work_success_results`, which binds one terminal succeeded job to
   its work kind, result kind/digest, and either the exact graph commit/origin or
   an explicit empty result; and
5. makes every successful outbox row reference that exact success-result row.

The success-result check maps work kind to origin code. A formation job cannot
point at promotion, and a predicate job cannot point at repair. A non-empty
success cannot omit a graph commit; an empty success cannot smuggle one in.
The follow-on result-staging migration additionally makes every success point to
the exact owner-local staged normalized result and response digest. Every key
and foreign key is account-scoped. The migrations grant nobody.

## Replay and failure

Same job, fence, result digests, append digest, and request digest replay the
same terminal job/commit/outbox. Any changed immutable coordinate is a hard
idempotency conflict. Stale lease, stale graph parent, stale context,
authorization denial, and serialization failure remain distinct closed
outcomes. A failure writes nothing partially and never downgrades to retry,
dead, abstained, or empty.

Returned committed/replayed results are re-parsed and must contain the exact
terminal job, expected graph commit (or none), positive sequence, and one opaque
outbox id deterministically derived from the accepted work, attempt, fence, and
result digests. The success event time must fall inside the lease that authorized
the commit. Raw SQL/provider errors and content never enter the outcome.

## Pre-registered acceptance tests

1. Wrong capability, owner/epoch, non-leased/wrong-worker job, malformed fence,
   unknown result kind, bad digest, or hostile container fails before adapter.
2. `successful_empty` rejects any graph append; `successful` requires one and
   binds its request digest to the result digest.
3. Each work kind accepts only its exact origin. Formation also binds work id,
   frontier, owner, response digest, and total outcome.
4. Request identity changes with job state/fence, response/result digest,
   append digest, origin, or result kind.
5. Adapter output cannot substitute job, owner, epoch, fence, result, commit,
   sequence, outbox, or raw fields.
6. Migration bytes remain append-only and checksummed; static tests prove the
   origin expansion, work-kind mapping, terminal-state/graph/result FKs, success
   outbox linkage, account scoping, and absence of grants.
7. Public success surface exposes one named commit operation and no SQL,
   connection, clock, lease, retry, or model operation.
8. Focused/full tests, contract QA, import lint, strict changed-file TypeScript
   filter, and `git diff --check` pass before recording the unit.

## Explicit exclusions

- No real PostgreSQL semantics are claimed before the supported runtime gate.
- No worker loop, result staging store, outbox delivery/ack, or service
  composition is activated.
- No provider/prompt selection, policy change, subject admission, bystander
  change, identity-authority change, or compose-voice change.
