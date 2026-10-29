# Error-class alerts

Alert-as-code detector for new or surging prod error classes. Motivation
(David, 2026-10-29): batch failures ran for a day or more as unwatched ERROR
lines before a ramp tripped on them (`contracts.py:45` VAD-span ValueError,
`batch_projection_followup` ContextVar errors, `SyncAssignmentConflict` record
target discarded, `invalid retained audio slice`). Each would have been obvious
from "new error class above N/h" or "class jumped 5x vs its 7-day baseline".

## Mechanism (and why not a log-based metric)

The sweep is a Cloud Scheduler job (`error-class-alerts-sweep`, every 15 min,
declared in `backend/deploy/scheduler/jobs.yaml`) POSTing
`/v2/error-class-alerts/sweep` on backend-sync, like the other backend-sync
scheduler sweeps. A log-based metric keyed by fingerprint is **not feasible**:
metric label extractors are single-entry regexes, while the fingerprint needs
multi-line traceback stitching and id-normalized message templates. Loki log
alerting was retired (`backend/charts/monitoring/LOG_CONSOLIDATION.md`), and
every Monitoring-policy provisioning entry point (`ensure_*` scripts under
`.github/scripts/`) is workflow-owned; the brief that commissioned this work
forbids `.github/` edits. The scheduled job reuses the Logging `entries.list`
REST read pattern from `services/capture_wedge.py`.

## Detection

- Scope: Cloud Run `backend`, `backend-sync`, `backend-sync-backfill`,
  `backend-integration`, `backend-listen`, plus `prod-omi-gke` pods
  `batch-pipeline-worker`, `pusher`, `backend-listen`.
- Window: the hour ending 20 minutes ago (the Logging view trails ~20 min).
- Fingerprint: exception type + raising site (file:line) + logger; for
  non-exception entries, app level + normalized message template + logger.
  Ids, numbers, addresses, quoted values and digit-bearing slugs are
  normalized out (`utils/error_class_fingerprint.py`).
- Container stderr is severity=ERROR at the Cloud Logging level regardless of
  app level, so app levels are parsed from the message: WARNING classes alert
  at doubled thresholds, INFO never alerts.
- Baseline: Redis (`errclass:baseline`) hourly buckets, 7 days, counts only;
  per-class alert dedupe (`errclass:alerted`) is a 6-hour TTL.
- Fire when a class is NEW and >= 20/h, or >= 50/h and >= 5x its baseline mean
  hourly rate.
- Every read error, 403, or truncation fails closed: no alerts that tick, and
  the outcome lands in `omi_error_class_sweep_total{outcome=...}`.

## Delivery

- `omi-error-class-firing` (Grafana): pages when
  `sum(omi_error_class_alert_firing) > 0` for 5m. The firing class fingerprint,
  hourly count, baseline mean and first-seen epoch are on the gauge labels and
  in the matching `error_class_alert` ERROR line in backend-sync logs.
- `omi-error-class-sweep-silent` (Grafana): dead-man. Pages when the sweep
  stops completing ok ticks (fewer than 4/hour), reports any non-ok outcome
  (including `permission_denied`), or the metric is absent.

Both rules live in `backend/charts/monitoring/alerts/error-classes.json` and
are provisioned by the existing Grafana alert provisioning workflow.

## IAM dependency (deploy-blocking, lead-owned)

backend-sync runs as `backend-runtime@based-hardware.iam.gserviceaccount.com`,
which currently has **no** `logging.read` role. Until the lead grants
`roles/logging.viewer` (or an equivalent narrow read grant) on
`based-hardware`, every sweep reports
`omi_error_class_sweep_total{outcome="permission_denied"}` and the dead-man
rule fires within the hour. That is deliberate fail-loud behavior: the
detector must not pretend to watch while it cannot read.

## Kill switch

Set the prod job's `state: PAUSED` in `backend/deploy/scheduler/jobs.yaml`
and run the scheduler reconcile; the sweeps stop within one tick and the
dead-man rule fires (that is expected — mute or pause
`omi-error-class-sweep-silent` for the maintenance window). No env change or
redeploy of backend-sync is needed.

## Parity

The same detector ran as a read-only m5 sentinel from 2026-10-29 (lane
`errclass`, `/Volumes/Ephemeral/scratch/errclass/sentinel.py` on m5) with
identical thresholds; its bus reports and per-run reports under
`/Volumes/Ephemeral/scratch/errclass/state/reports/` are the reference
baseline while this sweep seeds its own.
