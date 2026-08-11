# Blind memory-evaluation sheet contract

Status: P5 preregistration, 2026-08-11; implementation not yet landed

## Purpose

Render paired sensitive read results for external truth grading without showing
which answer came from the baseline or candidate. The renderer never grades
truth. It removes work that is structurally machine-judgeable: null answers are
labelled `empty` in the hidden key, and byte-identical nonempty answers for one
input are shown once and later expand back to every exact result reference.

The sheet is an offline evaluation artifact. It never enters product state,
memory authority, a route, or runtime telemetry.

## Inputs and authority

The builder requires:

- `memories.experiments.shadow` authority for the exact owner and account epoch;
- a parsed, opaque evaluation cohort;
- every runtime-verified isolated result named by that cohort, exactly once;
- every normalized result reparsed as `memory-read-evaluation-result-v1`; and
- a private 32-to-128-byte randomization key copied at construction.

Every result ID, input digest, run/mode, role, repeat, and strategy coordinate
must agree with its cohort placement. Baseline and candidate query bytes must
match within one input unit. Missing, extra, duplicate, forged, cross-owner, or
cross-epoch results fail closed.

## Public sheet

The exact public `memory-blind-sheet-v1` contains only:

- version, grading protocol, opaque sheet reference, cohort digest, counts,
  hidden-key digest, and sheet digest;
- one opaque row reference and exact query per input that has a nonempty answer;
  and
- a secret-randomized list of opaque answer references and nonempty answer text.

It contains no owner, account epoch, run, assignment, input, pair, result,
strategy, role, repeat, source, frontier, trace, citation, assertion, grade,
machine-label target, or answer key. Row and answer references are HMAC-derived,
not stable hashes of cohort/result identifiers.

Within one input, exact duplicate nonempty answer bytes across arms/repeats are
rendered once. A unit whose every result is null is absent from human rows. A
mixed empty/nonempty unit shows only its unique nonempty answers. This means the
grader never has to select `empty` for an answer the contract already proves is
null.

## Hidden key

The separate exact `memory-blind-key-v1` contains:

- cohort digest;
- each public answer reference mapped to all exact result references with those
  bytes for that input; and
- all exact null result references with the machine grade `empty`.

Its digest is embedded in the public sheet and later in the external labels
envelope. It contains no query or answer text and is never rendered to the
grader. The randomization key itself is never persisted in either artifact.

The label importer expands one human grade over every result reference in that
answer mapping and appends the exact machine-empty labels. It still requires a
complete one-grade-per-result external labels envelope before paired statistics
run. No correctness, partly, wrong, or unsure grade is inferred by code.

## Pre-registered acceptance tests

1. Two arms with distinct nonempty answers render in secret-randomized order;
   changing the key changes at least one tested order/reference while identical
   inputs and key are byte-stable.
2. Same-input duplicate nonempty answers across arms/repeats render once and the
   hidden mapping expands to every exact result reference.
3. Null answers never render: a mixed unit exposes one nonempty target and an
   all-null unit exposes no row; the hidden key labels every null result `empty`.
4. Public serialized bytes contain planted query/answer text but none of the
   planted owner/run/input/pair/result/strategy/source/frontier/trace/citation
   sentinels or the words baseline/candidate.
5. Hidden serialized bytes contain result references but no query, answer,
   strategy, source, frontier, trace, citation, owner, role, or repeat.
6. Missing/extra/duplicate/forged results, query mismatch, normalized-result
   role/repeat/strategy/input mismatch, wrong capability/owner/epoch, unsafe
   key, extras, accessors, proxies, sparse/decorated arrays, and digest tampering
   fail closed.
7. Public sheet and hidden key round-trip through strict parsers; labels expand
   only after exact sheet/key digest validation and produce one grade per cohort
   result with no strategy field.
8. No model, truth grading, repository/file/network write, UI, route, grant,
   promotion, subject/privacy change, or product default is introduced.
9. Focused/full tests, contract QA, import lint, changed-file TypeScript filter,
   and `git diff --check` pass before recording the unit.

## Explicit exclusions

- no grading web app, authentication session, grader identity, or live link;
- no contamination audit or promotion decision;
- no production result loader or PostgreSQL runtime activation;
- no bystander, `subject:*`, identity, compose-voice, data-disposition, model,
  deployment, or cohort-default decision.
