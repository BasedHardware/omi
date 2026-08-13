# PostgreSQL Listen formation outbox contract

Status: implemented as an inert, bounded worker seam. It does not register a
poller, issue a credential, choose a rollout cohort, or change a route/default.

## Purpose

An atomically finalized Listen capture writes one immutable pending outbox row.
This unit delivers that row to the already-idempotent formation acceptance
boundary without losing work across worker crashes or silently changing the
formation inputs.

## Durable state

The source `listen_formation_outbox` row remains immutable. Delivery state is
recorded as append-only revisions plus a fenced current head:

- `leased` identifies one worker, attempt, expiry, and lease fence;
- `retryable_failed` records a closed failure code and next eligible time;
- `dead_letter` records the bounded terminal failure selected by injected
  `max_attempts` policy;
- `accepted` stores the exact durable formation acceptance digest.

The policy values for lease duration, retry delay, and maximum attempts are
required at adapter construction. This unit supplies no production defaults.
All delivery tables are in the `staged_results` deletion surface.

## Authority and isolation

Every operation requires a sealed `memories.work.accept` context and runs on one
checked-out SERIALIZABLE PostgreSQL connection after transaction-time authority
revalidation. The application role has no direct table privileges; it can call
only the fixed security-definer functions. Those functions independently bind
the account, principal, and capability from transaction-local settings.

Selection is owner-local and uses `SKIP LOCKED`. A lease claim, payload read,
failure transition, or acceptance acknowledgement fails closed when its head,
fence, worker, immutable outbox coordinates, or expiry has changed.

## Exact input and replay

The PostgreSQL adapter reconstructs the sealed finalization from the immutable
session and segment rows and verifies session, segment, transcript,
finalization, payload, and outbox digests before returning any text.

The service consumer requires an injected durable
`load_ingestion_request(context, payload)` operation. It must return the entire
versioned `ListenFormationIngestionRequest`, including graph snapshot,
language/timezone, reference clock, policy and generation coordinates,
strategy assignment, execution policy, and accepted event time. The consumer
does not infer or default any of these values.

Formation acceptance is the correctness-level idempotency boundary. A crash
after acceptance but before delivery acknowledgement may cause another worker
to call acceptance again after the lease expires; the stable formation work
coordinate returns replay without another model call. The accepted delivery
transition additionally verifies in PostgreSQL that the supplied acceptance
digest belongs to the exact outbox formation work.

## Bounded worker behavior

`runNext` performs at most one claim and one formation acceptance call. It
starts no timer. Dependency, payload, serialization, ineligibility, and
acceptance-conflict failures are reduced to closed codes before persistence;
transcript text and provider errors are never written into delivery state.

## Qualification evidence

- focused consumer, ingestion, adapter, manifest, and schema tests cover exact
  call order, hostile inputs, replay/conflict, retry recording, authority, and
  cleanup registration;
- the real PostgreSQL 18.4 gate applies/reapplies migration 0031 and exercises
  claim, sealed payload reconstruction, retry persistence, privilege denial,
  authority revocation, and atomic rollback;
- the same migration corpus remains qualified under pinned Bun and Node
  runtimes.

## Explicit nonclaims

This unit does not:

- activate the Listen route or switch it from its current store;
- mint or distribute a `memories.work.accept` worker credential;
- select production lease/retry/dead-letter values or retention policy;
- run a daemon, scheduler, deployment, or cohort rollout;
- choose missing language, timezone, graph, strategy, or policy coordinates;
- alter identity authority, subject admission, bystander policy, or compose
  voice.

Those remain composition, operations, and David-gated rollout decisions.
