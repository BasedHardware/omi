# Paired memory evaluation statistics contract

Status: P5 preregistration, 2026-08-11; implementation not yet landed

## Question and fixed analysis

For one authority strategy and one candidate strategy, does the candidate
increase externally graded `correct|partly` answers on distinct evaluation
inputs without adding a confidently `wrong` owner answer?

The primary analysis is fixed before labels are imported:

- one distinct copied input is one paired sample;
- repeat ordinal 0 is the sole primary sample for that input;
- `correct` and `partly` are success; `wrong` and `empty` are nonsuccess;
- a primary pair containing `unsure` is excluded and counted explicitly;
- the primary comparison reports discordant candidate-win and authority-win
  counts and the two-sided exact McNemar p-value;
- primary `wrong` counts are reported separately for the authority and candidate;
- repeats 1 and later report within-strategy grade flips against repeat 0 as a
  descriptive read-path noise floor only. Repeats never increase primary N;
- no statistic or threshold automatically promotes a strategy.

The production identity floor remains external and stricter: candidate primary
wrong must be zero on David's blind identity sheet, while the ratified
correct+partly gain must not materially regress.

## Required artifacts

### Unit export

`memory-evaluation-export-v1` remains one owner/epoch/run/assignment/input unit.
Its strategy references must be stable for the same owner epoch, evaluation
role, and exact strategy across assignment bundles; bundle identity must not
fragment a strategy into a new analysis arm.

### Cohort manifest

A deterministic content-safe cohort manifest joins two or more verified unit
exports from one evaluation run. It requires:

- one evaluation mode, run reference, authority strategy reference, and
  candidate strategy reference;
- distinct input references;
- exactly one pair for every declared input/repeat coordinate;
- the same repeat ordinal set on every input, including 0 and at least one
  later repeat;
- opaque unit/input/pair/result/strategy references and counts only;
- a canonical cohort digest.

Multi-candidate experiments are split into one cohort per authority/candidate
comparison so the sample set and missingness are explicit.

### External blind labels

The statistic accepts an exact plain-data label artifact produced outside the
memory runtime. It contains:

- the exact cohort digest;
- a closed grading protocol version;
- opaque grader-session, blind-sheet, and hidden-key digest references;
- exactly one grade for every unique result reference in the cohort;
- only `correct|partly|wrong|empty|unsure` grades.

It contains no question, answer, evidence, owner, strategy name, side name,
note, or free-form grader text. The importer proves structural completeness and
digest binding; it does not claim to prove that a human stayed blind.

## Output

The content-safe report contains cohort/label digests, input/repeat counts,
primary grade counts per arm, included/excluded primary pairs, McNemar
discordants and exact p-value, primary wrong counts, and per-arm self-noise
comparisons/flips/rates. It contains no raw grades by input, owner, question,
answer, evidence, strategy id, promotion decision, or human note.

## Pre-registered acceptance tests

1. Two or more distinct inputs with repeats 0 and 1 produce deterministic
   primary and self-noise counts under input permutation.
2. Adding repeats changes noise counts but cannot change primary N, discordant
   counts, wrong counts, or McNemar p-value.
3. A hand-calculated discordant table matches the two-sided exact McNemar result,
   including zero-discordant and strongly asymmetric cases.
4. `unsure` excludes only its primary pair; `empty` remains a primary
   nonsuccess; all five grades remain visible in arm-level counts.
5. Missing, duplicate, extra, forged, accessor/proxy, mixed-run, mixed-strategy,
   duplicate-input, uneven-repeat, and same-input-coordinate artifacts fail
   before a report is returned.
6. Serialized cohort and report contain none of the planted owner, strategy,
   question, answer, evidence, frontier, source, or free-form note sentinels.
7. The implementation performs no model call, self-grading, label inference,
   repository write, file write, network call, or automatic promotion.
8. Focused/full tests, contract QA, import lint, changed-file TypeScript filter,
   and `git diff --check` pass before the implementation unit is recorded.

## Explicit exclusions

- no blind-sheet answer renderer or grading UI;
- no contamination audit or answer-provenance judgment;
- no confidence interval, multiple-comparison policy, power claim, or promotion
  threshold beyond the fixed descriptive/paired outputs above;
- no production sample loader, route, worker, database adapter, grant, cohort,
  subject/bystander policy, compose-voice default, or identity-authority change.
