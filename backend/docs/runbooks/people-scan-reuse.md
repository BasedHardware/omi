# People scan reuse: corrected sites and fresh ramp

The earlier WQ20 slice was graded FALSIFIED. This change wires the actual
`find_person_by_name` miss fallback and sync `speaker_identity` context reads.
Known spellings keeps its existing opt-in. `vocabulary._sources` stays live.
Raw rows alone may be reused within one explicit sync attempt; learning and
entitlement/privacy projections execute on every call. Mutation and authority
reads invalidate snapshots. Every hit checks the atomic writer generation.

Missing, malformed or unavailable generation heads never admit cached rows.
They use fresh People scans and avoid repeated paid head probes until the next
invalidation/attempt. This adds no head writes or account mutation.

## Writer enumeration repeated 2026-11-02

Re-grepped `origin/main` for direct People references and generation helpers
before changing callers. These writers already increment the generation in
the same transaction/batch as the People mutation:

| Owner | Writers covered |
| --- | --- |
| `users`, `people_generation` | create/delete/update via `write_person`; transactional profile, alias and sample changes |
| `person_aliases`, `people` | rename/dismiss and pin |
| `person_speech_samples`, `speaker_learning` | sample and learning updates |
| `speaker_learning_jobs`, `speaker_auto_enroll` | job completion and enrollment |
| `speaker_assignment_effects` | assignment effects |
| `review_changes`, `chat_edits` | apply and restore |
| `_client` | recursive People deletion batches; account purge deletes generation last |
| `utils/person_evidence_backfill` | evidence repair |

Meeting context, dream prescan and dream seed references are readers. The
emulator script's writes are synthetic test setup. The pinned AST inventory
detects new/changed People-reference or generation-helper scopes; it does not
by itself prove transaction atomicity. Re-audit before `--write`, then run the
strict writer unit tests and loopback emulator contract. A changed writer
without a generation bump invalidates the inventory test.

## Recurring-voice scope audit 2026-11-04

`recurring_voices.checkpoint`, `learn` and `learn.commit` read the People
generation and current person prints; they only write recurring profiles, the
owner's profile index and conversation evidence metadata. They do not mutate
People and need no generation increment. A People mutation during inference
changes the generation and refuses recurring publication.

`speaker_assignment_effects.persist_assignment_effects` still increments the
generation alongside every People update in the same transaction. Its new
recurring-profile writes run after all reads and do not replace that increment.
`speaker_auto_enroll.publish` and its `commit` likewise retain the atomic People
update plus generation increment; recurring binding shares that transaction.
`speaker_auto_enroll.update_privacy`, `retract_conversation`, `revoke_person`
and their transaction bodies keep one increment for each People mutation;
their new account-deletion fences and recurring cleanup add no unfenced writer.
The inventory pins the reviewed bodies, with strict transaction tests and
loopback binding/publication proofs that assert the generation increments.

## Transcript-pointer scope audit 2026-11-07

C2 changes nine pinned scopes in `review_changes`, `speaker_auto_enroll`,
`speaker_learning_jobs`, `users` and `utils/person_evidence_backfill`. The changes
add transcript preloading or narrow unavailable-content refusals. Re-audit found
identical generation-helper and document-write calls before and after the change;
the existing transaction still commits each People mutation and generation bump
together. No new People writer or generation helper was added or removed.

Regenerate the AST inventory with the backend Python 3.11 environment. The strict
writer and inventory suites passed 17 tests, and
`scripts/fsr_people_generation_emulator_test.py` passed 31 checks on an owned
loopback emulator, including review apply/undo/redo, enrollment, evidence backfill,
rollback and concurrent increments. The emulator was stopped after verification.

## Measure before enabling

`people_scan_dedupe` remains **0**. The closed-label counter
`omi_people_scan_dedupe_total{site,outcome}` observes `first` and `repeat` keys
while dark without generation reads. Sites are `known_spellings`,
`name_fallback`, `sync_context`, `other`. On an enabled cohort it also records
`scan`, `hit`, `guard_unavailable`. No identities or input text enter labels.

Production repeat rate is **not measured yet**. The five-call synthetic name
fallback fixture measures four repeats (80%) and one scan; this is correctness
evidence, not production savings. Report the dark production ratio
`repeat/(first+repeat)` by site over a full lookback after deployment. It is an
eligibility upper bound; invalidations, absent heads and generation reads
reduce actual savings. The $4-8/day estimate remains unbooked.

Before any ramp, infracost must add `people_generation:read_people_generation`
to this lever's caller origin needles alongside `person_aliases:list_people`.
The current single caller needle omits paid head reads and cannot grade net
savings. Re-pin this item's own absolute pre-ramp reads/day baseline after the
new code and dark telemetry are serving; do not reuse the FALSIFIED baseline.
Then use a separate config PR for 5%, require two `verify.py` ticks PASS, then
100% only with lower absolute reads/day and clean 5xx/latency guards. Infracost
owns expansion and the first decision within three days of deploy. Rollback:
set the lever to 0. The read-loop grading change is owned by infracost; this PR
does not edit its in-flight verifier work.
