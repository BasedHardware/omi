# Soniox idle cohort retirement

SCA-3503 retires the user-hashed Soniox idle cohort, its three treatment settings,
and its arm-specific telemetry. Every listen session uses the [fleet idle
policy](../../listen_pusher_pipeline.mdx#soniox-idle-transport). The
`SONIOX_IDLE_CLOSE_SECONDS` kill switch remains available. The fleet policy
still defaults to a 45-second VAD silence threshold, a 20-second no-frame
threshold, a 60-second re-arm period, and a shared cap of 12 closes per session
per rolling hour.

Production listen had the cohort pinned at 0 before retirement. The next
serving listen rollout removes the cohort keys. After rollout, confirm the keys
are absent and compare `omi_soniox_connected_seconds_total` with the prior
serving baseline. Rollback is a revert of [PR #25913](https://github.com/BasedHardware/omi/pull/25913).

The [idle transport tests](../../../tests/unit/test_soniox_idle_close.py) cover
the fleet kill switch, close and reopen behavior, and connected-time accounting.
The [listen Helm tests](../../../tests/unit/test_backend_listen_helm_defaults.py)
verify the cohort keys are absent from the rendered deployment.
