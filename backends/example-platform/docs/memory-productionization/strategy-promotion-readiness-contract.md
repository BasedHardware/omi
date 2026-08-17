# Memory strategy promotion-readiness contract

Status: pre-registered, inactive P5 decision-support boundary.
Version: `memory-strategy-promotion-readiness-v2` (2026-08-13).
V1 is historical evidence only.

Governing decisions: `backend:ADR-015` and
`DAVID-IDENTITY-EXPRESSION-FLOOR-DECISION.md`.

## Purpose

This unit answers one narrow question: has a baseline/candidate comparison met
the identity-expression floor strongly enough to be queued for David's strategy
review? It never promotes a strategy, changes a default, accepts durable work,
selects a cohort, touches a route, or claims production readiness.

Truth about answers and identity expression remains external blind human input.
The program may verify the sheet/key/label joins and compute paired statistics;
it never invents or self-grades a truth label.

## Required evidence

One readiness evaluation consumes two complete paired/repeated cohorts over the
same exact baseline and candidate strategies:

1. `regression`: the frozen 25-question owner-memory floor; and
2. `generalization`: at least 10 distinct, harder inputs not present in the
   regression cohort. This cohort must include identity-bearing cases
   (self-introduction conflicts, multi-speaker speech, documents), not only
   usefulness puzzles.

Each cohort must have at least two repeats, a complete usefulness-grade
artifact, a complete identity-expression artifact, and a verified
assertion-local contamination report over the same cohort. Regression and
generalization cohort, usefulness-label, identity-expression, sheet,
hidden-key, statistics, and contamination digests must be distinct. Input refs
must be disjoint. Strategy refs must agree exactly across both cohorts.

Identity-expression classes are:

- `certain_owner_match`
- `certain_owner_mismatch`
- `qualified`
- `source_local`
- `abstain`

## Frozen v2 gates

Every identity/structural gate is conjunctive and determines
`blocked` vs `ready_for_david_review`:

- regression has exactly 25 distinct inputs; generalization has at least 10;
- candidate primary `certain_owner_mismatch` is zero in both cohorts;
- candidate-only contamination does not exceed baseline-only contamination in
  either cohort; and
- candidate total contamination does not exceed baseline total contamination
  in either cohort.

Usefulness grades (`correct`, `partly`, `wrong`, `empty`, `unsure`) and
McNemar 14-1 / p≤0.05 are **reported in the packet and do not block**.
Abstention, qualification, and source-local wording are identity successes.
A generic usefulness `wrong` is not an identity-floor failure.

Repeats measure read-side self-noise and remain present in the decision packet,
but repeat observations never inflate primary N or significance.

## Output and authority

The result is exact, content-safe, detached, and deeply frozen. It contains
only version, `blocked` or `ready_for_david_review`, strategy/cohort/report
digests, fixed gate codes with booleans, primary usefulness and identity
counts, repeat/noise counts, and its own digest. It contains no owner, input,
question, answer, grade row, evidence, citation, sheet row, model text, human
note, or free-form reason.

`ready_for_david_review` is not an authority coordinate and cannot be consumed
by strategy assignment, durable work, product projection, route composition,
or deployment. David still decides strategy/default promotion and whether a
quieter usefulness trade is acceptable. Subject tiers, bystander privacy,
compose voice, data disposition, and first-cohort activation remain separately
gated.

## Acceptance tests

1. Identity-safe evidence with the inherited 14-1/25 usefulness shape plus a
   passing disjoint harder cohort yields `ready_for_david_review`.
2. Any candidate primary `certain_owner_mismatch` blocks even when McNemar
   significance and total success improve.
3. A usefulness `wrong` that used `source_local` or `abstain` wording does not
   block.
4. A usefulness `unsure` row does not block.
5. Added repeats change only noise evidence, never primary counts or p-value.
6. Same input in both cohorts, strategy drift, digest mismatch, incomplete
   usefulness or identity labels, forged contamination, or cross-cohort
   artifacts fail closed.
7. Inputs with proxies, accessors, classes, extras, sparse/decorated arrays,
   hostile text, non-finite numbers, or impossible counts are rejected without
   executing attacker code.
8. Serialized output contains no content or owner coordinate and has no method
   that mutates assignment, work, graph, product state, route, or deployment.

## Exclusions

- no new blind sheet or request for grading;
- no automatic promotion or product default;
- no production cohort, deployment, database adapter, route, grant, or worker;
- no return to the v1 zero-wrong / no-unsure identity floor; and
- no change to bystander, subject-tier, or compose-voice behavior.
