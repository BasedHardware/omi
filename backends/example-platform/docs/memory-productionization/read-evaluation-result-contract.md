# Sensitive memory read-evaluation result contract

Status: P5 preregistration, 2026-08-11; implementation not yet landed

## Purpose

Represent one retrieval/composition answer in the physically isolated
evaluation-result plane so blind sheets and zero-model contamination audits can
be built later. The opaque evaluation export remains content-free, and this
result never enters the product answer, graph, projection, or durable-work path.

## Input authority and identity

The builder requires:

- a runtime-verified copied evaluation input minted under
  `memories.experiments.shadow`;
- an exact `retrieval` or `composition` registered strategy;
- evaluation role and repeat ordinal supplied by the existing replay
  coordinator;
- the exact query text; and
- a finalized content-safe recall trace constructed by the canonical recall
  integrity boundary.

The result binds the copied input digest, a digest of its input frontier, the
strategy execution-contract digest, role, repeat, query, answer/absence,
assertion/citation manifest, and trace. A caller cannot relabel a formation or
other durable strategy as a read result.

## Answer and grounding shape

The v1 sensitive result is one exact bounded plain-data object:

- version, copied-input digest, input-frontier digest, strategy kind/id/digest,
  role, and repeat ordinal;
- bounded query text;
- either an answer or a qualified no-answer;
- the finalized `recall-trace-v1` value; and
- zero or more ordered assertions with bounded text and nonempty unique sorted
  `tr1_` citations.

For an answer:

- trace outcome is `grounded`;
- assertions are nonempty;
- every assertion citation is in both the trace's cited and grounded stages;
- every grounded trace reference is used by at least one assertion; and
- `answer_text` is byte-exactly the assertion texts joined by one ASCII space.
  No unmanifested prose is allowed.

For no answer:

- `answer_text` is null, assertions are empty, and absence is exactly
  `query_gap`;
- trace outcome is not `grounded` and has no grounded references.

The result contains no evidence excerpts, raw evidence/claim/entity ids, source
references, tool arguments, free-form error/reason/note, owner id, assignment
bucket, or grader label. Query and answer are intentionally sensitive and may
exist only in the isolated result store under the experiment capability.

## Replay and export

The canonical result digest uses the existing isolated evaluation stage. Same
input/strategy/role/repeat/result bytes replay; changed answer, trace, assertion,
or citation bytes conflict under the existing exact coordinate.

The content-safe export continues to emit only opaque result references and
counts. A later offline blind-sheet renderer may load these sensitive results,
randomize arms, and reveal query/answer to David without revealing strategy;
that renderer is not part of this unit.

## Pre-registered acceptance tests

1. Grounded answer with two assertions round-trips as a deeply frozen bounded
   result and its canonical digest changes with every identity/content field.
2. Unmanifested answer prose, empty assertion text/citations, citation outside
   cited or grounded stages, unused grounded refs, duplicate/unsorted refs, and
   grounded/no-answer contradictions fail closed.
3. Qualified no-answer accepts only null answer + empty assertions +
   `query_gap` + non-grounded trace.
4. Formation/promotion/identity/predicate strategies, forged copied inputs,
   forged traces, wrong owner/epoch context, invalid roles/repeats, accessors,
   proxies, sparse/decorated arrays, control-only/oversized query or answer,
   and extra fields fail before a result is returned.
5. Serialized result contains planted query/answer (proving the sensitivity
   test is meaningful) but none of the planted raw evidence/source/tool/error/
   owner sentinels.
6. The opaque evaluation export for a staged read result contains none of its
   query, answer, assertion, or trace fields.
7. No model, inference, grading, contamination decision, repository write,
   file write, network call, route, promotion, or product default is introduced.
8. Focused/full tests, contract QA, import lint, changed-file TypeScript filter,
   and `git diff --check` pass before recording the unit.

## Explicit exclusions

- no read producer, query planner, composer, entailment model, source adapter,
  blind-sheet renderer, grading UI, contamination auditor, or promotion rule;
- no schema migration: the existing isolated normalized-result JSON envelope
  already stores versioned bounded result contracts;
- no subject/bystander/privacy, identity authority, compose-voice default,
  PostgreSQL runtime/version, production credential, deployment, or cohort
  decision.
