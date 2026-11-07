# Batch speaker final-pass serving readout

> **The algorithm is untested on prod traffic.** The readout measures the serving config, not the speaker algorithm. Root cause (ro-prod counts, 2026-11-07): `backend-integration` serves 100% of traffic and has `BATCH_FINAL_PASS_ENABLED` but no `HOSTED_DIARIZATION_API_URL`. 98% of post-serving `failed_batch_audio` lines are `diarizer_unconfigured`, so the diarizer is almost never called there. The 23 successes come from the services that have the URL. The 11-05 local repro (14 of 16 completed) has not been confirmed on prod traffic.

Status: **MEASURED, PARTIAL.** Aggregate counts from the read-only RC session, ro-prod GMP, measured about 2026-11-07T19:40Z. Not a forecast. Compute and outcome figures are sampled or windowed, as noted per row.

The operator updates this record after serving at 100% and links the dated
measurement when reporting cost. Do not copy changing figures into the runbook.

| Evidence | Record at serving / T+2h |
| --- | --- |
| Serving release SHA / image digest | Image `0433d12`. Full digest `gcr.io/based-hardware/backend@sha256:dedf61c09819a7ba5827a19a577a36e8b6657d198b76f11f0183ac29ab6d6949`, read on ro-prod from revision `backend-0433d12-42329148500-1` (train cl2d-1107a). Fix commit `08b33b93` (#24691) is an ancestor of `0433d12` (verified by compare, 353 commits ahead). |
| GKE backend-listen / Pusher / installed sync worker identities and ready times | Not captured in this readout. Pending, from the deploy record. |
| Cloud Run backend / sync / sync-backfill / integration traffic revision identities | `backend-integration`, `backend`, `backend-sync`, `backend-sync-backfill` all on `0433d12` revisions at 100%, per the 02:51Z deploy check. Revision `backend-0433d12-42329148500-1` is the `backend` revision read for the digest above; the other services' revision names are not yet recorded. |
| All-runtime serving timestamp (UTC) | About 02:34Z, 2026-11-07 (train cl2d-1107a, hand-finished after an env-fold timeout). |
| Readout due (serving + 2 hours, UTC) | About 04:34Z, 2026-11-07. This readout was produced late, at about 19:40Z. |
| Observation window and measurement timestamp (UTC) | Window about 02:34Z to 19:40Z, 2026-11-07. Measured about 19:40Z. |
| GPU-hours/day, measurement method and source dashboard/query link | Pool `prod-omi-diarizer-batch`: 24 GPU-h/day allocated. Consumed about 0.02 GPU-h/day post-serving against 0.14 GPU-h/day baseline. Method: utilization-sampled estimate. Query link pending. |
| Compute consumption versus allocated pool/idle hours | Consumed about 0.02 GPU-h/day. Idle is allocated minus consumed, about 23.98 GPU-h/day. Kept distinct. The cause of the lower consumption is **unverified**. Terminal volume is about flat (about 42.4k a day post-serving against 39.9k a day baseline, from the same outcome counters), so fewer completed runs does not explain it. Per-run GPU time by outcome is needed before interpreting it as efficiency or as lost work. |
| Baseline window and comparable source link | 24h window ending 02:34Z, 2026-11-07: 39,904 terminals, 29 successes. Query link pending. |
| Outcome freshness, success/partial/refusal, latency and queue-depth evidence | Durable outcome counters fresh at 117s at measurement. Post-serving: 30,224 terminals, 23 successes (0.08%). Baseline: 39,904 terminals, 29 successes (0.07%). `failed_batch_audio` 58.5% of terminals post-serving versus 45.6% baseline. Legacy speaker-matching fallbacks: 26 post-serving versus 72 baseline. Latency and queue-depth not captured in this readout. |
| Decision / rollback evidence | **Decision: lead2 ruled B (26b2bc-B, 2026-11-07 21:59Z), but it is not yet implementable as written.** The prod admission check requires `BATCH_FINAL_PASS_ENABLED` to agree across every production host, so a `false` on `backend-integration` alone is rejected, and removing the binding is also rejected (every Cloud Run host needs an explicit true or false). A global `false` would stop the 23 post-serving successes on the configured services. Lead2 must choose: a fleet-wide change, a validator change for host-scoped disable, or option A (add the diarizer URL to `backend-integration`, new GPU spend, David's gate). No rollback of the pass itself is taken in this readout. |
| Labeled speaker accuracy on prod-path transcripts | **Not measured.** No labeled prod-path set was found. Not estimated. |

Use the [runbook](../runbooks/batch-conversation-speakers.md#rollback-on-every-serving-runtime)
to disable the pass across every serving runtime. Repository tests validate the
bindings and custody path; they cannot populate this live operational readout.
