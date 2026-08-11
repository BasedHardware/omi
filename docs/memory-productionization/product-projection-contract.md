# Product proposition identity and projection contract

Status: P4 pre-registration, 2026-08-11

## Purpose

This contract freezes the production-neutral product-memory mechanics required by
ADR-006, ADR-009, ADR-013, and ADR-014 before a PostgreSQL product projection,
migration copier, background projector, or app route is implemented. It does not
change the current `/v1/memories` response, expose claim rows, or create a second
memory API.

The authoritative append-only ledger and the product read model remain separate.
The ledger owns evidence, claims, lineage, identity authority, liveness, and graph
commits. The product read model owns stable proposition identity, versioned
membership, immutable projection history, redirects, conflicts, citations, and
rebuildable grouping/search rows.

This unit is deliberately independent of the open PostgreSQL runtime decision. It
can be verified as a pure contract now and later persisted behind the already
ratified PostgreSQL authority boundary.

## Fixed identities

The following coordinates are never overloaded:

- `claim_lineage_id` is the ledger lineage;
- `canonical_claim_id` is an authoritative claim identity;
- `proposition_id` is the stable user-visible product identity;
- `membership_revision_id` versions the set of claim lineages represented by one
  proposition;
- `projection_revision_id` versions one human-readable rendering;
- `group_projection_id` is a disposable rebuildable grouping row and is never an
  identity exposed as the target of a correction, comment, conflict, or citation.

A native proposition is born against exactly one claim lineage and its first
membership revision contains exactly that lineage. Routine ledger consolidation,
claim supersession, or correction may append a membership revision to the same
proposition. Those operations never mint a successor proposition.

Product-level merge and split operations are different. They append attributable
redirect records. A superseded proposition stays resolvable forever and resolves to
one or more successor propositions. Redirect traversal is owner-local, acyclic, and
bounded. Nothing may delete the source identity merely because it is absent from the
current list surface.

## Migration identity

Migration identity is a repository operation, not a hash helper.

For every legacy item, the copier transaction:

1. binds one exact `(account_id, legacy_source_id)` coordinate;
2. checks the account lifecycle/deletion fence and the item tombstone;
3. reads the insert-if-absent mapping for that exact coordinate;
4. reuses the winner if a mapping already exists;
5. otherwise asks an injected cryptographically secure random-ID port for an opaque
   proposition id and inserts it with `ON CONFLICT ... DO NOTHING` semantics;
6. rereads and uses the winning mapping;
7. rechecks lifecycle and the item tombstone before copying product data.

No function in core derives a proposition id from account bytes, a legacy id, a
claim id, a content digest, or a model response. The unresolved ADR-012 word-slug
grammar is not minted or validated here. A tombstoned item returns a closed
`tombstoned` decision and cannot allocate, map, or copy an identity. Exact replay
returns the same mapping; a mapping whose immutable owner/source/id tuple changes is
a conflict, never an overwrite.

## Membership and projection history

Membership is append-only and versioned. Every revision binds:

- owner and proposition;
- a monotonically increasing revision sequence;
- the exact parent membership revision, except at birth;
- a non-empty, sorted, duplicate-free claim-lineage set;
- the ledger graph frontier and derivation/result digest that produced it;
- a closed cause: `birth`, `ledger_consolidation`, `correction`, or
  `product_successor`.

Only `birth` has no parent and it contains exactly the proposition's birth lineage.
Routine changes use `ledger_consolidation` or `correction`. A newly created product
merge/split successor may use `product_successor`, but the proposition identity record
still names one birth lineage and the first revision still contains exactly that
lineage; any expansion is a later attributable revision. Membership never refers to a
group projection.

Projection revisions are immutable. Each binds the proposition, exact membership
revision, graph frontier, renderer contract, rendered-content digest, and a complete
set of citation-support records. Recomputing with a new provider or renderer appends a
revision and does not change the proposition id. A projection with no citation support
is not servable. Citation support binds exact claim revisions and evidence revisions;
it never cites a current group or an unversioned source label.

The latest projection is selected only after reader-relative authorization and
deletion-dominant liveness have been applied. A hidden newer projection cannot suppress
an older authorized projection. The product projection layer receives an authorized,
coherent snapshot from the existing application-read boundary; it never accepts an
account-wide global head as a substitute.

Time-travel uses an immutable snapshot frontier plus a `(sequence, revision id)`
keyset cursor. It must not skip or duplicate history when a newer projection is
appended concurrently.

## Redirects, conflicts, and grouping

A redirect is append-only, attributable, and owner-scoped. It names one superseded
source proposition and a non-empty sorted successor set. Merge may converge several
sources on one successor; split may map one source to several successors. Redirect
resolution returns the terminal successor set, detects cycles, and has a fixed depth
and fan-out bound. Comments, corrections, and citations resolve through the same
redirect graph rather than dangling.

An unresolved conflict references at least two distinct proposition ids and has no
fabricated winner. A later resolution records an explicit resolved proposition set and
preserves the original alternatives and history. Conflict/correction execution remains
a later attributable write slice; this unit freezes only the reference invariant.

Grouping is a rebuildable projection over proposition ids. It may improve browsing and
search presentation, but:

- no proposition, membership, redirect, conflict, correction, comment, or citation row
  may depend on a group id;
- deletion of every grouping row changes no authoritative identity or history;
- recall completeness and migration loss count propositions, never groups;
- grouping is versioned by its exact input frontier and projection contract.

## Completeness and integration

Product reads preserve the existing `RecallCoverage` honesty boundary. A page can claim
complete durable product coverage only when its authorized product-projection frontier
matches the authorized ledger frontier and any accepted/STM overlay is accounted for.
Missing projection work, excluded dead-letter work, stale grouping/search indexes, or an
unsearched recent overlay is reported as an explicit partial reason, not an empty answer.

The existing `/v1/memories` route, MCP door, and chat/agent memory port remain the only
supported consumption seams. The current QA seeded loader stays explicitly QA-only
until a PostgreSQL projection repository passes the real database gate. This contract
does not add a query-recall endpoint, change composition voice, change `subject:*`
admission, or alter the bystander privacy boundary.

## Production-neutral implementation slice

The first core slice will provide strict, pure constructors and transitions for:

- native proposition birth;
- append-only membership revision;
- immutable cited projection revision;
- append-only redirect validation and bounded terminal resolution;
- legacy mapping decisions that consume an externally allocated random opaque id but
  never derive one;
- rebuildable grouping rows whose identifiers cannot inhabit authoritative refs.

Inputs must be exact plain data: no proxies, accessors, sparse/decorated arrays,
unexpected keys, unbounded identifiers, duplicate unordered sets, or non-finite
numbers. Durable failures use closed codes and never preserve rendered content, model
errors, legacy ids, or provider responses in diagnostics.

## Pre-registered acceptance tests

The pure slice is accepted only if tests prove:

1. Native birth creates one stable proposition and a one-member birth revision.
2. Correction, ledger supersession, and renderer/provider recomputation preserve the
   proposition id while appending deterministic revision coordinates.
3. An invalid birth, empty/duplicate/unsorted membership, missing/wrong parent, stale
   revision sequence, cross-owner reference, or group id in authoritative input fails
   closed.
4. Exact replay is byte-identical; changed immutable input under the same revision id
   conflicts loudly.
5. A migration mapping wins by insert-if-absent semantics, a concurrent loser reuses
   that winner, and tombstoned input never requests/allows allocation.
6. No production-neutral core API accepts a derivation function from legacy bytes; a
   proposed opaque id equal to or containing the legacy id is refused defense in depth.
7. Redirect chains resolve to terminal propositions; merge and split fan-out work;
   cycles, self redirects, dangling successors, excessive fan-out/depth, and
   cross-owner edges fail closed.
8. A cited projection requires exact non-empty claim/evidence support, one current
   membership revision, and a matching frontier/contract digest.
9. Authorized-latest selection filters before choosing the maximum sequence, so a
   hidden newer revision cannot suppress an older visible one.
10. Grouping rows can be dropped and rebuilt without changing proposition,
    membership, projection, redirect, conflict, correction, or citation identities.
11. Strict plain-data adversaries and oversized values fail without durable raw
    diagnostics.
12. The focused suite, full `bun test`, import graph, contract QA, strict TypeScript,
    and `git diff --check` pass before the slice is recorded.

## Explicit exclusions and gates

- No PostgreSQL product schema, repository, migration copier, worker, pool, or route is
  activated by this contract.
- No comment mutation or conflict-resolution UI is implemented in this slice.
- Search and embeddings remain rebuildable later projections; pgvector stays dormant.
- No legacy memory is copied and no real user data is read.
- Bystander/privacy policy, `subject:*` admission, compose voice, data disposition,
  blind grading, cohort selection, and deployment remain David-gated.
