# Batch projection and timeliness alarms

`alerts.yaml` holds the projection-obligation PrometheusRule. Prod runs no Alertmanager, so that file is a record,
not a live route. Live alerts are Grafana-managed rules in `../alerts/*.json`.

## 2-hour timeliness alarm (David, 2026-11-02)

Target: process most batch audio within 30 minutes of admission, and alarm when a unit is still unpublished after
2 hours. Failed-held, quarantined and repair waits count, because that is how 165 segments were lost on 2026-11-01.

The batch worker queue sample exports these series (`utils/batch_pipeline/metrics.py`, at most once per 5 minutes
per process):

| series | meaning |
|---|---|
| `omi_batch_timeliness_new_oldest_age_seconds{leg}` | oldest unpublished unit admitted at or after the epoch. `uncommitted` and `quarantined` clock from `enqueued_at`; `projection` and `sibling_held` clock from `committed_at`, a lower bound |
| `omi_batch_timeliness_new_over_sla_units{leg}` | units admitted at or after the epoch and unpublished past 2 h (`quarantined`, `projection`, `sibling_held`) |
| `omi_batch_timeliness_backlog_units{leg}` | unpublished units from before the epoch; visible, never alarmed |
| `omi_batch_timeliness_scan_truncated` | 1 when the bounded uncommitted walk saw only policy holds |
| `omi_batch_timeliness_samples_total{outcome}` | `ok`, `error`, `disabled` |

Legs:
- `uncommitted`: `ready`, `leased`, `result_ready`, `retry`, `vendor_held`, skipping deliberate admission holds
  (allowance, budget, fair use, daily ceiling) and live vendor holds.
- `quarantined`: every recovery state, including `failed_held` and `prepared`.
- `projection`: committed, projection `pending`, `persisted` or `ready`.
- `sibling_held`: committed, held behind a quarantined sibling. Counted, never alarmed: its root is the quarantined
  sibling, and a `partial` ledger may already show the owner part of the text.

Config: `BATCH_TIMELINESS_ALARM_ENABLED` (default on; `false` stops the Firestore reads),
`BATCH_TIMELINESS_EPOCH` (default `2026-11-02T06:09:00Z`, when the target was set) and
`BATCH_TIMELINESS_INTERVAL_SECONDS` (default 300, clamped to 60–3600). Each sample uses existing indexes only:
about 10 single-document or count reads, plus at most 40 for the hold-skipping walks.

The metric is alert-only. No scheduler, ramp, hard-3 rollback trigger or gate reads it.

### Apply (lead)

The rules live in `../pending/batch-timeliness.json` until the series exist in prod, because the monitoring
contracts reject rules that read metrics missing from `metric-inventory.prod.json`.

1. Deploy a batch worker image that contains this change.
2. Confirm in Prometheus that `max(omi_batch_timeliness_observed_at_seconds) > 0` and that
   `omi_batch_timeliness_samples_total{outcome="ok"}` increases.
3. Move both rule objects from `../pending/batch-timeliness.json` into `../alerts/batch-timeliness.json` and append
   them to `../alert-rules.json`. Refresh `metric-inventory.prod.json` with its documented generator, then run the
   monitoring contract tests.
4. Import with the documented Grafana rule provisioning path (`--apply --backup-file <new-file>`).

Both rules are agent tier: Grafana keeps their state, and Telegram stays muted (`omi-tier-silent`). Change `tier`
to `page` only if David wants the alarm on his phone.

Rollback: set `BATCH_TIMELINESS_ALARM_ENABLED=false` on the worker (gauges freeze and the stale rule fires), or pause
the two Grafana rules.
