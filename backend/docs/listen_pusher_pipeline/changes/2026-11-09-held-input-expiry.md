# Held staging input expiry (lead2 9a5190)

Option A preserves the 30-day staging privacy ceiling. The existing held sweep
retains eligible GPU/assignment jobs as `dead/input_expiring` at enqueue age
29 days. The existing timeliness exporter gains a staging-scoped enqueue-age
leg and a warning above 21 days. Enqueue time proxies staging at admission;
no GCS metadata or lifecycle change is involved.

The default-on `BATCH_INPUT_EXPIRING_ENABLED` kill controls new transitions;
manual recovery remains usable with it off. No record-pending or timer change,
audio deletion, provider call, or automatic terminal resurrection is added.
The existing failure/custody-repair wire protocol and checked operator GPU
requeue / target-restorable assignment release remain the exits.

Contract: [held staging input expiry](../../listen_pusher_pipeline.mdx#held-staging-input-expiry).
Operator commands and rollback: [runbook](../../runbooks/held-staging-inputs.md).
Hermetic evidence: `tests/unit/test_batch_input_retention.py`, plus the retained
dead-letter, lifecycle writer, retention contract, telemetry and alert suites.
No deployment or live operator execution is claimed.
