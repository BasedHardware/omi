# 2026-11-14 — unlimited_v2 backfill/import daily transcribed-hours cap (default off)

Adds a default-off admission cap for the `unlimited_v2` plan: once the current
UTC user-day already recorded `UNLIMITED_V2_BACKFILL_HOURS_CAP_HOURS` (default
24) of `transcription_seconds` on `users/{uid}/hourly_usage`, further managed
**backfill/import** transcription for that day is refused. The meter is the same
per-user-day basis the finops `unit_cost_user_day.tx_sec` projection aggregates;
nothing is estimated.

Flags: `UNLIMITED_V2_BACKFILL_HOURS_CAP_ENABLED` (default `false`, kill switch)
and `UNLIMITED_V2_BACKFILL_HOURS_CAP_HOURS` (default `24`). Both ship
disabled/24 on the GKE listen deployment, Cloud Run `backend`, `backend-sync`,
`backend-sync-backfill`, `backend-integration`, and the batch-pipeline worker
chart.

Behavior is unchanged while disabled: no plan read, no meter read, no admission
change. Only the sync `backfill` lane and the batch `backfill` lane pass the
backfill marker; live listen and fresh sync/batch capture never do, so live
capture is untouched even on a user-day above the cap. Above the cap the answer
is the existing exhausted-allowance contract — offline segments take durable
holds. Free, Plus and the deprecated paid tiers are unchanged in both modes.

Contract section: [Funded transcription cap](../listen_pusher_pipeline.mdx#funded-transcription-cap).
Runbook, readback and activation: [unlimited-v2-backfill-hours-cap](../runbooks/unlimited-v2-backfill-hours-cap.md).
