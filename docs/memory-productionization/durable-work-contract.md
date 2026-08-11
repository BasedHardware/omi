# Durable memory work contract

Status: P3 pre-registration, 2026-08-11

## Boundary

P3 makes already-accepted memory work survive process loss. It does not activate a
model, choose a provider, alter subject/privacy policy, or substitute for the real
PostgreSQL gate. The production-neutral core owns only the state vocabulary and pure
transition rules; PostgreSQL will own leases, fences, atomic result/outbox persistence,
and replay.

The measured failure to prevent is explicit: a model error must never be serialized as
an abstention, and an unanswered item must never be reported in a caller-drained
`deferred` collection. Accepted work remains durable until a typed success or dead
outcome exists.

## Immutable work identity

Every accepted work row binds the account, account epoch, active/deletion coordinate,
work kind, exact input frontier, exact input digest, and complete execution contract
digest. A changed input, frontier, model/prompt/policy/code/schema contract, or owner
gets different work identity. Raw transcript, memory, model output, query, provider
error, or prompt text is never job metadata.

Attempt budgets are structurally bounded to 1–100. Strategy-specific production values
remain versioned execution-contract decisions; neither a caller nor an environment
variable can select an unbounded retry loop.

P3 initially supports four closed work kinds:

- `formation`;
- `promotion`;
- `identity_cluster`; and
- `predicate_batch`.

Projection rebuild and delivery jobs enter later under their own contracts rather than
through an open string.

## State machine

The closed states are `pending`, `leased`, `retryable_failed`, `succeeded`, and
`dead_letter`.

- Acceptance creates `pending`, attempt zero, fence zero, and no lease or outcome.
- A lease is eligible only from `pending` or an eligible `retryable_failed` state. An
  expired lease must first record a typed `worker_lost` retry/dead outcome; it is never
  silently overwritten. A new lease increments both attempt and fence and uses a
  half-open `[leased_at, expires_at)` interval.
- Only the exact unexpired fence may finish or fail work. A stale worker cannot extend,
  succeed, fail, emit an outbox record, or consume accepted input.
- A retryable failure carries only a closed error code and a future eligibility time.
  If the attempt budget is exhausted it becomes `dead_letter`; exhaustion is never an
  abstention or deletion.
- Success binds exact response and result digests. A successful-empty result is still a
  durable success, not missing work.
- Terminal states are immutable. Equal transition replay is idempotent in the adapter;
  changed replay is a hard conflict.

Account lifecycle, epoch, credential/grant, and destination activation are revalidated
before lease and again before result commit. Deletion dominance may make work
ineligible, but it does not erase or rewrite its history.

## Atomic PostgreSQL obligations

Later P3 migrations and the real adapter must make each of these one transaction:

1. accept work plus its exact input manifest;
2. acquire/reclaim lease plus fence/attempt advance;
3. commit success plus authoritative graph transition, total formation outcome, and
   content-safe outbox coordinate; or
4. record retry/dead outcome without any graph allocation.

Outbox rows contain only a closed event kind, owner/work/result coordinates, and digest.
They never copy model output or raw evidence. Delivery acknowledgement is idempotent and
cannot make an uncommitted result visible.

The inert first migration stores terminal outbox events but grants no application or
worker access. A success event carries the exact result digest; a dead-letter event has
no fabricated result digest and binds only the terminal state digest. Delivery lease and
acknowledgement persistence land with the real worker adapter rather than guessing its
runtime authority in SQL.

## Pre-registered tests

The core slice succeeds only if adversarial tests prove:

- exact-shape acceptance rejects proxies, accessors, extras, unbounded tokens,
  non-digests, and invalid lifetimes before inspecting content;
- changed owner, epoch, deletion coordinate, frontier, input, or contract changes the
  accepted-work digest;
- pending lease, retry lease, and expired-lease reclamation advance fences
  deterministically, while early/backdated/ineligible lease attempts fail closed;
- the lease expiration boundary is expired, not still owned;
- stale/expired fences cannot succeed, fail, or consume;
- retryable failure remains retryable below budget and becomes `dead_letter` exactly at
  budget, with no abstention/deletion state anywhere in the API;
- success requires exact response/result digests and terminal replay cannot mutate;
- no durable job or outcome field can carry raw model output or raw error strings.

The PostgreSQL slice later adds two-worker races, lease expiry/reclaim, deletion and
credential revocation during work, process termination at every atomic boundary,
outbox crash/replay, and restart reconstruction. Fake/in-memory tests cannot satisfy
those gates.

## Explicit exclusions

- no model call or concurrency increase;
- no `subject:*`, bystander, compose-voice, or identity policy change;
- no route, service composition, PostgreSQL client, or runtime default;
- no environment-selected strategy or lease behavior;
- no raw provider exception, output, prompt, evidence, query, or answer in job state;
- no claim that SQLite dream tables are production authority.
