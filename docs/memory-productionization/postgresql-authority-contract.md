# PostgreSQL memory authority contract

Status: P2 pre-registration plus an inert graph/formation/identity/liveness append adapter,
2026-08-11

## Decision boundary

This contract was frozen before the first PostgreSQL migration and transaction-boundary
scaffolding were added. It implements the already-ratified direction in
backend ADR-009, ADR-010, ADR-013, and ADR-014; it does not choose new product or
data-disposition policy.

The current tree now contains inert, checksummed migration files, a sealed service
repository contract, Postgres.js 3.4.9, a migration runner, a hermetic PostgreSQL 18.4
container harness, and a transaction-time authority revalidation boundary. The narrowly
named successful-empty repository kernel remains available, and an inert full append
adapter has now been exercised against the real database under the application role for
nonempty event/evidence/claim graphs, total formation outcomes, and identity
authorization/mention/constraint/adjacency writes. The real gate also covers exact
replay, cross-account key isolation, one-head races, atomic rollback, revocation before
replay, and transaction-local context cleanup. SQLite remains the offline/QA reference.
This is not a production authority or activation claim.

One identifier choice remains outside this unit:

- the account identifier grammar is blocked by backend ADR-012's reconciliation note.
  This slice accepts a bounded opaque platform account key and neither mints nor
  validates either proposed word-slug grammar.

No pgvector, FTS, product route, model call, worker execution, Cloud SQL resource,
production credential, or runtime default enters this unit.

## First slice

The planned slice has four parts:

1. an append-only, checksummed, expand-only migration manifest;
2. an internal PostgreSQL transaction boundary over one checked-out connection; the
   exported callback receives only frozen, revalidated metadata and no arbitrary SQL
   capability;
3. an asynchronous `AuthoritativeLedgerRepository` contract that accepts only a sealed write
   authorization context and a complete atomic graph transition;
4. shared SQLite/PostgreSQL invariant fixtures plus PostgreSQL-only concurrency,
   pooling, and crash tests.

The checked-in repository contract, transaction revalidation boundary, successful-empty
kernel, and full append adapter are inert. The adapter persists every current graph
revision and artifact kind plus total formation accounting, and verifies durable
committed witnesses and the active identity-authorization head before reserving a
receipt. Claim purge/forget is now an exact `manual_liveness` transition: it requires
committed claim witnesses and derivation inputs, writes a commit-linked closed-code
fence, and advances the same graph frontier atomically. The old SQLite side-write API
has been removed. An inert owner-internal reconstruction adapter now rebuilds a deterministic
`GraphSnapshot` from checksummed authoritative rows through a fresh application-role
pool, but product-projection rebuild and a separately ratified read/rebuild capability
remain unimplemented; and a backend terminated during a Bun + Postgres.js transaction
rolls back atomically but leaves the size-one pool unable to recover promptly. Those
remain activation blockers. A later unit may add exactly one
canonical service composition only after the complete gate exists. The existing synchronous `LedgerPort.findCommitByIdempotencyKey` is
not a production PostgreSQL seam and is not widened or faked. Model preflight will use
an asynchronous authorized lookup owned by the new repository.

## Authority context

The application-facing repository never accepts a caller-selected owner by itself. Its
write capability binds:

- authenticated principal and platform account;
- application id;
- credential id and generation;
- required capability;
- exact active grant id and version;
- account epoch and destination activation revision;
- lifecycle state and deletion epoch;
- authentication strength and expiry; and
- an authorization-state digest covering the persisted rows that minted the context.

The static import fence reserves construction for one future reviewed
authentication/authorization composition boundary; no production composition is wired
yet. Ordinary application and driver modules receive only the public validation facade.
This is a checked code-organization boundary, not a claim that JavaScript module access
is cryptographically unforgeable. The PostgreSQL transaction re-reads and locks the referenced subordinate
account-control projection, credential, and grant rows. Generation, account epoch,
lifecycle, deletion epoch, and destination activation are fields/revisions of that one
control projection, never a second mutable lifecycle authority. Missing, stale,
conflicting, expired, migrating,
deletion-pending, deleted, inactive, or mismatched state denies before idempotency replay
is returned.

The PostgreSQL control/lifecycle state remains subordinate. Only a verified legacy
observation may append a control revision and advance its current head; the destination
cannot independently transition legal account generation or lifecycle. The projection
includes terminal tombstones for never-migrated accounts as well as migrated accounts.

Every owner-bearing value in the transition must equal the context account. Payloads,
model responses, evidence, and job records never choose their tenant.

## Structural tenant isolation

Every authoritative table carries `account_id`. Every primary, unique, and foreign-key
relationship that can connect two authoritative records includes `account_id`, even
when its opaque row id is expected to be globally unique. A valid foreign key can never
represent a cross-account edge.

This specifically covers event/evidence lineage, claim/mention lineage, identity
support and authorization, generated adjacency, placement artifacts, derivation
attempts and commits, graph heads, purge/forget fences, formation work/outcomes, and
idempotency receipts in P2.1. Later schema units apply the same rule to jobs, outbox
records, propositions, projection membership, citations, and experiment assignments.

PostgreSQL row-level security may be added only as defense in depth after the pool test
below proves transaction-local context. It is never the only tenant boundary.

## Expand-only schema order

The P2.1 migration set introduces only the first three logical groups required for an
atomic ledger/formation append. Later migrations remain expand-only and apply the same
contract, but do not enter P2.1's success claim:

1. **Account root and control projection** — opaque account root, immutable subordinate
   legacy control revisions carrying generation/epoch/lifecycle/deletion state, one
   current control head, destination activation on that projection,
   credential binding, exact grant, and their immutable audit revisions.
2. **Ledger authority** — owner graph head; event, evidence, claim, mention, identity,
   predicate, entity, adjacency, placement, liveness, derivation-attempt, and
   derivation-commit rows. Immutable payloads are strict versioned JSON only where a
   normalized relational column would duplicate core schema authority.
3. **Formation coordinates** — accepted input, exact response digest, candidate
   manifest, total extraction and placement outcomes, and terminal-deletion export
   records. Durable lease/retry/dead/outbox execution remains P3.
4. **Later P3 work coordinates** — accepted work, lease tuple, retry/dead state, and
   outbox records bound to account epoch, lifecycle/deletion epoch, input frontier, and
   exact work versions.
5. **Later P4/P5 rebuildable coordinates** — proposition-per-lineage identity, versioned
   membership, redirects, projection revisions, citations, conflicts, comments,
   search-generation metadata, migration mapping, and experiment namespace. Runtime
   projection and search remain P4/P5.

Historical migrations are immutable and checksummed. Applying the same set twice is a
no-op; changing the bytes of an applied migration is a hard failure. One advisory lock
serializes migrators. Migrations do not run implicitly from a request handler. Ordinary
application rollback never runs a down migration; destructive contract work requires a
separate ratified removal gate after old readers and backfills are retired.

Database roles enforce the append-only split. A migration owner may perform DDL. The
application role has no DDL, has `SELECT`/`INSERT` on immutable revision/history tables,
has narrowly named `UPDATE` privileges only on current-head and receipt rows, and has no
`DELETE` privilege on authoritative history. Worker/operator roles are separate and do
not inherit broader application identity by convention.

## One append transaction

One `SERIALIZABLE` transaction on one checked-out connection performs, in order:

1. set transaction-local account, principal, grant, epoch, lifecycle, and capability
   settings;
2. lock and revalidate the account root, the single subordinate control projection
   (including destination activation and lifecycle/deletion state), credential, and
   exact grant;
3. validate that the complete transition and all referenced durable witnesses belong
   to the authorized account;
4. reserve or read the owner-scoped idempotency receipt;
5. compare the expected parent to the locked owner graph head;
6. append every immutable revision, identity witness, adjacency edge, placement
   artifact, liveness fence, derivation attempt/commit, and the validated total
   formation outcome when this is a formation-originated transition;
7. advance the graph head with a compare-and-swap predicate;
8. finalize the receipt and transactionally coupled formation coordinates; and
9. commit.

Any error rolls back every stage. A connection error, cancellation, or callback throw
must roll back and discard or safely reset the connection before it returns to the
pool. Session-level `SET`, a pool-wide `BEGIN`, and work split across independently
borrowed clients are contract violations.

## Replay and conflict semantics

Formation work and graph append attempts have separate identities. The immutable
`formation_work_id` binds accepted input, complete input frontier, strategy/schema
coordinates, candidate manifest, and a content-safe digest of the strict model response;
it does not store raw model output in an idempotency receipt. A graph-append attempt has
its own key and binds one exact parent head plus the normalized transition digest.

The append-attempt idempotency key is structurally scoped by `(account_id,
account_epoch, idempotency_key)`. Its immutable value covers the content-safe response
digest/manifest, complete input frontier, parent head, formation work id, strategy and
schema versions, and normalized transition input digest.

- same account, epoch, key, and digest returns the recorded commit exactly;
- same account, epoch, and key with a different digest is a hard conflict;
- another account cannot collide or observe whether the key exists;
- a stale epoch, inactive lifecycle, revoked grant, or deactivated destination denies
  before a prior receipt can be replayed;
- a graph-head conflict returns a typed stale-parent outcome and writes nothing; a
  caller may retry only after rebuilding the complete transition against the new head.
  That retry creates a new append-attempt key bound to the new parent and reuses the
  already-validated formation result retained by the caller, without invoking the model
  again. Restart-safe persistence of accepted formation work is a P3 requirement and an
  activation blocker; P2.1 does not falsely claim it from an outcome row whose append
  transaction rolled back; and
- a serialization failure is a typed retryable outcome that writes nothing and never
  mutates or silently retries the plan.

Formation work is never inferred to have abstained or disappeared. Retryable and dead
outcomes remain durable, retain their candidate accounting, and cannot allocate a
canonical claim. A graph commit found after a crash is replayed before any model call.
Every formation-originated graph commit links exactly one validated total formation
outcome. A repair, manual liveness, or other non-formation transition explicitly declares
that it has no formation work; neither transition class may omit its accounting by
accident.

## Liveness, deletion, and rebuild

Purge and forget fences are monotone ledger facts and retain the existing closed
`purged | forgotten` cause set; there is no delete or unfence path. Supersession,
evidence/item tombstones, and the terminal account tombstone are separate typed
coordinates rather than new claim-liveness causes. Deletion lifecycle dominates
requests, model work, leases, outbox, migration resume, projection rebuild, and index
rebuild. The terminal account tombstone survives product-data disposal.

Product projections, search documents, embeddings, grouping, and experiment views are
rebuildable. No authoritative repair depends on them. With fixed ledger bytes and fixed
schema/strategy coordinates, a rebuild must produce the same projection revision ids,
content digests, citation closure, liveness, and reader-relative head selection. Grant
eligibility is applied before lineage-head selection and ranking.

Restore and deletion disposal are not proven by this first unit. Before real-user
writes, a later gate must prove PITR, tombstone replay before traffic, export/deletion,
stranded-account recovery, retention, and David-approved RPO/RTO/data disposition.

The first persistent schema nevertheless reserves the ADR-014 terminal-deletion export
contract: every transition to `deleted` appends one versioned immutable record containing
the opaque account id, deletion epoch, transition time, generation state, and whether
stranded data existed. Its retention-locked external sink and disclosure/retention policy
remain P7/pre-cohort human gates.

The later P4 migration proposition identity is an insert-if-absent mapping from
`(account_id, legacy_source_id)` to a random opaque proposition id. It is never derived
from legacy bytes. Every migration resume checks both this mapping and item tombstones
before copy, so rollback and re-cutover cannot resurrect deleted identities.

## Pre-registered tests

The first slice succeeds only when a repository-owned real PostgreSQL gate proves:

- fresh migration, identical reapply, concurrent migrator serialization, checksum
  drift rejection, failed-migration rollback, and expand-only compatibility;
- supported server-version refusal before authority writes;
- the application role cannot execute DDL or update/delete immutable authority rows;
- a `pg_catalog` structural audit proving every authority-bearing primary, unique, and
  foreign-key relation carries `account_id`;
- structural rejection of cross-account event/evidence, claim/mention, identity,
  adjacency, placement, formation, and receipt relationships;
- one-client transaction identity across every write stage;
- transaction-local context cleared after success, rollback, callback failure,
  cancellation, and alternating tenants through a size-one pool;
- tampering with transaction-local settings cannot substitute for the locked control,
  credential, and grant rows, and SQL account bindings always come from the sealed
  context;
- same-input replay, changed-input conflict, cross-account noninterference, stale epoch,
  revoked grant, expired context, deactivated destination, deletion-pending, and deleted
  refusal;
- two writers racing one graph head yield one commit and either a typed stale-parent or
  typed retryable-serialization result, with no hidden plan mutation;
- account creation seeds its graph-head row at sequence zero in the same transaction,
  so every append locks an existing head and two first writers never race an absent row;
- injected failure after every P2.1 append stage leaves no partial revisions, outcome,
  receipt, head, formation coordinate, or deletion-export row;
- termination of the checked-out backend at a named pre-commit checkpoint after its
  first write leaves no commit, verified from a separate connection;
- active identity-witness verification, superseded/tampered witness rejection, monotone
  liveness, and process-restart reconstruction;
- stale-parent retry from one retained validated formation result without a second model
  call; restart recovery of accepted work remains a P3 gate;
- empty and nonempty authoritative ledger reconstructions produce byte- and
  version-stable snapshots; and
- the shared synthetic transition has semantically identical SQLite and PostgreSQL
  ledger snapshots while PostgreSQL remains the production-semantic arbiter.

P3 separately gates deletion during leases and outbox crash/drain. P4 separately gates
nonempty product projection rebuilds covering citations, liveness, multiple lineage
revisions, and the reader-relative case where a hidden newer head must not suppress an
older visible revision.

Mocks and SQLite may exercise query planning and shared fixtures, but cannot satisfy the
pool, lock, isolation, cancellation, backend-termination, or migration gates.

The hermetic entrypoint is `bun run test:postgres`. It starts a loopback-only database
of the ratified major from a digest-pinned image, uses randomized synthetic credentials
and an exactly labelled persistent volume, refuses ambient PostgreSQL selectors, and
removes only its own resources. The developer setup, status, non-destructive teardown,
restart, and destructive reset workflow is documented in
`local-postgres-qualification.md`.

The current executable corpus proves migration reapply, the real callback-scoped
Postgres.js serializable transaction path, rollback-local cleanup, graph/formation/
identity writes, exact liveness replay with a commit-linked fence and incremented
frontier, deterministic graph reconstruction through a fresh application-role pool,
the shared SQLite/PostgreSQL graph-snapshot digest, and Bun 1.3.14 versus Node 24.19.0
client parity. It also terminates a size-one pool's checked-out backend at a named,
query-quiescent pre-commit checkpoint after the first write: a separate connection sees
no commit, the dead lease is not committed or returned to the open queue, and the next
transaction reconnects with cleared local authority state under both runtimes. Arbitrary
in-flight query cancellation, complete injected-failure coverage, and product-projection
reconstruction remain open.

## Activation blockers outside this slice

The scaffolding stays inert and no adapter may be activated until all of the following
are true:

- PostgreSQL major, exact test image digest, and client driver are ratified and pinned;
- the real PostgreSQL gate above passes;
- one canonical service composition owns the repository;
- P3 durable job execution and P4 product projection/read integration pass their own
  contracts;
- account deletion, restore, export, and cohort evidence pass P7/P9 gates; and
- no bystander, `subject:*`, compose-voice, blind-grade, or data-disposition human gate
  has been bypassed.
