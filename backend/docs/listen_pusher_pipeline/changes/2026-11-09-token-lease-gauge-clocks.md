# Repair age gauge excludes invalid enqueue clocks

Lead decision 6 follows the local production readout
`data/run-2026-11-08-pipeline-refactor/findings-24953-gate.md` in the Omi
workspace. Zero enqueue clocks produce a horizon-epoch age, masking the
oldest valid sample in the token-lease backlog warning.

Discovery now optionally collects metric ages where the enqueue clock is
known. `MIN_METRIC_ENQUEUED_AT` is a telemetry-only floor of 2020-01-01 UTC,
before the record pipeline existed. Older/non-positive clocks do not
contribute to the gauge; future clocks already fail the existing discovery
minimum-age check. With no valid samples the gauge is zero. The conversation
discovery samples still contribute as before, excluding duplicate job paths.

Returned rows, their ages, ordering, cursors, saturation and repair attempts
are unchanged, including jobs with zero or implausible clocks. This does not
implement the discovery correction owned by cl2-fixnow or Part B. The active
repair CronJob remains the producer, the idle seal worker stays disabled,
and no alert expression or threshold changes.

Unit regressions cover mixed valid/zero pages, all-zero pages, other
implausible clocks and the inclusive floor, in both discovery orders. They
compare the complete discovery result with and without metric collection and
exercise the coordinator's actual gauge publication. Real PromQL backtests
add a zero-age page that stays quiet, correction of a legacy pinned series to
zero that clears the warning, and a legacy pinned epoch constant that still
fires: a positive constant is indistinguishable from a legitimate flat backlog
in the warning, so validation belongs at the producer.

Mode remains off by default. Production signal-gap measurement, the 48-hour
shadow soak and ramp acceptance remain pending. No production/GCP access is
used for this correction. Validation results are recorded after the run.
