# Streaming GPU fleet-off activation

Production runtime declarations and listen/pusher chart values set
`STT_GPU_FLEET_OFF=true`. Merge is activation: the lead must pass G0-G3 in
`/Volumes/Ephemeral/scratch/planscost-handoff/fleetoff-gates.md` before merging,
then deploy through the canonical train (dry-run first). This note describes
source configuration; no serving state or production gate was measured here.

Managed streaming uses Soniox under the existing retirement policy. Prerecorded,
speaker-sample and Windows PTT work use Modulate. File VAD bypasses the hosted
service for process-local ONNX. Language detection keeps the existing vendor
probe unless a separately qualified `HOSTED_LID_API_URL` is configured; failure
of that service preserves vendor fallback without dialing shared Parakeet.
No dedicated LID URL is activated by this change (#24473 owns that rollout).

The six routing roles are backend-listen, pusher, backend, backend-sync,
backend-sync-backfill and backend-integration. Configuration regression tests
load the composed manifest and rendered production charts and exercise provider
selection, direct prerecorded calls, VAD and language detection with fleet-off.
The retained shared endpoint bindings support warm rollback; the switch blocks
their use. The dedicated batch worker, diarizer-batch and embedding diarizer
(`/v2/embedding`) retain their existing models and serving configuration.

No definitions for dormant `boot-probe` or `op1-batch-redrive-epoch3` exist in this
repository. The notifications job source has no hosted-VAD binding. Before
reruns, the lead must update or disable the two dormant jobs and remove the old
notifications job's live `HOSTED_VAD_API_URL` binding, including any secret binding.
These are external runtime actions, not completed by this source change.

Keep GPUs warm until every old caller drains and at least 15 minutes of known
zero shared-Parakeet HTTP/LID/stream and hosted-VAD requests has passed. Leave
guards, HPAs, node pools and off overlays alone until the lead reaches steps 3-4.
Rollback before serving: keep false. After scaling to zero: restore and verify
ready capacity first, then restore routing, as in runbook step 5.

Contract: [GPU retirement runbook](../../operational/streaming-gpu-retirement.md).
