# Batch projection and timeliness alarms

The all-epoch compute-queue alarm and bounded-scan blindness page are in
`../alerts/batch-queue-safety.json`; see
`../../../docs/runbooks/batch-queue-safety.md`. They are independent of the
epoch-scoped delivery rules below. They do not waive held recovery or custody.

`alerts.yaml` holds the projection-obligation PrometheusRule. Prod runs no Alertmanager, so that file is a record,
not a live route. Live alerts are Grafana-managed rules in `../alerts/*.json`.

## 2-hour timeliness alarm (David, 2026-11-02)

Target: process most batch audio within 30 minutes of admission, and alarm when a unit is still unpublished after
2 hours. Failed-held, quarantined and repair waits count, because that is how 165 segments were lost on 2026-11-01.

The batch worker queue sample exports these series (`utils/batch_pipeline/metrics.py`, at most once per 5 minutes
per process):

| series | meaning |
|---|---|
| `omi_batch_timeliness_new_oldest_age_seconds{leg}` | oldest unpublished unit admitted at or after the epoch. `uncommitted`, `quarantined` and `assignment_held` clock from `enqueued_at`; `projection` and `quarantine_held_rows` clock from `committed_at`, a lower bound |
| `omi_batch_timeliness_new_over_sla_units{leg}` | units admitted at or after the epoch and unpublished past 2 h, per leg |
| `omi_batch_timeliness_backlog_units{leg}` | unpublished units from before the epoch; visible, never alarmed |
| `omi_batch_timeliness_scan_truncated{leg}` | 1 when a walk page is full and may hide an older admission (`uncommitted`, `projection`); the blind rule fires after 30 minutes, which is expected during large catch-up uploads |
| `omi_batch_timeliness_samples_total{outcome}` | `ok`, `error`, `disabled` |

Legs:
- `uncommitted`: `ready`, `leased`, `result_ready`, `retry`, `vendor_held`, skipping deliberate admission holds
  (allowance, budget, fair use, daily ceiling) and live vendor holds.
- `quarantined`: every recovery state, including `failed_held` and `prepared`.
- `assignment_held`: committed, but the projection receipt is quarantined (job `recovery_state=held`), so the text
  never reached the conversation.
- `projection`: committed, projection `pending`, `persisted` or `ready`.
- `quarantine_held_rows`: result rows at `quarantine_held`. Counted, never alarmed: most are ready receipts whose text
  is already in the conversation and only the content ledger waits; the rest are the assignment holds above.
- `terminal_empty` (counts only): the quarantined units that are `failed_held` with recovery failure `empty_asr`
  and measured held VAD speech exactly 0, the existing silence contract for "no recoverable speech".

David, 2026-11-02 10:45Z: "finished recording counts as processed". So `TERMINAL_EMPTY_IS_PROCESSED` in
`config/batch_timeliness.py` defaults to `True`: terminal empty units are subtracted exactly from the `quarantined`
leg, and `terminal_empty` stays visible. `False` puts them back in the alarm. On prod at 2026-11-02 10:36Z, no
quarantined `empty_asr` unit had zero measured speech: 13 of 13 admitted since the epoch carried some (10 under
2 s), so today the default changes nothing. Units with measured speech always stay in the alarm.

Config: `BATCH_TIMELINESS_ALARM_ENABLED` (default on; `false` stops the Firestore reads),
`BATCH_TIMELINESS_EPOCH` (default `2026-11-02T06:09:00Z`, when the target was set) and
`BATCH_TIMELINESS_INTERVAL_SECONDS` (default 300, clamped to 60–3600).

Reads per sample, worst case: 8 bounded walks of 20 documents (160; 9 with the terminal-empty switch on), the projection walk and its job reads (100), 3
single-document reads, and 17 count aggregations (one read per 1,000 index entries each, about 25 at today's backlog).
That is under 300 reads per process per sample. Sixteen workers at the default cadence read at most about 1.4M per day
(roughly $0.4–0.8/day); a healthy queue reads far less, because walks stop at the first unheld row. The
`assignment_held` leg needs the new jobs `(state, recovery_state, enqueued_at)` composite index, and `terminal_empty`
needs jobs `(state, recovery_state, recovery.failure.reason, measured_held_vad_speech_seconds, enqueued_at)`. Until
both are READY, the whole sample fails and counts as `error`, and the stale rule fires.

The metric is alert-only. No scheduler, ramp, hard-3 rollback trigger or gate reads it.

### Apply (lead)

The producer is now present in prod and the measured metric inventory includes its series. The three rules
live in `../alerts/batch-timeliness.json`, in the combined export and the existing `live-alert-gate.json` import
set. Gate changes trigger the existing metrics-egress workflow; no workflow change is needed. A committed
definition is not evidence that production Grafana has imported it.

1. Deploy a batch worker image that contains this change.
2. Confirm in Prometheus that `max(omi_batch_timeliness_observed_at_seconds) > 0` and that
   `omi_batch_timeliness_samples_total{outcome="ok"}` increases.
3. Run the monitoring contracts. Dispatch the existing metrics-egress workflow for production at the reviewed
   main SHA, or use the documented Grafana provisioning path (`--apply --backup-file <new-file>`).
4. Read back every gated UID, its definition, unpaused state and receiver; distinguish import proof from actual
   notification-delivery proof. Deploy the queue-age worker/guard fix before importing its queue-specific pages.

`omi-batch-unit-unpublished-2h` is page tier with human audience and no agent mute interval: it uses the existing
Telegram receiver. The stale and truncated-scan diagnostics remain agent tier. The independent queue-safety blind
rule is page tier. No contact point, secret or notification-policy tree is changed.

Rollback: set `BATCH_TIMELINESS_ALARM_ENABLED=false` on the worker (gauges freeze and the stale rule fires), or pause
the three Grafana rules. The index step: merge triggers the Firestore index reconcile; approve its prod job and wait
for READY before shipping the worker (merge_pr.sh waits out these gates).
