# Alert-only pipeline drain guards

Adds source definitions for upload-admission size-class 503s, exhausted Firestore contention, owner-drain
progress and held-row age warnings. Runtime behavior is unchanged apart from four indexed oldest-row reads
at the existing timeliness sampling cadence; the new held-stock gauge has no epoch or 24h cohort cutoff.

No new flag, runtime gate, scheduler, ramp, rollback or autoscaling input is added. Log metrics and Grafana
rules require separate operator admission. No production access, provisioning or deployment is part of this PR.
Thresholds, evidence, verification and rollback: [policy](../../../charts/monitoring/batch-projection/pipeline-alerts.md).
Existing contract: [batch pipeline](../../listen_pusher_pipeline.mdx).
