# Batch speaker final-pass serving readout

Status: **MEASURED, PARTIAL.** Aggregate counts from the read-only RC session, ro-prod GMP, measured about 2026-11-07T19:40Z. Not a forecast. Compute and outcome figures are sampled or windowed, as noted per row.

The operator updates this record after serving at 100% and links the dated
measurement when reporting cost. Do not copy changing figures into the runbook.

| Evidence | Record at serving / T+2h |
| --- | --- |
| Serving release SHA / image digest | Image `0433d12` (digest `dedf61c0`), per the cl2d-1107a deploy record. Fix commit `08b33b93` (#24691) is an ancestor of `0433d12` (verified by compare, 353 commits ahead). |
| GKE backend-listen / Pusher / installed sync worker identities and ready times | Not captured in this readout. Pending, from the deploy record. |
| Cloud Run backend / sync / sync-backfill / integration traffic revision identities | `backend-integration`, `backend`, `backend-sync`, `backfill` all on `0433d12` revisions at 100%, per the 02:51Z deploy check. Exact revision names pending. |
| All-runtime serving timestamp (UTC) | About 02:34Z, 2026-11-07 (train cl2d-1107a, hand-finished after an env-fold timeout). |
| Readout due (serving + 2 hours, UTC) | About 04:34Z, 2026-11-07. This readout was produced late, at about 19:40Z. |
| Observation window and measurement timestamp (UTC) | Window about 02:34Z to 19:40Z, 2026-11-07. Measured about 19:40Z. |
| GPU-hours/day, measurement method and source dashboard/query link | Pool `prod-omi-diarizer-batch`: 24 GPU-h/day allocated. Consumed about 0.02 GPU-h/day post-serving against 0.14 GPU-h/day baseline. Method: utilization-sampled estimate. Query link pending. |
| Compute consumption versus allocated pool/idle hours | Consumed about 0.02 GPU-h/day. Idle is allocated minus consumed, about 23.98 GPU-h/day. Kept distinct. The cause of the lower consumption is **unverified**. Terminal volume is about flat (about 42.4k a day post-serving against 39.9k a day baseline, from the same outcome counters), so fewer completed runs does not explain it. Per-run GPU time by outcome is needed before interpreting it as efficiency or as lost work. |
| Baseline window and comparable source link | 24h window ending 02:34Z, 2026-11-07: 39,904 terminals, 29 successes. Query link pending. |
| Outcome freshness, success/partial/refusal, latency and queue-depth evidence | Durable outcome counters fresh at 117s at measurement. Post-serving: 30,224 terminals, 23 successes (0.08%). Baseline: 39,904 terminals, 29 successes (0.07%). `failed_batch_audio` 58.5% of terminals post-serving versus 45.6% baseline. Legacy speaker-matching fallbacks: 26 post-serving versus 72 baseline. Latency and queue-depth not captured in this readout. |
| Decision / rollback evidence | **Decision: no rollback taken in this readout.** Finding: the pass is serving but almost never succeeds (0.08%, about baseline). Root cause of `failed_batch_audio` not yet identified; exception-type breakdown requested from the MacBook session. Rollback for the final pass is `BATCH_FINAL_PASS_ENABLED=false` on every serving runtime (the runtime manifest binds it as `ops_kill`). `BATCH_CONVERSATION_SPEAKERS_ENABLED=false` also disables the pass, but it is the wider switch for all batch speaker resolution. The owner decides whether to roll back. |
| Labeled speaker accuracy on prod-path transcripts | **Not measured.** No labeled prod-path set was found. Not estimated. |

Use the [runbook](../runbooks/batch-conversation-speakers.md#rollback-on-every-serving-runtime)
to disable the pass across every serving runtime. Repository tests validate the
bindings and custody path; they cannot populate this live operational readout.
