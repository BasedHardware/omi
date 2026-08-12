# Shadow result and offline replay contract

Status: P5 contract plus real PostgreSQL result/pair adapter qualification,
2026-08-12; graph-query input, model runtime, route, and activation absent

## Purpose

Let a registered memory strategy run on production-shaped or copied evidence
without acquiring any authoritative graph, product-projection, or answer write
capability. Preserve paired/repeated evidence so later machine comparisons and
blind sheets can be generated without rerunning a model or confusing an
experimental result with user memory.

## Evaluation coordinates

One evaluation result binds:

- owner account and current account epoch;
- an already minted strategy-assignment bundle and one exact assignment entry;
- role `baseline` for the bundle authority strategy or `candidate` for a selected
  shadow strategy;
- mode `live_shadow` or `offline_replay`;
- opaque evaluation-run id, exact input frontier and digest, and repeat ordinal;
- exact strategy and execution-contract digest;
- exact result-contract, provider-response, and normalized-result digests; and
- one bounded detached normalized-result object.

The raw assignment unit, assignment secret, transcript, prompt, provider body,
query, answer, and error text are never stored in an evaluation coordinate or
default telemetry. The normalized result is sensitive and may contain derived
memory content, so it is stored only in the protected result table and is never
content-safe telemetry.

Baseline and candidate results are separate immutable physical relations.
Baseline rows must reference the bundle's exact authority assignment. Candidate
rows must reference an actually selected shadow assignment. Neither relation is
referenced by durable-work acceptance, graph commits, product projections, recall
reads, or answer rendering.

## Pairing and repeats

A pair is derivable only from one baseline and one candidate with identical
owner, account epoch, bundle, evaluation mode/run, input frontier/digest, and
repeat ordinal. Strategies must differ. Pair identity contains only opaque ids
and digests and is stable under replay.

Repeat ordinals are explicit rather than inferred from arrival order. This makes
read-side self-disagreement and repeated model behavior measurable without
turning an unpaired comparison into evidence. The contract records pairs; it does
not self-grade truth or compute a benchmark verdict.

## Repository and persistence boundary

A sealed repository requires the separate `memories.experiments.shadow`
capability and exposes only immutable stage/load/pair-record operations. It validates the
minted assignment, owner, epoch, role, strategy, result contract, normalized
result digest, and request digest before calling an adapter. Same bytes replay;
different bytes at the same coordinate conflict. No success, append, projection,
read, query, route, SQL, clock, model, or logging capability is exposed.

Checksummed migrations add account-scoped baseline, candidate, and pair tables
plus the minimum composite key required to reference selected shadow assignments
exactly. Migration 23 grants the application role only `SELECT, INSERT` on
those isolated relations. The sealed adapter revalidates the exact
`memories.experiments.shadow` authority before lookup or replay. It activates
no route, model runner, query source, graph/product authority, default, or
traffic.

The PostgreSQL 18.4 application-role gate stages baseline and candidate rows,
round-trips normalized JSON, records and replays the opaque pair, rejects
updates/deletes, and denies a replay after grant revocation. Bun 1.3.14 and the
pinned Node 24 control both pass the same migration/runtime corpus.

## Pre-registered acceptance tests

1. Baseline accepts only the bundle authority entry; candidate accepts only a
   selected shadow entry. Wrong owner, epoch, work kind, strategy digest, result
   contract, or unminted/forged bundle fails before adapter invocation.
2. Normalized results reject non-plain/proxy/accessor/class/cyclic/aliased/sparse,
   oversized, or non-canonical data using the existing bounded result contract.
3. Same coordinates and bytes replay with the same opaque result id. Any response,
   normalized result, repeat, frontier, input, strategy, mode, or run change has
   a different identity; same coordinate with different bytes conflicts.
4. Pairing refuses unpaired input/frontier/repeat/run/mode/account/bundle, two
   baselines, two candidates, or the same strategy. Reordered arrival cannot
   change pair identity.
5. Serialized default pair metadata contains only stable opaque ids, digests,
   modes, counts/ordinals, and versions; it contains no normalized result or raw
   source content.
6. Migration/static tests prove exact authority-baseline and selected-shadow
   foreign keys, account scope on every key, no relation from evaluation tables
   into graph/projection/read authority, bounded JSON, and append-only isolated
   application-role grants.
7. Focused/full tests, contract QA, import lint, strict changed-file TypeScript
   filter, bundle parse/build, and `git diff --check` pass before recording the
   unit.

## Explicit exclusions

- No model runner, copied-evidence loader, evaluator, McNemar calculator,
  contamination audit, blind-sheet renderer, human grading, or promotion rule is
  implemented in this unit.
- No subject tier, bystander/privacy, identity authority, compose voice, data
  disposition, database/runtime choice, worker grant, route, cohort, deployment,
  or traffic decision changes.
