# Batch pipeline package map

This package separates durable upload admission, GPU compute and ordered legacy
projection. The design is in [batch-pipeline-worker.md](../../docs/batch-pipeline-worker.md);
operator settings, RPCs and index readiness are in
[batch-pipeline-serving.md](../../docs/batch-pipeline-serving.md).

## Entry points and boundaries

| Area | Modules | Responsibility |
| --- | --- | --- |
| Shared contract | `contracts.py`, `capacity.py` | Immutable work/results, original VAD evidence, pool ceilings and fresh capacity checks; the A/B meeting point. |
| Upload intake | `intake.py`, `audio.py` | Cohort admission, canonical capture-unit boundaries and bounded encrypted context. |
| Durable scheduling | `scheduler.py`, `control.py`, `merge.py` | Priority/owner fairness, token-fenced leases, capped indefinite retry and capture-ordered result log. |
| Compute loop | `pump.py`, `compute_client.py` | Pull/heartbeat/drain interface used by the GPU runtime; service-OIDC authorization before model spend. |
| Spend policy | `admission.py` | Backend-only original quota guards and lease-bound compute seals. |
| Encrypted artifacts | `artifacts.py`, `artifact_policy.py` | Authenticated object IO, immutable generations and privacy-fenced object registration. |
| Conversation projection | `context.py`, `projection.py`, `projection_parts.py`, `projection_followup.py` | Validated encrypted metadata, legacy VAD/assignment grouping and resumable per-part receipts. |
| Enrichment | `enrichment.py` | Privacy-aware adapter to the existing coalesced sync reprocess outbox. |
| Quarantine recovery | `quarantine_recovery.py`, `recovery_recognizers.py`, `recovery_steps.py` | Owner-gated per-unit STT, bounded independent language recovery, single dispatch and encrypted result reconciliation; async provider waits release the shared executor and retain the original batch claim. |
| Cleanup | `retention.py` | Durable erasure outboxes and bounded object/metadata cleanup. |
| Real-upload shadow | `shadow_intake.py`, `shadow_worker.py`, `shadow_recovery.py`, `shadow_metrics.py` | Idle-only isolated GPU handoff, capped recovery and hashed outcomes; [contract](../../docs/batch-pipeline-shadow.md). |
| Backend supervisor | `serving.py`, `metrics.py` | Recovery, ordered projection, retention and queue-age export independent of upload admission. |

Firestore transaction/query adapters live in `database/batch_pipeline_*.py`.
Serving indexes are declared in `database/sync_pipeline_indexes.py`, imported by
the central registry and generated into `firestore.indexes.json`. Private worker
HTTP handlers live in `routers/batch_pipeline.py`; the legacy sync router owns
the minimal upload/status hooks. GPU runtime/model implementations live under
`diarizer/` and must not import backend conversation/LLM projection dependencies.

## Invariants and ownership

- A owns intake, scheduling, merge, service integration and config. B owns GPU
  execution and encrypted payload production. C owns projection/accounting and
  multipart receipts. D owns privacy/deletion fences and retention.
- Existing content follows its recorded protocol; batch admission failures never
  start a legacy twin. Admission rollback leaves accepted work draining.
- Late captures keep original clocks and append after the committed log tail;
  the capture high watermark never regresses. Historical dead heads are redriven.
- Privacy-fenced recovery is isolated by `database/batch_pipeline_recovery.py`;
  it revokes leases without clearing privacy fences or resurrecting content.
- Dedicated GPUs receive conversation-sized units (intake maximum one hour).
  Shared-live admission remains separately off, bounded to120s and one hardware
  flight; lease expiry never proves non-preemptible CUDA idle.
- Only complete multipart projection advances the owner publication cursor.
  Durable privacy checks apply before reads/writes and object publication.
- All switches default off; production index/GPU/live acceptance belongs to the
  lead. Tests use synthetic identities, fakes and explicitly bound loopback
  Firestore, through `backend/test.sh`.
