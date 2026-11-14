# Fresh repair rollback reaches serving intake

`main.py` starts the serving runtime independently of router role. Its
`serving.start_serving_from_env()` runs `live.drain_recordings()` when serving is
enabled (a projection-only pump does not run this intake drain). The runtime
manifest enables serving on production `backend-integration`. The same entrypoint
also runs on Cloud Run `backend`, `backend-sync`, `backend-sync-backfill` and GKE
`backend-listen`; their declared serving switch is currently off. Both dev and prod now
bind `RECORD_SEAL_REPAIR_FRESH_ENABLED=true` as `ops_kill` on all five hosts.
`BATCH_HELD_DEAD_LETTER_ENABLED=true`, the second condition for certifying
`record_intake_retry_at`, was already bound on all five and remains independent.
Both keys are already classified as non-secret config.

Pusher does not start this runtime, so it receives neither intake control. The
cohost gate records the fresh switch as listen-only. The dedicated GPU worker
uses `diarizer.batch_pipeline_runtime`, not this intake drain; its Deployment now
also receives the shared `recordSealRepair.freshEnabled` value, alongside its
existing `worker.heldDeadLetterEnabled` binding. All main, Spot, borrowed and T4
worker variants use the same template. This is an env-only chart change; retain
the qualified GPU image digest. The CPU repair CronJob and continuous seal worker
already receive the shared fresh value.

Perform a complete rollback as one coordinated configuration change and rollout:

- Set `recordSealRepair.freshEnabled=false` on the batch-pipeline-worker release.
  It reaches the repair CronJob, continuous record-seal worker and every GPU
  worker Deployment. The chart default is in `backend/charts/batch-pipeline-worker/values.yaml`.
- Set `RECORD_SEAL_REPAIR_FRESH_ENABLED` to value `'false'` in the selected
  `backend/deploy/runtime_env/{dev,prod}.overlay.yaml`, under each of
  `overlay.cloud_run.services.{backend,backend-sync,backend-sync-backfill,backend-integration}.env`
  and `overlay.gke.backend-listen.env`. Keep category `ops_kill`, recompose the
  manifest, and roll those four Cloud Run services.
- Match the listen value in
  `backend/charts/backend-listen/{dev,prod}_omi_backend_listen_values.yaml` and
  roll GKE backend-listen. Disabling only the repair CronJob's chart value leaves
  serving intake enabled; there is no implicit synchronization between these
  chart and Cloud Run sources. Roll all receiving workloads with the same flag
  decision. `BATCH_HELD_DEAD_LETTER_ENABLED` need not be changed for this rollback.

The final config roll targets are the four Cloud Run services, GKE backend-listen,
and the batch-pipeline-worker Helm release (repair CronJob, CPU seal worker if
enabled, and all GPU Deployment variants) using the existing GPU image. Pusher
has no new binding or roll requirement from this change. No live settings,
capacity, custody proof, schedule, image or provider-backlog release flag changed.

The Home flag contract now matches its reader: pending clock, else pending time
inferred from the stamped deadline minus `HOME_TRANSCRIPTION_DEADLINE_SECONDS`,
else creation. The 24h bound is per upload revision, not a lifetime bound. Reads
never renew it; a new upload revision may re-stamp a new bounded wait. A row with
no valid server timestamp at all stays `Transcribing…`; a lifetime guarantee
would need a separate immutable admission clock. No Home behavior changes here.
