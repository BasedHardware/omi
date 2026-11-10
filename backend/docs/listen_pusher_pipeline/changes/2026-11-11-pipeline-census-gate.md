# Pipeline ledger census gate (C2)

The C1 in-flight ledger is now readable by an operator-only, aggregate-only
census. `GET /v2/pipeline-ledger/census` takes one owner and a window, reads
the C1 `census_window` helper, joins each row to its conversation row for the
product `home_step.classify` predicate, and returns exact counts by stage,
stuck-past-deadline counts, the Home-visible share on the real-speech
denominator, per-end-type counts and Kaplan-Meier p50/p90. It never returns a
uid, conversation id, title, transcript or audio path.

`GET /v2/pipeline-ledger/explain/{conversation_id}` returns one
operator-supplied conversation's ledger transition list. It is for a human
debugging one row, never for the ramp decision.

Both routes use the same service-OIDC gate as the batch worker RPC, with
`PIPELINE_LEDGER_CENSUS_AUDIENCE` and `PIPELINE_LEDGER_CENSUS_INVOKER_SA`.
Unset env means the service is not a census target. The census is owner-scoped
because the C1 read helper is owner-scoped; a fleet-wide aggregate is a
separate read the C1 PR deferred.

The census publishes bounded-label gauges (`omi_pipeline_ledger_stuck_rows`,
`_stuck_users`, `_oldest_stuck_age_seconds`, `_new_stuck_per_hour`,
`_unknown_end_type_share`, `_refreshed_at_seconds`). The workspace gate runner
writes `omi_pipeline_ledger_gate_receipt_generated_at_seconds` as a textfile.
`alerts/pipeline-ledger.json` pages on stuck rows, a stale census sample and a
stale gate receipt; a missing sample is `Alerting`, never a healthy zero.

Contract: [pipeline ledger](../../listen_pusher_pipeline.mdx). Rollback: remove
the two routes and the three alert rules; the ledger write path is unchanged.
