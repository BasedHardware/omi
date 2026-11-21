# Silent-unit read reduction (R9, SCA-1757)

Prepared 2026-11-12. Integration canary 2026-11-21T13:20:14Z (`backend-integration-sca1824-on`,
SCA-1824): one clean hour, target-caller reads −13.5% against the 11-20 control hours
(19.98M→17.36M/h), guard clean. The expansion to every role is #25959 (2026-11-21).

`BATCH_PIPELINE_SILENCE_READ_SKIP_ENABLED` defaults **on**. Set `false`, `off`, or
`0` to restore the full processing path for subsequent silent projections. Existing
ready receipts remain valid on rollback. There is no storage format migration.
Production source sets the switch `true` on backend, backend-sync,
backend-sync-backfill and backend-integration (and backend-projection-pump, which
derives from integration). These Cloud Run hosts evaluate it
in `Projector._assign` and `Projector.complete_content`, through the shared
`serving_for_stage` composition and reconcile/metrics routes or serving loop.
The listen overlay and chart set it `true` too, matching the other roles: the legacy image
mounts the shared routes, although its serving loop is disabled and its worker
auth settings are empty. The dedicated GPU worker runs `diarizer.batch_pipeline_runtime`
with a pump that commits results and requests CPU-side work; it does not construct
`Projector` or evaluate this switch. Its chart needs no flag declaration.
The operator cohost `scripts/batch_pipeline_projection_repair.py` also constructs
`Projector`. For `--stage prod` it forces this process's switch to `false`, even
when the shell inherited `true`. Only the explicit `--enable-silence-read-skip`
CLI flag opts that invocation in. Omit that option on every prod repair during
the hold or rollback; an environment value alone cannot enable it. Local repair
keeps the normal environment/default behavior. Existing identity, dry-run,
plan-SHA approval and apply requirements remain. No repair is authorized here.
No production configuration or deployment is changed by this source-only PR.

## Receipt and fences

The worker still classifies, stores its encrypted result and commits its ordered
result log exactly as before. For an ordinary `outcome=silence` upload, assignment
writes the existing projection receipt directly as `ready`, with no output IDs,
zero speech seconds, and no audio/enrichment follow-up. It retains the immutable
job/result binding, processed-segment ledger checkpoint, owner watermark,
predecessor ordering and privacy generation checks in the assignment transaction.
It does not mark silence as supersession or weaken T2’s terminal accounting.

All-silent upload completion verifies every bound job/result/ready receipt in one
transaction before completing the content ledger and writing the existing zero
usage stamp. It refuses mixed speech, erased results, output IDs, dispositions,
multipart receipts, partial ledgers and prior speech charges; those use the normal
completion path. The completing unit’s snapshots are reused only inside that same
transaction. Every sibling still enrolls its job/result in the conflict set.

When an upload has coalesced original receipts, their existing identity reads and
atomic completion fan-out remain. Original receipt expiry is not extended on
replay. The post-commit allowance settlement and transcription observers also
remain: silent completion supplies zero speech and the billing generation from
the authorizing transaction. A replay uses the stored billing generation for
settlement and does not emit another transcription advance. Observer failures
retain their existing handling; no observer or T2 threshold is disabled.

Record-origin/native-record units retain their ordinary path: even silence may
need to replace live-preview text in a conversation. Empty ASR and
`no_recoverable_speech` retain their existing paths and evidence requirements.
Mixed uploads retain ordinary speech accounting; their silent siblings can still
skip the redundant assignment pre-check and follow-up transaction.
Before a silent completing unit tries zero-speech completion, it reads the result
rows that ordinary accounting would need. Known-mixed uploads go directly to
ordinary accounting and reuse those snapshots, without a speculative transaction
or duplicate result reads. All-silent candidates retain one classification read
per sibling (`database.batch_pipeline_projection:completion_entries`). That scan
is a hint only; the completion transaction still verifies every bound sibling.
There is no persistent mixed-outcome marker or process cache to invalidate.

## Reads skipped and kept (anatomy numbering)

| Reads | Treatment |
| --- | --- |
| A1–A9, B1–B8 | Kept: admission, custody and lease authorization occur before classification. |
| C1–C5 | Kept: worker completion/result registration, privacy fencing and artifact custody/expiry. |
| D1–D3 | Kept: discovery and fetch hints continue to locate the ordered result. |
| D4/D5 redundant pre-check | Skipped for ordinary silent units: assignment immediately rechecks the same session rows, privacy authority and predecessor in its authorizing transaction. |
| D4/D5 follow-up `ready()` transaction | Skipped: assignment already wrote the zero-output receipt as ready. |
| D7 completion sibling rows | Kept in the completion transaction; the current unit reuses its session snapshots. |
| D8 accounting prepare | Full preparation is skipped for transactionally verified silence; one result classification read per sibling remains. Mixed uploads reuse those reads in ordinary accounting. The zero-usage stamp and post-commit observers stay. |
| D9 visible/redirect walks | Skipped for verified all-silent completion; no output IDs exist. |
| D10 additional completion guard | Skipped only for verified all-silent completion; session preparation already performed the live owner/generation/source fence in the same transaction, and no visible IDs are published. |
| Retention and publication acknowledgement | Kept unchanged, including their reads and fences. |
| E1–E6 | Kept: no sweeper or alarm thresholds change. |

No artifact is deleted here. `retention.py`, artifact expiry intervals, archival
storage, erasure and GCS lifecycle policies are unchanged. Publication failure
leaves completion retryable, without arming cleanup before the ordinary publication
step. The existing retention path arms the same cleanup intervals afterward.
A false silent classification keeps `audio_uri` and its generation, capture clock,
source references and original worker result. During the existing retention window,
a reviewed reprocessing request can read those bytes through the ordinary
privacy-authorized artifact loader and submit a new intake/content identity using
the original capture identity. After staging expiry, recovery must use the existing
retained source archive if available; this change does not promise longer retention
or automatically replay a completed silent job. User erasure still takes precedence.

## Re-measured baseline

Read-only GMP query at `2026-11-12T09:00:00Z`; UTC window
`2026-11-11T09:00:00Z` through `2026-11-12T09:00:00Z` (24 hours). Exact anatomy queries:

```promql
sum by (caller) (increase(omi_firestore_billed_reads_by_caller_total{caller=~"database.batch_pipeline_.*|utils.batch_pipeline..*|database.lifecycle_metrics_queries:.*"}[24h]))
sum by (outcome) (increase(omi_batch_pipeline_unit_diarization_outcome_total[24h]))
```

Summing the returned caller series gives **1,043,558,176.69** batch-family reads.
Outcome counts (PromQL increases are extrapolated) are **565,258.12 diarized** and
**378,069.70 silence**, totaling **943,327.82** true units: **40.08%** silent and
**1,106.25** family reads per true unit. Allocating reads proportionally gives
418.24M reads/day, $225.85/day at $0.54/M; that is an **estimate**, not observed
silent-unit attribution or a forecast of savings. Pre-classification and fixed
poll reads cannot be removed by this projection change.

The anatomy’s by-caller series has no outcome dimension. Dividing all family reads
by silent outcomes is not a valid silent-unit numerator. A matched-hour production
claim needs isolated silent-unit tracing/billed-read attribution, or an independently
qualified attribution measurement, in addition to the above family totals. This
PR does not add a high-cardinality unit label or claim that this gap is solved.

## Corrected local sizing (second review)

The narrow cold strict-fake boundary (assignment, readiness, completion and its
observers, before publication/retention) now measures **50 → 23** lookups for one
ordinary silent unit. The earlier 50 → 22 receipt predates the classification
scan; the historical two-unit 89 → 40 number used a different boundary.

The real loopback Firestore emulator also runs the whole projection of a synthetic
two-unit, 30-second-per-unit upload, with four speech seconds on its speech unit,
`FIRESTORE_READ_LEVERS={}`, no provider calls and no injected contention. The
existing `omi_firestore_billed_reads_by_caller_total` probe counts lookups,
returned query documents and empty-query floors. Admission and GPU/worker work
are outside the measurement; result discovery by `project()`, assignment,
readiness, accounting, completion, observers, publication and retention remain.

| Upload | Upload reads off → on | Reads/unit (upload ÷ 2) off → on | Completing unit off → on |
| --- | --- | --- | --- |
| All silent | 161 → 114 | 80.5 → 57 | 104 → 75 |
| Mixed, completing on silence | 198 → 180 | 99 → 90 | 107 → 89 |
| Mixed, completing on speech | 198 → 180 | 99 → 90 | 141 → 141 |

Completing-unit replay is 67 → 58, 70 → 70 and 72 → 72 respectively. Both mixed
cases make zero speculative zero-speech completion attempts, including replay.
These are deterministic synthetic code-path counts, not production billing or
a forecast at the production upload-size/mix distribution. The probe does not
model extra index-entry charges. Include the new `completion_entries` caller in
any net-read canary numerator; a fall in the old labels alone is insufficient.

## Integration acceptance and coverage

At reviewed head `4782fd28e0`, the unmodified pagination integration test failed
against the emulator at line 231: status was `completed`, not `processing`.
Silent assignment now writes ready, so the first follow-up page can complete all
siblings. The test explicitly covers both true (new transition) and false (old
persisted boundary), retaining restart, ordering, no-load/no-enrichment and
publication replay assertions.

Hosted CI was green because this suite was **not selected**, not because its
assertion passed or was skipped. The unit selector excludes integration roots.
The successful [emulator job](https://github.com/BasedHardware/omi/actions/runs/43966715147/job/133647961938)
also omitted this file from its named proof list and log. The existing
`run-emulator-proofs.sh` now includes the follow-up and sizing suites. No workflow
is changed. The broader native-record suite has nine protocol-cutover failures
also reproduced unchanged on clean main `c63c9c8d17d2`; these are documented in
the PR rather than altering their assertions or enabling the protocol in tests. The optional slow heavy-owner simulation also
passes its assertions but exceeds the unchanged 1s CPU guard on both the branch
and clean main; no timing allowance is changed.

## Deployment and verification handoff

1. Once the image serves, the release owner hand-enables
   `BATCH_PIPELINE_SILENCE_READ_SKIP_ENABLED=true` only on backend-integration.
   Require one clean hour: `omi_firestore_billed_reads_by_caller_total` for
   `database.batch_pipeline_projection_session:prepare`,
   `database.batch_pipeline_privacy:read`,
   `database.batch_pipeline_projection:prepare_accounting` and
   `database.batch_pipeline_projection:commit` per silent unit must fall;
   completed audio-hours must stay at least 70% of the prior hour; no new
   custody or T2 alarm. Include `completion_entries` reads in the net numerator.
   Record matched windows and qualified silent-only
   attribution; these caller counters have no outcome dimension by themselves.
2. The margin-40 lead expands all roles to `true` in repo config after that
   clean hour. Done: canary clean hour ended 2026-11-21T14:20:14Z (READBACK on
   SCA-1824); expansion PR #25959. The original 2026-11-18T20:00Z deadline slipped
   because the canary started late (SCA-3495 rollback).
   Rollback value: `false` on every affected role, including the listen hold and the
   projection pump; the integration-only rollback revision is
   `backend-integration-a1a8b2d-44889281317-1`.
3. Record serving image/revision identity, retention/erasure and speech-latency
   evidence. At D+2 record settled Firestore charges, including simultaneous
   changes and traffic. No production savings are claimed by this PR.

Owner log: prepared flag `BATCH_PIPELINE_SILENCE_READ_SKIP_ENABLED`; rollback is
`false`. Integration canary and matched-hour attribution done 2026-11-21 (SCA-1824).
The all-roles serving proof, all-roles READBACK and D+2 bill effect are pending after #25959 serves.
