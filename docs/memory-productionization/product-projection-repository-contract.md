# Product projection repository contract

Status: P4 service-boundary pre-registration, 2026-08-11

## Purpose

This contract freezes the service seam between the pure product-projection core
and a later PostgreSQL adapter. It adds no database client, SQL execution,
worker, route, grant, migration copier, or runtime default.

The repository has named product operations only. It never lends a connection,
accepts SQL, mints authority, or accepts a raw account id as read authority.

## Projector writes

Every write receives an already-issued `AuthorizedLedgerWriteContext` whose
exact capability is `memories.project`. The eventual PostgreSQL adapter must
lock and revalidate that context with the database clock before replay or
mutation. Each request binds one exact owner-local graph commit coordinate and
one closed operation:

- append proposition birth plus its one-member birth membership atomically;
- append a later membership revision;
- append projection metadata, rendered payload, and complete citations
  atomically;
- append one attributable redirect; or
- append one rebuildable group projection.

The boundary re-parses every pure-core row, rejects cross-owner or cross-
proposition combinations, checks the graph frontier, and verifies a bounded
canonical JSON payload against `rendered_content_digest`. Its request digest
binds the operation, graph coordinate, all immutable records, and payload.
Diagnostics use closed codes and never include rendered content.

Exact immutable replay returns the persisted result. The same immutable id with
different bytes is a conflict. A changed graph head is stale work, never an
implicit rebuild or a second model call. Serialization failure is explicitly
retryable. Authority and lifecycle denial happen before replay observation.

Redirect cycle/dangling validation remains a transaction responsibility because
only the adapter can read the authoritative owner-local redirect graph. Group
rows remain disposable and cannot be referenced as proposition identities.

## Authorized reads

The read port accepts only the existing branded
`ApplicationGrantProjectedTreeInputSnapshot`, created after credential and grant
authorization. An adapter returns candidate identities, memberships,
projections, and payloads for that exact authorized projection. The service
facade then:

1. re-parses every row as strict plain data;
2. applies the existing citation/evidence/claim closure validator;
3. requires every returned projection to have exactly one payload and no extra
   payload;
4. recomputes each payload digest; and
5. returns a branded authorized product read set.

The adapter must filter by reader authorization before latest-head selection. A
hidden newer projection therefore cannot suppress an older visible projection.
The existing application-read final revalidation remains mandatory after the
consumer renders the result.

## Explicit exclusions

- Legacy mapping/tombstone operations are absent. They require a separately
  ratified migration-copier authority and cannot borrow app or projector grants.
- The port does not activate `0005-product-memory-projections.sql` or grant any
  role access.
- It does not change `/v1/memories`, MCP, chat composition, `subject:*`,
  bystander/privacy policy, or compose voice.
- It does not claim real PostgreSQL, pool, crash, replay, load, or recovery
  qualification.

## Pre-registered acceptance tests

1. A forged/unissued context, wrong capability, owner substitution, stale graph
   coordinate, or malformed core row is rejected before the adapter runs.
2. Birth requires one matching birth membership; later membership and projection
   writes require exact owner, proposition, membership, and frontier agreement.
3. Payloads reject proxies, accessors, sparse/decorated arrays, non-JSON values,
   oversized bytes, non-object roots, and digest mismatch.
4. Request digests change with any operation, graph, record, citation, payload,
   or payload-contract change.
5. The public repository surface exposes named methods only and no query/execute
   or connection capability.
6. Reads reject an unbranded snapshot before loading, cross-owner/hidden citation
   rows after loading, missing/duplicate/extra payloads, and payload digest drift.
7. An authorized older projection remains readable when an unauthorized newer
   projection was correctly omitted by the adapter.
8. Focused tests, full tests, contract QA, import lint, the strict changed-file
   TypeScript filter, and `git diff --check` pass before this slice is recorded.
