# Batch record lane contract

Status: ratified promises as of 2026-10-25 (ramp at 5%, PERCENT=0 after the
10:39Z T2 rollback). Review by 2026-11-01 or at the 100% step, whichever is
first. Rulings behind each promise are in [`docs/adr/`](../../docs/adr/README.md);
a promise with no ADR is not durable ([ADR 0005](../../docs/adr/0005-rulings-live-in-adrs.md)).
Package map: [README.md](README.md). Design: [batch-pipeline-worker.md](../../docs/batch-pipeline-worker.md).

The record lane turns an accepted upload into the conversation's transcript of
record. Live transcription is a preview; the batch result is the record.

## Promises

| Promise | What is guaranteed | Enforced by (code) | Trip |
| --- | --- | --- | --- |
| **Custody** | An accepted input object is never lost. Original bytes are archived before any 202 (`routers/sync.py:sync_local_files_v2`); every source reference is owner/conversation scoped and pinned to one GCS generation (`source_audio.py:validate_reference`, `read_reference` reads with `if_generation_match`). An ambiguous admission reply keeps the staging outbox and returns 503 (`intake.py:accept_upload`); it never releases a legacy twin. A quarantined unit keeps its encrypted artifacts with no TTL until recovery (`retry_policy.py:quarantine_job`). | `intake.py`, `source_audio.py`, `artifacts.py`, `retention.py` | T1, T2 |
| **Latency** | Soft bound, not a hard SLA ([ADR 0001](../../docs/adr/0001-trip-floors-t2-t3-t5.md)): an obligation over 900s or a job over 1,800s is a freeze through 50%. Hard backstops roll back: record latency p95 over 30 min for 30 min; any admitted unit 2h without a terminal state; wedged units over 5% of admitted for 30 min (at least 20 admitted). Audio waits in custody; latency trouble is never loss. | `scheduler.py:Scheduler` (120s token-fenced leases, `owns_lease`), `merge.py:OrderedMerge`, `pump.py` | T3 |
| **Transcript route** | No unit in an unsupported language is decoded on Parakeet; every completed unit carries route proof. | `utils/stt/batch_language.py:resolve_language`, `select_decision`; route receipts via `language_metrics.py:record_route` (intake, `diarizer/batch_pipeline.py` worker) | T4 |
| **Speaker naming** | Through 5–25%: #23581 links/names retained-audio batch groups. David approved temporary sync-off centroids in [ADR 0004](../../docs/adr/0004-sync-off-speaker-centroids.md) at ~14:45Z on 2026-10-25; delivery is the separately reviewed qualfix2 PR. Product owner ruling 2026-10-25 ~09:40Z (option A): keep ramping and fix naming in parallel, so naming quality is **not** a trip. FP32 flight batching needs a one-time speakers-per-unit parity check (±5%). | `projection.py:Projector`, `utils/conversations/speaker_resolution.py` | none (watch) |

## Inputs and outputs

- **Job document** (`database/batch_pipeline_*.py`, shape in `contracts.py:WorkItem`):
  immutable `segment_id`, `owner_id`, `capture_at`, `duration_seconds` (0–7,200s),
  `priority`, `unit_kind` (`conversation` | `capture_span`), `conversation_id`,
  `privacy_generation`, encrypted `audio_uri`. Mutable: attempt, lease token and
  deadline, retry time, `result_uri`, merge status, `state`
  (`quarantined` with `recovery_state` `held` → `prepared` → `running` → terminal
  `failed_held`, or completed). No transcript or audio bodies in queue metadata.
- **Admission**: one transaction binds the content ledger `dispatch_protocol=batch_v1`,
  the sibling set, the frozen projection binding and `intakes/bp_<job>` status.
  Policy is frozen per unit at admission (`config/policy/batch.py`).
- **Result**: `contracts.py:WorkResult` (`segment_id`, encrypted `result_uri`,
  `outcome` from `WORK_OUTCOMES`); holds are `HeldWork`, recovery handoffs `RecoveryWork`.
- **Projection**: `projection.py:Projector` follows the capture-ordered log from
  `merge.py:OrderedMerge`; late captures keep their clock and append after the
  committed tail. Per-part receipts in `projection_parts.py`; only complete
  multipart projection advances the owner cursor.
- **Receipts**: durable upload status via `intake.py:durable_status`
  (`failed` + `failed_segments` + `batch_worker_quarantined` only for terminal
  quarantine); VAD/silence evidence in the result payload (`contracts.py:projection_speech_spans`);
  `omi_batch_pipeline_events_total` counts are best effort, the job records are the census.

## Trips: which invariant each enforces

Registry: omi-workspace `infra/rollout/trips.toml` (rollback authority only with a
passing backtest receipt). All are cohort-scoped: only units the change admitted.

| Trip | Invariant | Authority |
| --- | --- | --- |
| T1 custody missing/mismatch | Custody: object present, right size and generation | rollback, no floor |
| T2 lost speech | Custody: no measured unrecovered speech (unit ≥120s, or >0.2% over ≥3,600 speech-s). Unknown VAD is not measured loss ([ADR 0002](../../docs/adr/0002-unknown-vad-freezes.md)) | rollback |
| T3 wedge + backstops | Latency (above) | freeze ≤50%, backstops roll back |
| T4 route | Transcript route | rollback, no floor |
| T5 failed_held | Recovery stays bounded: >2% with terminal ≥50 and failed_held ≥2 | rollback; below floor freeze |
| T6 intake 5xx | Admission services are healthy. UNVERIFIED as a trip: not in `trips.toml`; the 10-25 observer emits it as a BLIND/alert for lead attribution | alert |

A missing or stale read freezes expansion; it never rolls back.

## Owners

Batch record lane: intake, scheduling, merge, config (A); GPU execution and
payloads (B, `diarizer/batch_pipeline*.py`); projection and receipts (C);
privacy and retention (D) — see [README.md](README.md). Trip registry and
backtests: infra. Ramp steps and rollbacks: the lead, applied by the approved
operator lane. Recovery redrive of `failed_held`: the redrive owner named in each ramp packet.

## Not promised

- Real-time or first-summary deadlines (watch only through 50%).
- Speaker names for sync-off users, or naming parity with legacy, before 100%.
- Recovery of audio that never reached an accepted upload (device-side drops are
  the client WAL contract, `app/lib/services/wals/CUSTODY.md`).
- Automatic redrive of vendor-cause `failed_held` (operator redrive today).
- Exactly one vendor for language ID (Modulate today; self-LID #23460 is required from 50%).
- Live preview quality: retire-cohort preview is a preference shift ([ADR 0003](../../docs/adr/0003-retire-flag-is-preview-preference.md)).
