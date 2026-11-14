# Held staging input expiry (lead2 9a5190)

Option A preserves the 30-day staging privacy ceiling. The existing held sweep
retains eligible GPU/assignment jobs as `dead/input_expiring` at current-object
age 29 days. The existing timeliness exporter gains a staging-scoped age leg
and a warning above 21 days. Enqueue time proxies staging for legacy objects;
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

## Follow-up review (lead2, f1df857427d0)

Both custody findings are confirmed: exact-bundle replacement changed the URI
without changing the age anchor, and the default-on kill had no explicit deploy
binding. Repair now stamps `audio_staged_at`; expiry, operator selection and the
age exporter prefer it to legacy `enqueued_at`. The enqueue clock stays intact.
Initial admission already attaches newly staged audio at enqueue; the other
`audio_uri` assignment in `database/record_partial.py` attaches an encrypted
coordinator plan while `record_pending`, rather than restaging a held audio
object. That path remains outside held-input expiry.

The runtime base and prod overlay explicitly bind the kill true on all five
existing held-sweep serving surfaces. Listen dev/prod and worker default,
dev/staging/prod charts bind it as well, including both worker GPU deployments.
The runtime manifest and feature-flag registry are regenerated from source.

The correctness finding is also confirmed: the ordinary name-cursor pass could
exceed the one-day expiry margin. Urgency now runs first using two oldest-first
indexed streams, each capped at 128 rows, for legacy enqueue and current restage
anchors. Independent age cursors advance over filtered/fenced rows. For the
review's 22,583-row cohort the bounded pass is 14h45m, rather than 58h50m at 32
rows per five minutes. No timer or ordinary page-size change is made. The new
prod/dev restage-clock composites are in the index registry and generated
manifest; existing index/deploy guards enforce them. No legacy backfill is
needed. The earlier coalesced-query question is resolved by the two streams.
