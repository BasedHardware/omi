# Conversations v3 stage all

SCA-2918 moves the shared runtime stage from `beta` to `all`. New recording-derived
conversations are admitted for owners with a current v3-capable client marker,
including owners outside the beta channel. Owners without the marker stay on
legacy intake. See the [pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
and the [activation runbook](../../runbooks/conversations-v3.md).

## Rollout

- Land and deploy sync gate telemetry from [PR #26299](https://github.com/BasedHardware/omi/pull/26299)
  and confirm it is exporting before widening.
- Arm the auto-revert guard for the new stage. After one full lookback window at
  `all`, revert to `beta` if reconcile 5xx exceeds 5% or pending-age p95 exceeds
  one hour.
- On 2026-11-25, David approved the flip at about 06:00 UTC on 2026-11-26 and
  accepted rollout variance. Verify activation readiness in the runbook's move
  order.

Deploy `backend`, `backend-sync`, `backend-sync-backfill`, `backend-integration`,
and `backend-projection-pump`. Redeploy `notifications-job` in full mode,
`x-connector-sync-job`, and `frame-request-retention-job`. Apply the shared
listen/pusher ConfigMap and roll both workloads to load it. Run the
[desktop-backend production workflow](../../../../.github/workflows/desktop_backend_prod.yml)
separately so desktop picks up the same stage.

## Rollback

Set `conversations_v3_stage: beta` in the shared source, regenerate the runtime
manifest, and redeploy the same set, including a separate desktop-backend run.
For a hard stop on new v3 admission, deploy `CONVERSATIONS_V3=off` through the
production overlay across the same set. Previously marked recordings continue
draining.

### Desktop-backend recovery while stage is `all`

Traffic rollback or recovery can route desktop-backend to a retained revision
with its original `beta` environment. After any desktop traffic rollback or
recovery, take one of these actions.

- Forward-redeploy desktop-backend through its production workflow with the
  admitted image needed for recovery and the current manifest's v3 environment.
- Restore the shared stage to `beta` and redeploy the full set listed above,
  including a separate desktop-backend production run.

Collect fresh serving state and rerun the
[activation parity check](../../runbooks/conversations-v3.md#desktop-backend-recovery-while-stage-is-all).
Confirm stage equality and a `READY` verdict before closing recovery.
