# Read-side memory experiment strategy contract

Status: P5 preregistration, 2026-08-11; implementation not yet landed

## Purpose

Make retrieval and composition experiments first-class in the isolated replay
and evaluation plane without turning them into durable graph-writing work or a
product default. The current registry covers only the four authoritative
durable work kinds; this expansion closes that measured read-path gap.

## Type and authority split

Introduce a closed `MemoryStrategyKind`:

- durable kinds: `formation`, `promotion`, `identity_cluster`,
  `predicate_batch`;
- evaluation-only read kinds: `retrieval`, `composition`.

Strategy definitions, assignment policies/bundles, isolated baseline/shadow
results, pair records, copied-input replay, opaque exports, and paired statistics
may use every `MemoryStrategyKind`.

`DurableMemoryWorkKind` remains unchanged. Durable acceptance, leasing,
staging, graph plans, atomic success, work outbox, product projection, and
authoritative append remain restricted to the four existing durable kinds. A
retrieval/composition assignment presented to durable acceptance must fail
before its adapter is called.

## Strategy coordinates

Read-side definitions still bind the complete existing coordinate set. Values
that do not apply use the literal `none`; no coordinate is omitted. At minimum:

- retrieval binds model/query-planning, prompt, policy, code, schema, tokenizer,
  tool, result-contract, and retrieval strategy versions;
- composition binds model, prompt/voice, policy, code, schema, tokenizer, tool,
  result-contract, and composition strategy versions.

The current field names remain stable in v1; read-side-specific vocabulary is
encoded in their version values rather than silently changing identity shape.

## Persistence

An expand-only checksummed migration widens only the work-kind checks on the
existing inert strategy, assignment, and isolated evaluation-result tables.
It does not widen `memory_work_acceptances`, work state, staged durable results,
success, outbox, graph, projection, or answer authority. It grants nobody and
adds no route, worker, database client, scheduler, or runtime composition.

## Pre-registered acceptance tests

1. Retrieval and composition definitions, policies, deterministic assignments,
   isolated baseline/candidate results, and exact replay are accepted with
   stable full-coordinate identity.
2. A read-side assignment cannot be used to accept formation, promotion,
   identity, or predicate durable work; rejection occurs before repository
   implementation access.
3. Existing four durable kinds retain byte-identical strategy/assignment ids
   and all durable runner/formation tests remain green.
4. Unknown near-miss work kinds fail strict parsing and cannot enter either
   plane.
5. Migration checks widen exactly the seven strategy/evaluation tables that own
   a `work_kind`; every durable-work table remains on the four-kind vocabulary.
6. Migration bytes are checksummed and contain no grant, role, route, trigger,
   function, graph/product relation, or destructive data rewrite.
7. Serialized assignment/result/export/statistics artifacts still omit raw
   account units, secrets, prompts, queries, answers, evidence, and model output
   where their existing contracts require omission.
8. Focused/full tests, contract QA, import lint, changed-file TypeScript filter,
   migration manifest/static tests, and `git diff --check` pass before recording
   the unit.

## Explicit exclusions

- no retrieval algorithm, query planner, answer composer, answer result schema,
  blind sheet, contamination audit, promotion threshold, or product integration;
- no read-side strategy is selected or run by default;
- no subject/bystander/privacy, identity-authority, compose-voice,
  data-disposition, PostgreSQL runtime/version, or cohort decision.
