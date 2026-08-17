# Content-safe memory evaluation export contract

Status: P5 production-neutral export boundary, 2026-08-11

## Purpose

Export the minimum join coordinates needed by external paired-evaluation and
blind-sheet tooling without exporting copied evidence, model results, queries,
answers, raw source references, account identifiers, or strategy names. This
manifest records experiment structure; it never judges truth or promotes a
strategy.

## Input and grouping

The builder requires an already-issued `memories.experiments.shadow` context
and one or more runtime-verified evaluation pairs. Every pair must belong to the
same owner, account epoch, assignment bundle, evaluation mode/run, input digest,
and frontier digest. Exactly one pair may occupy each repeat/candidate-strategy
coordinate. Duplicates, conflicting results for one pair coordinate, forged
pairs, mixed coordinates, hostile arrays, and cross-authority use fail closed.

## Output

The v1 manifest contains:

- opaque evaluation-run, assignment, and input references;
- pair count, repeat count, and candidate-strategy count;
- one deterministic row per pair with ordinal, repeat ordinal, opaque pair and
  result references, and owner-scoped hashed baseline/candidate strategy refs;
- one canonical export digest.

Rows sort by repeat, candidate strategy, then pair id, so input permutation is
byte-stable. It deliberately omits owner/account, input/result/frontier digests,
strategy ids, response digests, normalized results, copied payload, source ref,
query, answer, label, grade, and statistical verdict.

## Pre-registered acceptance tests

1. Input permutation yields one byte-identical export and explicit repeat joins.
2. Serialized output contains no owner id, raw strategy name, frontier, copied
   result content, or source/result digest.
3. Forged, duplicated, conflicting same-coordinate, mixed-run, empty,
   wrong-capability, and hostile inputs fail before an export is returned.
4. The export performs no grading, contamination classification, McNemar test,
   model call, repository write, filesystem write, or network access.
5. Focused/full tests, contract QA, import lint, changed-file TypeScript filter,
   and `git diff --check` pass before the unit is recorded.

## Explicit exclusions

- no answer or evidence exporter, blind-sheet renderer, grader, labeler,
  statistic, promotion rule, telemetry sink, route, worker, or database adapter;
- no subject/bystander/privacy, identity, compose-voice, data-disposition, or
  production-cohort decision.
