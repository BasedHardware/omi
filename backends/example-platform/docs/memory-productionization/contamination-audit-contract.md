# Zero-model memory contamination audit contract

Status: P5 audit kernel landed, 2026-08-11; production provenance adapter remains
preregistered and inactive

## Purpose and inherited definition

Detect one structural read/write contradiction without a model or human truth
grade: an answer assertion addresses the reader in second person while at least
one of its exact grounded citations is supported only by claims the write path
classified `bystander`.

This preserves the inherited `answer-provenance.ts` definition while replacing
its SQLite/log coupling with canonical authorized trace provenance. It is not a
wrong-answer count. Someone else can state something true about the owner, and
a store with no bystander admissions scores zero by construction. The result is
a bounded contamination-class signal, not truth.

## Provenance source boundary

The audit never accepts caller-authored subject labels directly. A sealed
evaluation provenance source receives:

- `memories.experiments.shadow` authority;
- one runtime-verified isolated evaluation result; and
- its strictly reparsed `memory-read-evaluation-result-v1` value.

The source implementation must resolve the finalized producer's exact grounded
trace references against the same authorized projection and return one total row
per grounded reference. Each row contains only the opaque `tr1_` reference and a
sorted unique nonempty set of contributing subject classes. The facade rejects
missing/extra/duplicate references, owner/epoch/result drift, raw text/ids,
unbounded classes, hostile data, and digest drift, then brands and freezes the
manifest.

The first implementation unit defines and tests this sealed port with hermetic
fixtures. It does not claim a production source implementation. Activation
requires wiring inside the exact authorized retrieval/composition producer—where
trace-to-claim correspondence exists. A QA-only copied-artifact compatibility
tool now reproduces the inherited 29.7% whole-answer measurement, but this does
not substitute for fresh assertion-local producer evidence. An adapter that
reconstructs correspondence from answer text or opaque-reference shape is
forbidden.

The exact producer, artifact, atomic staging, revalidation, and legacy-parity
requirements are frozen in
`docs/memory-productionization/query-grounding-provenance-contract.md`.

## Deterministic classification

For each assertion in the sensitive result:

- `second_person` is true only for the bounded ASCII-word forms `you`, `your`,
  `you're`, or `yours`, case-insensitive;
- a cited trace reference is `bystander_only` when its contributing classes
  include `bystander` and include neither `owner` nor `owner_context`;
- the assertion is contaminated only when both conditions hold; and
- the result is contaminated when any assertion is contaminated.

Generic, owner-backed, owner-context-backed, restricted/mixed, and unknown
classes never become bystander-only by inference. No sentence splitting is
needed because the read-result contract already binds exact assertion units.

The content-safe per-result finding contains only result reference/digest,
counts, booleans, and its digest. It contains no query, answer, assertion text,
trace reference, subject class, owner, source, frontier, strategy, role, repeat,
label, or grade.

## Paired report

A report joins complete per-result findings to the existing strict cohort. It
uses each distinct input's repeat ordinal 0 as the sole paired McNemar sample;
later repeats are descriptive contamination self-noise only. It reports
baseline/candidate answer, second-person, and contamination counts across all
declared repeats plus primary both/baseline-only/candidate-only/neither cells and
the same exact rational two-sided McNemar representation used by grade analysis.

The report contains no query, answer, trace, subject class, raw result ID,
strategy ID, owner, source, or truth grade and makes no promotion decision.

## Pre-registered acceptance tests

1. Exact second-person forms over bystander-only support contaminate; owner or
   owner-context support suppresses bystander-only; first/third person,
   generic/restricted/unknown, and no-answer remain clean.
2. Classification is per assertion/citation, not answer-wide: a second-person
   assertion cannot borrow a bystander citation from another assertion.
3. Provenance manifests require every grounded ref exactly once and reject
   missing/extra/duplicate refs, empty/duplicate/unsorted/oversized classes,
   forged results, owner/epoch/result drift, extras, proxies, accessors, and
   sparse/decorated arrays.
4. Finding bytes contain planted counts/booleans but none of planted
   query/answer/trace/class/owner/source/frontier/strategy/role/repeat content.
5. Cohort reports require every result exactly once and reject missing/extra/
   duplicate/forged findings or coordinate drift.
6. Later repeats cannot change primary N or McNemar cells; they only change
   descriptive all-repeat counts/noise.
7. A hand table with 14 candidate-only cleanups and 1 baseline-only cleanup
   reproduces exact two-sided `1 / 2^10 = 0.0009765625`.
8. No model, truth label, blind-sheet write, repository/file/network write,
   route, grant, promotion, subject/privacy behavior, or product default lands.
9. Focused/full tests, contract QA, import lint, changed-file TypeScript filter,
   and `git diff --check` pass before recording the unit.

## Explicit exclusions and activation gate

- no SQLite/log scanner in product code;
- no inference from pronouns to owner identity and no compose-voice change;
- no production provenance-source adapter until the exact read producer exists;
- no claim that a clean finding means a correct answer or correct diarization;
- no real sample, David time, PostgreSQL runtime, credential, deployment, or
  cohort decision;
- copied-artifact zero-model compatibility must continue to reproduce the
  inherited 29.7% figure and paired population; activation additionally
  requires fresh assertion-local results from the authorized producer.
