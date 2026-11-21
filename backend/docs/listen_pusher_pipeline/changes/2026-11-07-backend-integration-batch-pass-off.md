# backend-integration batch speaker final pass switched off

`backend-integration` serves all Cloud Run traffic but has no `HOSTED_DIARIZATION_API_URL`. Its batch
speaker final pass therefore failed with `diarizer_unconfigured` before any diarizer call, and the
pass succeeded almost nowhere. This change switches `BATCH_FINAL_PASS_ENABLED` off on that host
alone (lead2 ruling B). The other five production hosts keep it on.

What changed:

- `backend/deploy/runtime_env/prod.overlay.yaml`: `BATCH_FINAL_PASS_ENABLED` is `false` on
  `backend-integration`, with a comment saying why. `HOSTED_DIARIZATION_API_URL` is listed in that
  host's `forbidden_env`, so the live service state is checked for it.
- `backend/deploy/runtime_env.yaml`: regenerated with `compose_runtime_env.py`.
- `backend/scripts/runtime_env_capability_contracts.py` (#24888): a Cloud Run host without the diarizer
  URL may be switched off alone. A host with the URL, and every GKE host, stays on unless all six hosts
  are off, which keeps the full rollback valid.

Rollout and flag state: the other five production hosts keep `BATCH_FINAL_PASS_ENABLED=true`. The full
rollback, `false` on all six hosts, is unchanged. The runbook is
[batch-conversation-speakers](../../runbooks/batch-conversation-speakers.md). Option A, adding the
diarizer URL to `backend-integration`, is new GPU spend and is not part of this change.

Evidence: the read-only ro-prod counts behind this change are in the RCA and the serving readout.
Local tests (`test_batch_final_pass_runtime.py`, `test_runtime_env_manifest_compat.py`,
`test_backend_runtime_env_validator.py`, 242 passed) and `compose_runtime_env.py --check` cover the
manifest and the admission rule. They do not prove deployment, the live rollback, or the GPU
measurement.
