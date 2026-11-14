# 2026-11-14 — unlimited_v2 daily transcribed-hours cap (default off)

Adds a default-off admission cap for the `unlimited_v2` plan: once the current
UTC user-day already recorded `UNLIMITED_V2_TX_HOURS_CAP_HOURS` (default 8) of
`transcription_seconds` on `users/{uid}/hourly_usage`, further managed
transcription for that day is refused. The meter is the same per-user-day basis
the finops `unit_cost_user_day.tx_sec` projection aggregates; nothing is
estimated.

Flags: `UNLIMITED_V2_TX_HOURS_CAP_ENABLED` (default `false`, kill switch) and
`UNLIMITED_V2_TX_HOURS_CAP_HOURS` (default `8`). Both ship disabled/8 on the GKE
listen deployment, Cloud Run `backend`, `backend-sync`, `backend-sync-backfill`,
`backend-integration`, and the batch-pipeline worker chart.

Behavior is unchanged while disabled: no plan read, no meter read, no admission
change. Above the cap the answer is the existing exhausted-allowance contract —
live listen pauses provider work and holds audio (capture continues), offline
segments take durable holds, and the HTTP STT route keeps its 402. Free, Plus and
the deprecated paid tiers are unchanged in both modes.

Contract section: [Funded transcription cap](../listen_pusher_pipeline.mdx#funded-transcription-cap).
Runbook, readback and activation: [unlimited-v2-day-cap](../runbooks/unlimited-v2-day-cap.md).
