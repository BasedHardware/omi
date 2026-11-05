# Batch speaker final-pass serving readout

Status: **NOT MEASURED — awaiting production serving.** This record is the
destination for the release operator's T+2h GPU-hours/day readout, not a forecast
or a claim that the local owner-data gate has passed.

The operator updates this record after serving at 100% and links the dated
measurement when reporting cost. Do not copy changing figures into the runbook.

| Evidence | Record at serving / T+2h |
| --- | --- |
| Serving release SHA / image digest | Pending |
| GKE backend-listen / Pusher / installed sync worker identities and ready times | Pending |
| Cloud Run backend / sync / sync-backfill / integration traffic revision identities | Pending |
| All-runtime serving timestamp (UTC) | Pending |
| Readout due (serving + 2 hours, UTC) | Pending |
| Observation window and measurement timestamp (UTC) | Pending |
| GPU-hours/day, measurement method and source dashboard/query link | Pending |
| Compute consumption versus allocated pool/idle hours | Pending; keep these distinct |
| Baseline window and comparable source link | Pending |
| Outcome freshness, success/partial/refusal, latency and queue-depth evidence | Pending |
| Decision / rollback evidence | Pending |

Use the [runbook](../runbooks/batch-conversation-speakers.md#rollback-on-every-serving-runtime)
to disable the pass across every serving runtime. Repository tests validate the
bindings and custody path; they cannot populate this live operational readout.
