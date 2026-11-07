# Projection kill switches honor explicit off values

The following default-on switches now treat `false`, `0`, `off`, and `no` as
disabled after trimming whitespace and lowercasing:

- `BATCH_PIPELINE_SERVING_PROJECTION_SWEEP`
- `BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED`
- `PROJECTION_DRAIN_CLAIM_AWARE`
- `PROJECTION_DRAIN_PRIVACY_BACKOFF`
- `PROJECTION_PRIVACY_REFUSAL_RESUME`

Previously only `off` disabled these controls. Unset values remain ON. This
changes behavior only for an explicit `false`, `0`, or `no` value, including
case and whitespace variants. This change sets no production values and adds
no rollout flag.

Contracts: [serving projection sweep](../../listen_pusher_pipeline.mdx#dedicated-projection-pump)
and [drain admission](../../listen_pusher_pipeline.mdx#batch-projection-drain-admission).
Regression coverage: `tests/unit/test_batch_unit_policy.py::test_projection_kill_switch_explicit_off_values`
executes the production parser for all five names through injected flags and
environment variables, including explicit off values, `on`, unset, and normalization.

Source: loop-audit finding F-010984; workspace brief
`data/run-2026-11-07-dropped-work-crawl/briefs/S2-kill-switch-off-values.md`.
Rollback: revert this change.
