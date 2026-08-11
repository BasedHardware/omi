# Memory strategy promotion-readiness contract

Status: pre-registered, inactive P5 decision-support boundary.

## Purpose

This unit answers one narrow question: has a baseline/candidate comparison met
the already-ratified machine and blind-human evidence floor strongly enough to
be queued for David's strategy review? It never promotes a strategy, changes a
default, accepts durable work, selects a cohort, touches a route, or claims
production readiness.

Truth about answers remains external blind human input. The program may verify
the sheet/key/label joins and compute paired statistics; it never invents or
self-grades a truth label.

## Required evidence

One readiness evaluation consumes two complete paired/repeated cohorts over the
same exact baseline and candidate strategies:

1. `regression`: the frozen 25-question owner-memory floor; and
2. `generalization`: at least 10 distinct, harder inputs not present in the
   regression cohort, such as entity dossiers, multihop questions, or temporal
   change questions.

Each cohort must have at least two repeats, a complete blind label artifact,
and a verified assertion-local contamination report over the same cohort.
Regression and generalization cohort, label, sheet, hidden-key, statistics, and
contamination digests must be distinct. Input refs must be disjoint. Strategy
refs must agree exactly across both cohorts.

## Frozen v1 gates

Every gate is conjunctive:

- regression has exactly 25 distinct inputs; generalization has at least 10;
- no primary pair is excluded as `unsure` in either cohort;
- candidate primary `wrong` is zero in both cohorts;
- candidate correct-plus-partly is at least baseline correct-plus-partly in
  both cohorts;
- on regression, candidate wins are at least 14, baseline wins are at most 1,
  and exact two-sided McNemar p is at most 0.05;
- on generalization, candidate wins are at least baseline wins;
- candidate-only contamination does not exceed baseline-only contamination in
  either cohort; and
- candidate total contamination does not exceed baseline total contamination
  in either cohort.

Repeats measure read-side self-noise and remain present in the decision packet,
but repeat observations never inflate primary N or significance. V1 does not
pretend the measured 20-36% read-side noise floor is zero and does not use an
unpaired difference.

## Output and authority

The result is exact, content-safe, detached, and deeply frozen. It contains
only version, `blocked` or `ready_for_david_review`, strategy/cohort/report
digests, fixed gate codes with booleans, primary counts, repeat/noise counts,
and its own digest. It contains no owner, input, question, answer, grade row,
evidence, citation, sheet row, model text, human note, or free-form reason.

`ready_for_david_review` is not an authority coordinate and cannot be consumed
by strategy assignment, durable work, product projection, route composition,
or deployment. David still decides strategy/default promotion. Subject tiers,
bystander privacy, compose voice, data disposition, and first-cohort activation
remain separately gated.

## Acceptance tests

1. The inherited 14-1/25 regression shape plus a passing disjoint harder cohort
   yields `ready_for_david_review`; changing any single gate yields `blocked`.
2. Any candidate wrong answer blocks even when McNemar significance and total
   success improve.
3. Unsure rows block rather than disappearing from N.
4. Added repeats change only noise evidence, never primary counts or p-value.
5. Same input in both cohorts, strategy drift, digest mismatch, incomplete
   labels, forged contamination, or cross-cohort artifacts fail closed.
6. Inputs with proxies, accessors, classes, extras, sparse/decorated arrays,
   hostile text, non-finite numbers, or impossible counts are rejected without
   executing attacker code.
7. Serialized output contains no content or owner coordinate and has no method
   that mutates assignment, work, graph, product state, route, or deployment.

## Exclusions

- no new blind sheet or request for grading;
- no automatic promotion or product default;
- no production cohort, deployment, database adapter, route, grant, or worker;
- no relaxation of the exact zero-wrong identity floor; and
- no change to bystander, subject-tier, or compose-voice behavior.
