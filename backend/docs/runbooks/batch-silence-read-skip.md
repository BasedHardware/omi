# Silent-unit read reduction (R9, SCA-1757)

Prepared 2026-11-12. Activation belongs to the deploy lane and owner. This change
has not activated production or established the issue’s production acceptance checks.

`BATCH_PIPELINE_SILENCE_READ_SKIP_ENABLED` defaults **on**. Set `false`, `off`, or
`0` to restore the full processing path for subsequent silent projections. Existing
ready receipts remain valid on rollback. There is no storage format migration.
Production source explicitly holds the switch `false` on backend, backend-sync,
backend-sync-backfill and backend-integration. These Cloud Run hosts evaluate it
in `Projector._assign` and `Projector.complete_content`, through the shared
`serving_for_stage` composition and reconcile/metrics routes or serving loop.
The listen overlay and chart also hold it `false` defensively: the legacy image
mounts the shared routes, although its serving loop is disabled and its worker
auth settings are empty. The dedicated GPU worker runs `diarizer.batch_pipeline_runtime`
with a pump that commits results and requests CPU-side work; it does not construct
`Projector` or evaluate this switch. Its chart needs no flag declaration.
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

## Reads skipped and kept (anatomy numbering)

| Reads | Treatment |
| --- | --- |
| A1–A9, B1–B8 | Kept: admission, custody and lease authorization occur before classification. |
| C1–C5 | Kept: worker completion/result registration, privacy fencing and artifact custody/expiry. |
| D1–D3 | Kept: discovery and fetch hints continue to locate the ordered result. |
| D4/D5 redundant pre-check | Skipped for ordinary silent units: assignment immediately rechecks the same session rows, privacy authority and predecessor in its authorizing transaction. |
| D4/D5 follow-up `ready()` transaction | Skipped: assignment already wrote the zero-output receipt as ready. |
| D7 completion sibling rows | Kept in the completion transaction; the current unit reuses its session snapshots. |
| D8 accounting prepare | Skipped only after every sibling is transactionally verified as silent and ready; zero usage needs no plan/hourly attribution reads. The zero-usage ledger stamp and existing post-commit observers stay. |
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

A strict read-before-write document fake exercises the real assignment, follow-up
and completion functions for a two-silent-unit upload. Re-measured after the
2026-11-14 integration with allowance observers: **89 → 40 document lookups**
(**55.1% fewer**) before publication/retention, using no warm cache. The original
2026-11-12 measurement was 84 → 35 (58.3% fewer). These are local path budgets,
**not** the acceptance test’s whole-family billed-read ratio. Coalesced-original
receipt reads, retention, publication and observers must remain included in the
qualified production attribution where applicable.

## Deployment and verification handoff

1. Once the image serves, the release owner hand-enables
   `BATCH_PIPELINE_SILENCE_READ_SKIP_ENABLED=true` only on backend-integration.
   Require one clean hour: `omi_firestore_billed_reads_by_caller_total` for
   `database.batch_pipeline_projection_session:prepare`,
   `database.batch_pipeline_privacy:read`,
   `database.batch_pipeline_projection:prepare_accounting` and
   `database.batch_pipeline_projection:commit` per silent unit must fall;
   completed audio-hours must stay at least 70% of the prior hour; no new
   custody or T2 alarm. Record matched windows and qualified silent-only
   attribution; these caller counters have no outcome dimension by themselves.
2. The margin-40 lead expands all roles to `true` in repo config after that
   clean hour. Complete the expansion or revert by **2026-11-18T20:00Z**.
   Rollback value: `false` on every affected role, including the listen hold.
3. Record serving image/revision identity, retention/erasure and speech-latency
   evidence. At D+2 record settled Firestore charges, including simultaneous
   changes and traffic. No production savings are claimed by this PR.

Owner log: prepared flag `BATCH_PIPELINE_SILENCE_READ_SKIP_ENABLED`; rollback is
`false`. Production activation, matched-hour attribution, serving-revision proof
and D+2 bill effect are pending with deploy/verify, not executed by this worker.
