# Free-allowance watch: route coverage (SCA-1750), 2026-11-15

This follows the [watch-only ledger note](2026-11-12-free-allowance-watch.md). Serving admission, prices, plans,
wire payloads and user-visible behaviour are unchanged.

## Why

A production GMP read on 2026-11-15 covered the 24 hours to about 01:40Z. It used the `ro-prod` agent tier and
read aggregates only. It showed the watch could not judge most free spend:

| Path | Decisions | Problem |
|---|---|---|
| `live_open` | 8,022 `would_allow`; 5,334 `usage_unavailable` | About 40% of free live opens could not read usage. |
| `prerecorded` | 3,055 `would_refuse` | Every one had lease reason `identity_unavailable`. |
| batch, upload, sync | none | No series reached GMP. |

## What changed

1. **Monthly-usage epoch on production listen and pusher.** The Cloud Run billing gate (`backend`, `backend-sync`,
   `backend-sync-backfill`, `backend-integration`) rebuilds and trusts `monthly_usage_totals` documents under
   `FSR_USAGE_MONTH_TOTAL_EPOCH=c2fs_20261026_r1`.
   - Production `backend-listen` and `pusher` read the same documents with `v1`. The watch's verified reader
     therefore rejected them with `ValueError('unverified monthly usage')`, which was reported as
     `usage_unavailable`.
   - Both GKE hosts now use `c2fs_20261026_r1`, set in the prod overlay, the regenerated manifest and the prod
     chart values.
   - `FIRESTORE_READ_LEVERS` keeps `usage_month_cache` and `usage_month_total` at 0 on GKE, so no legacy reader
     starts trusting monthly totals.
   - Dev, the jobs and desktop-backend stay on `v1`.
   - A document that is ready under a different valid epoch now raises `UsageBaselineNotReady` instead of a plain
     `ValueError`. The watch then re-proves the month with the existing fenced source scan under its own epoch, so
     `v1` documents written by listen before this change do not stay `usage_unavailable`. Corrupt totals and an
     invalid configured epoch still raise `ValueError`.
2. **New `unbound` decision.** Previously `observe_unbound` emitted `would_refuse` whenever no account could be
   resolved. The callers were speaker-sample verification, the recovery recognizers and the transcription shadow,
   so these calls were counted as allowance refusals.
   - A call with no account now emits `omi_free_allowance_watch_decisions{decision="unbound"}`.
   - Lease reason `identity_unavailable` is unchanged.
   - A call that has an account but no bound operation still emits `would_refuse` with reason
     `billing_scope_unavailable`.
   - Before enforcement, these callers must pass the uid and run inside an operation. Otherwise enforcement would
     refuse them for everyone.
3. **Metric export.**
   - `omi_free_allowance_.*` was added to the explicit keep rule in `deploy/cloud_run_gmp_sync.yaml`.
   - The batch worker's private `/metrics` registry now registers the four allowance collectors, through
     `utils/stt/allowance_metrics.py`. That module imports only `prometheus_client`, so the worker's static
     reader closure does not gain the watch's policy imports.

## Reading the series across the change

- **Before the serving revision:** `prerecorded` `would_refuse` counts are unattributed calls, not allowance
  refusals.
- **After the serving revision:** `live_open` `usage_unavailable` should fall sharply, `prerecorded` should report
  `unbound`, and `batch_gpu`, `sync` and `batch_provider` series should appear.
- **Windows:** do not compare windows that straddle the serving revision.

Validation now uses a sampled free-user check (David, 2026-11-15, recorded on SCA-1750). It replaces the full-day
custodian reconciliation. Its per-user data stays on the operator host and only aggregates are published.

## Rollout and rollback

This rolls out with the normal backend, listen and pusher trains.

- **Rollback:** revert the PR, or restore `v1` for the two GKE hosts in the prod overlay and chart values and
  regenerate the manifest.
- **Observer kill switch:** `STT_FREE_ALLOWANCE_WATCH_ENABLED=false` still stops new observations.

## Evidence

- Unit tests: `test_free_allowance_metrics_are_scraped.py` (keep rule and worker registry),
  `test_free_allowance_session.py::test_unattributable_call_is_unbound_not_an_allowance_refusal`, and the
  epoch expectations in `test_render_backend_runtime_env.py` and `fixtures/usage_month_served_defaults.json`.
- Contract section: [Funded transcription cap](../../listen_pusher_pipeline.mdx).
