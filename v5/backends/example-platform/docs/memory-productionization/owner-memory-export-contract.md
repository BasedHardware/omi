# Route-free owner memory export contract

Status: implemented and real-PostgreSQL qualified; inert by construction.

## Boundary

This is a private owner/support-copy primitive over an already authorized
reader-relative memory projection. It is not the ADR-014 terminal-deletion
replay record, and it does not choose a route, object store, retention period,
approval workflow, sharing policy, model, or deployment.

The PostgreSQL composition requires the exact `memories.export` application
capability. A `memories.read` grant alone is insufficient. Grant and lifecycle
authority are revalidated before graph access, after renderer I/O, and once
more before any manifest or chunk bytes are returned. Export permission is an
application action; memory claims and attribution beliefs remain independent
of that permission.

## Artifact shape

The export is a deterministic manifest plus bounded chunks. Each chunk ends at
a complete synthesized memory boundary and carries:

- the user-legible synthesized memory text and source language;
- every authorized claim lineage and exact live revision represented by that
  memory;
- observation time and temporal precision for each lineage; and
- every supporting evidence excerpt, range, event, and capture coordinate.

All internal memory, lineage, revision, evidence, event, and capture identifiers
are replaced by reader-scoped, domain-separated `mxr1_` references. Excerpts
remain content because this is the private data copy, not an operational log.

The manifest binds the exact authorized projection snapshot, export timestamp,
fixed `temporal_leaf` item granularity, total memory/lineage/source counts, and
ordered chunk digests. A strict consumer verifier rejects alternate JSON
encodings, missing/reordered/tampered chunks, count drift, duplicate memories or
lineages, malformed references, and digest drift.

## Completeness and scale

The builder requires exactly one produced render for every authorized temporal
leaf and exactly one exported occurrence of every visible claim lineage.
Omission, duplicate lineage, a stale/tampered render, an oversized individual
memory, or a cloned authorization projection fails the whole export. It never
silently truncates.

The chunk byte limit is explicit and bounded from 64 KiB through 16 MiB. This
keeps the contract compatible with a future streaming/object-store writer
without committing to a storage vendor or one giant response body.

## Qualification

On 2026-08-12 the pinned PostgreSQL 18.4 gate passed 9/9 real tests with 531
expectations. It returned a nonempty export over the application role, verified
the manifest and cited lineage counts, proved raw lineage ids do not reach the
artifact, then revoked only `memories.export`: export denied while the separate
`memories.read` capability remained usable. PostgreSQL/Postgres.js parity also
passed under pinned Bun 1.3.14 and Node 24.19.0, including backend termination
and reconnect. The managed Colima runtime was stopped afterward and its labelled
volume preserved.

## Nonclaims

- The export contains only the selected authorized projection. Expanding owner
  visibility to additional policy classes is a separate projection-policy
  decision; this contract does not silently broaden it.
- No public or cross-account sharing, route, sink, archive encryption, download
  lifecycle, legal disclosure format, or production cohort is activated.
- Exact retention, RPO/RTO, lease, approval, and stranded-data windows remain
  injected operational policy.
- The renderer is injected. Product model/prompt selection and fresh blind
  quality evidence remain separate gates.
