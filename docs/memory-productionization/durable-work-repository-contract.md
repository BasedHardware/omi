# Durable work repository control contract

Status: P3 service-boundary pre-registration, 2026-08-11

## Purpose

This contract freezes the production-neutral repository boundary that persists
accepted memory work before model execution and controls fenced worker attempts.
It adds no PostgreSQL client, SQL operation, role grant, worker composition,
model call, clock, retry schedule, or runtime default.

The first control port deliberately has **no success method**. A worker cannot
mark work successful until success, the exact authoritative graph transition,
the total formation outcome where applicable, and the terminal outbox row can
be committed atomically. The current ledger origin vocabulary does not yet name
promotion, identity-cluster, and predicate-batch commits honestly; silently
calling those repairs or historical replay would corrupt provenance. Atomic
success coupling is the next separately pre-registered slice.

## Acceptance

Acceptance requires an already-issued context with exact capability
`memories.work.accept`. The request contains:

- one strict `AcceptedDurableMemoryWork` whose owner and account epoch equal the
  context;
- a non-empty, bounded, deterministic input manifest of closed typed references
  and content digests;
- exactly one graph-frontier witness matching the accepted input frontier; and
- an acceptance request digest over the normalized pending job plus manifest.

The accepted work's `input_digest` is the digest of that complete normalized
manifest. Same owner/job/digest is replay; same owner/job with different bytes
is conflict. Acceptance never stores raw evidence, transcript, prompt, model
output, provider error, query, or answer.

The eventual adapter obtains the current control revision and database clock
inside its transaction; neither is caller-selected. It revalidates lifecycle,
epoch, destination, credential, grant, and capability before replay observation
or mutation, and writes acceptance, manifest, and pending state atomically.

## Worker control

Execution control requires an already-issued context with exact capability
`memories.work.execute`. The public worker surface contains only:

- lease the next eligible job from a sorted closed work-kind set;
- load one job for restart/reconciliation;
- record a closed failure under the exact current lease fence; and
- recover one expired lease as typed `worker_lost` work.

The context principal is the worker identity. Requests never select another
worker, an event time, lease duration, retry delay, attempt budget, account,
provider, or raw SQL. The future adapter obtains DB time and the versioned lease
and retry policy from the persisted execution contract, locks the job head,
applies the pure state transition, appends one state revision, and compare-and-
swaps the head in one transaction.

Returned jobs are re-parsed, owner/epoch checked, frozen, and state checked by
the facade. A leased result must name the context principal. Failure/recovery
can return only retryable or dead work. Stale fences and ineligible states are
closed results, not exceptions carrying database/provider text.

## Explicit exclusions

- No success/finalize operation; no graph or outbox commit can be skipped.
- No model, prompt, policy, lease, or retry configuration is selected here.
- No application route, worker loop, scheduler, PostgreSQL function, grant,
  connection, query, or execute capability is added.
- No accepted input can be inferred from SQLite dream tables or a request-
  lifecycle deferred collection.
- No `subject:*`, identity, bystander/privacy, or compose-voice behavior changes.

## Pre-registered acceptance tests

1. Forged context, wrong capability, owner/epoch substitution, malformed work,
   manifest omission/duplication, missing/duplicate frontier witness,
   digest mismatch, and hostile plain-data containers fail before an adapter.
2. Equivalent manifest order normalizes to one acceptance identity; any input
   ref, kind, digest, frontier, contract, owner, or epoch change changes it.
3. Acceptance output must be the exact pending job or a closed replay/conflict/
   authority result.
4. Lease requests contain only a sorted unique closed work-kind set; leased
   output must be owner-local, current-epoch, leased, and owned by the context
   principal.
5. Failure requires a positive fence and closed error code; returned work can
   only be retryable or dead. Recovery can only return `worker_lost` retry/dead.
6. Forged, foreign-owner, stale-epoch, wrong-worker, success-state, or raw-field
   adapter output fails closed at the facade.
7. The public ports expose no success, finalize, query, execute, connection,
   clock, lease-duration, or retry-delay operation.
8. Focused/full tests, contract QA, import lint, strict changed-file TypeScript
   filter, and `git diff --check` pass before this unit is recorded.
