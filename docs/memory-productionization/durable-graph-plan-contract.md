# Durable graph work-plan contract

Status: P3 pre-registration, 2026-08-11

## Purpose

Give every durable memory work kind one parent-independent staged graph plan.
Model execution produces the plan once. A graph-head conflict may rematerialize
only its derivation/append envelope against a newly loaded parent; it cannot call
the model again, change the plan, or silently relabel the work kind.

This closes the remaining generic-runner gap between a sensitive normalized
result and an exact `AuthoritativeLedgerAppend`. It does not compose a model,
worker, database, route, or production runtime.

## Plan identity

One immutable plan binds:

- owner account, work kind, accepted job id/digest, account epoch, and exact
  input frontier/digest;
- the authority strategy's exact execution contract and derivation versions;
- a formation origin with one parsed total formation-v2 outcome, or the exact
  closed non-formation origin required by the job kind;
- immutable derivation inputs and output graph revisions;
- placement results/allocations, generated adjacency, operational artifacts,
  and any typed identity-authority witnesses required by validation; and
- a canonical plan digest over every field.

Formation plan provisional revisions must exactly equal accepted extraction
outcomes, and canonical revisions must exactly equal admitted placement
outcomes. Promotion, identity-cluster, and predicate-batch plans cannot smuggle
a formation outcome or use the wrong non-formation reason.

The staged plan is sensitive memory content. It uses the existing bounded plain
JSON result envelope and is never telemetry, a read model, or an answer surface.

## Parent-bound materialization

Materialization accepts only:

- a leased job whose accepted-work, input, owner, kind, epoch, and execution
  contract equal the plan;
- the exact registered authority strategy;
- the exact previously staged normalized result; and
- one current parent commit coordinate supplied by the authorized repository
  composition.

It deterministically derives attempt, commit, and idempotency identifiers from
the job, plan digest, and current parent. It rebuilds `PreparedDerivation`, then
constructs and validates one authoritative append with the exact origin. The
same plan plus parent is byte-idempotent. A different parent changes only the
parent-bound append identity and derivation; revisions, placement, origin,
result digest, and model response remain unchanged.

No caller-supplied append id, commit id, output digest, or success kind is
trusted. Successful-empty is derived from the validated allocation/output
contract, never used to hide missing work.

## Pre-registered acceptance tests

1. A total formation plan materializes an authoritative append whose accepted
   provisional and admitted canonical sets exactly equal its formation outcome.
2. Promotion, identity-cluster, and predicate-batch map only to their existing
   closed origins; cross-kind or formation/non-formation confusion fails.
3. The exact plan and parent are byte-idempotent. Changing only the parent
   changes append/attempt/commit identity while every planned graph byte stays
   equal and no producer/model callback exists.
4. Job owner, epoch, kind, accepted digest, input frontier/digest, strategy
   execution contract, result contract, staged-result digest, and plan digest
   mismatches fail before an append repository can be called.
5. Missing/extra provisional or canonical revisions, bad placement/adjacency,
   forged identity authority, cross-owner nested data, hostile objects, aliases,
   cycles, sparse arrays, non-finite values, and oversized plans fail closed.
6. A staged result cannot be replaced by an append-shaped object or a plan from
   another job. Provider/model text is never copied into errors or telemetry.
7. Focused/full tests, contract tests, import lint, strict changed-file
   TypeScript filter, bundle parse/build, and `git diff --check` pass before the
   unit is recorded.

## Explicit exclusions

- No formation extractor/placement composition, evidence loader, graph-head
  repository, PostgreSQL adapter, worker grant, scheduler, route, service
  default, or deployment is added.
- No subject tier, bystander/privacy, identity-authority policy, compose voice,
  data disposition, blind grading, or strategy promotion behavior changes.
- Real PostgreSQL transaction, crash, race, privilege, and pool semantics remain
  gated on the ratified version/client/runtime and `test:postgres`.
