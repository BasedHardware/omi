# 2026-11-19 — Defer native projection audio reads until assignment

## What changed

Owner-chain read-ahead still fetches immutable job bindings and results. Native staged and source audio are materialized when the assignment needs verified context. The assignment waits within its step budget, and the next step in the same turn can reuse the pending read. This avoids speculative reads for successors the walk never uses and adds no writes.

## Rollout

`BATCH_PIPELINE_DEFER_NATIVE_PROJECTION_AUDIO_PREFETCH_ENABLED` defaults on. Set it to `false` to restore eager audio read-ahead.

## Readback

With the matching collector revision serving, compare `sum by (outcome) (increase(omi_batch_projection_native_audio_prefetch_total{service_name="backend-integration"}[1h]))` for `started`, `consumed` and `abandoned`. Compare private-sync `batch_source` payload GETs and bucket `ReadObject` bytes per completed audio-hour while checking owner-drain age. An unused successor can avoid a staging body GET and its source GETs. Use the served counts to size the change.

## Custody

Assignment still runs authenticated staging reads, source generation and digest checks, frame and range validation, owner and conversation binding, and live authorization, privacy and deletion checks. The [projection replay contract](../../listen_pusher_pipeline.mdx#batch-projection-contention-and-replay) still governs retries. A speculative result grants no custody or deletion authority.

The [focused assignment tests](../../../tests/unit/test_batch_pipeline_projection_native_audio_prefetch.py) cover full verification, staging and source tampering, mid-read privacy revocation and eager rollback. The [readback runbook](../../runbooks/private-sync-retained-projection-prefetch.md) records the production checks.
