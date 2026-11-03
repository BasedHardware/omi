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

The active rules live in `../alerts/batch-timeliness.json`, are included in the
combined export, and are admitted by `../live-alert-gate.json`. Their metric
families are declared in the inventory; the older captured snapshot is unchanged.

1. Deploy a batch worker image that contains the sampler.
2. Confirm in Prometheus that `max(omi_batch_timeliness_observed_at_seconds) > 0` and that
   `omi_batch_timeliness_samples_total{outcome="ok"}` increases.
3. Dispatch the existing metrics-egress workflow explicitly for production at
   the merged SHA. The gated importer installs and verifies all three rules.
   A main push targets development by default.
4. Complete the delivery qualification in [critical-failures.md](../critical-failures.md).

The two-hour unpublished-unit alarm is page tier and routes to the existing
human Telegram receiver. The stale and blind companions remain muted agent tier.

Rollback an incorrect definition with a forward revert and the same import;
keep real timeliness breaches tracked while reverting. The index step: merge
triggers the Firestore index reconcile; approve its prod job and wait for READY
before shipping the worker (merge_pr.sh waits out these gates).
