# Projection kill switches document the off-only contract and warn

The deliberate default-on contract is unchanged: only `off` after trimming
whitespace and lowercasing disables these five switches:

- `BATCH_PIPELINE_SERVING_PROJECTION_SWEEP`
- `BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED`
- `PROJECTION_DRAIN_CLAIM_AWARE`
- `PROJECTION_DRAIN_PRIVACY_BACKOFF`
- `PROJECTION_PRIVACY_REFUSAL_RESUME`

`false`, `0`, and `no` keep the switch ON and now emit a WARNING:
`only 'off' disables <SWITCH>; value '<v>' keeps it ON`, using the normalized
value. Unset and other values remain ON. No production values or rollout flags
are changed. F-010984 is resolved by documentation and warnings, not by changing
behavior; the off-only contract is deliberate and pinned by tests.

Contracts: [serving projection sweep](../../listen_pusher_pipeline.mdx#dedicated-projection-pump)
and [drain admission](../../listen_pusher_pipeline.mdx#batch-projection-drain-admission).
Regression coverage: `tests/unit/test_batch_unit_policy.py::test_projection_kill_switch_off_only_contract_and_warning`
checks the production parser and exact warning text for all five names through
injected flags and environment variables, including normalization.

Source: loop-audit finding F-010984; coordinator ruling in workspace brief
`data/run-2026-11-07-dropped-work-crawl/briefs-s2b/S2-revert-and-warn.md`.
Rollback: revert the warning and documentation commit.
