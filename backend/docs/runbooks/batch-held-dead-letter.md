# Retained batch held dead letters

GPU batch holds (`quarantined`, `recovery_state=held|failed_held`,
`quarantine_reason=worker_failed`) gain a seven-day `held_deadline_at`.
The initial quarantine and each failed recovery settlement stamp a full window.
A legacy row without the field receives a full window at its first eligible
sweep; capture/enqueue age is never used to expire old stock immediately.

`BATCH_HELD_DEAD_LETTER_ENABLED` is default **on**. False stops new stamps
and automatic held maintenance without changing legacy quarantine writes.
The private requeue endpoint remains available. Rollback: set this flag false
on the serving and worker roles; revert the PR to remove the code. Expiry sets
`merge_pending=true` in the same transaction as `state=dead`, so the existing
`POST /v2/batch-pipeline/redrive-dead` route (`Scheduler.redrive_dead`) accepts
these rows even after the new route and nightly helper are reverted. It retains
`dead_letter_reason=held_expired`, `held_deadline_at` and `held_expired_at`.
No backward data rewrite or pre-revert drain is needed for these rows. The
rolled-back service requires an authorized operator to invoke its existing
re-drive; it does not run the new nightly pass. Deployment declarations are
source only; this change does not deploy.

The existing serving maintenance leader scans 32 held rows every five minutes,
with a durable document-key cursor. The transaction rechecks content ownership,
privacy generation, dormant held state, no result (including the result receipt),
no worker token, and an expired lease. Active recovery/operator intents block it.
Eligible expired rows become `state=dead`, `dead_letter_reason=held_expired`,
with `held_expired_at` and `merge_pending=true` for legacy re-drive. They retain
their encrypted source references, intent and attempt history and all other fields. No storage call, TTL, audio deletion,
conversation-status write or privacy-fence change occurs.

A nightly UTC pass re-attempts only `dead(held_expired)` rows expired before
that midnight. It shares the maintenance leader, uses the same 32-row page and
five-minute cadence, and resumes its durable cursor across restarts until the
pass ends. Each row goes through `RecoveryStore.checked` and the sanctioned
`Scheduler.requeue_quarantined_in_transaction` CAS into the GPU queue. Crash
before checkpoint replays safely; concurrent callers cannot append twice.
Normal scheduler admission, policy, capacity and attempt accounting still apply.
Provider-STT holds never enter the GPU DRR ring: their vendor-paid attempt
protocol needs a separate sanctioned re-drive, so expiry/requeue refuse them.
The state-table deadline xfail remains for those unstamped provider entry paths
and the deliberate flag-off entry. No projection state is added in phase 4a.

Authorized operators can call the existing private worker-OIDC surface:
`POST /v2/batch-pipeline/requeue-quarantined` with
`{"stage":"prod|dev","segment_id":"<retained segment>"}` using the configured
worker identity. It accepts quarantined holds and held-expired dead letters;
`accepted=false` is a fenced or already advanced row. It performs no provider
or artifact IO. Repair missing inputs through the existing artifact restoration
path first. Do not clear account-deletion, privacy or content ownership fences.

Status readers keep dead-held units in the held custody answer and partial
accounting. They never acknowledge full completion merely because a hold aged.
Healthy siblings remain visible. `privacy_blocked`, projection holds, BYOK and
finalization dead-letter tools remain outside this change.

`omi_batch_held_expired_total` counts committed expiry transitions;
`omi_batch_held_expired_units` is all retained dead stock for this explicit new
reason, and `omi_batch_held_expired_observed_at_seconds` timestamps successful
stock samples. The three exact metric families are pinned in both dev/prod
Cloud Run exporter releases (main and sync/integration), because serving
maintenance emits them on CPU hosts. Ship those metrics-egress declarations
with the alert through the existing release path; no live egress or alert
delivery was qualified here. The agent-tier `omi-batch-held-expired-volume` rule alerts on
fresh stock >100 or >10 expirations in 30 minutes for five minutes. Unrelated
legacy dead rows do not count, and this rule never pages. These are initial
operator thresholds, not production-calibrated measurements. Inspect worker
failure causes and nightly progress before requeueing. A stock sample is not
proof of user-visible recovery; verify real transcript publication separately.

Not measured here: production stock, dwell distribution, vendor spend, live
nightly execution, alert delivery or deployed behavior. Tests use synthetic
identities and offline/emulator paths only.

## Projection receipts (phase 4b)

Assignment-quarantined result receipts get the same seven-day `held_deadline_at`
when persisted. The release scan gives legacy eligible holds a full window from
first examination. Only settled assignment holds age-expire; original ownership,
operator-intent, privacy and target-restorability checks still apply. Persisted
multipart suffixes and privacy holds never age-expire.

Expiry retains `projection_state=quarantine_held` and adds `held_expired_at` and
`held_expired_reason=held_expired`. The result/transcript payload, quarantined
receipt, proven parts, audio references, job and owner watermark are unchanged.
There is no TTL, deletion or conversation-status change. The marker subset remains
visible through ordinary held obligations and the `held_expired_rows` leg.

The pre-4b release path rejects attempts at or above `MAX_RELEASE_ATTEMPTS=3`.
When an aged, still-unrestorable hold expires at that cap, the same transaction
saves its count in `held_expired_release_attempts` and resets
`projection_release_attempts` to zero. This one-time CAS keeps the row eligible
for the unchanged old release path; marked rows are never repeatedly reset.
Ordinary uncapped holds retain their counter. No reset releases an unrestorable
target or changes the receipt. A subsequent release uses the existing watermark
and held-parts reset. A fresh assignment hold starts a fresh deadline.

On the existing maintenance leader, a separate durable cursor rechecks 32 marked
receipts per five-minute continuation of a nightly UTC pass. Only previous-day
expirations qualify, using the same target-restorability predicate. Unrestorable
rows remain held. Checkpoints follow work and unfinished scans retain their
cursor across midnight; crashes replay safely and poison rows cannot pin pages.
The ordinary release scan can also release marked rows as soon as their targets
become restorable. Its existing durable cursors are unchanged.

`BATCH_HELD_DEAD_LETTER_ENABLED=false` stops new stamps and expiry. Already marked
rows remain discoverable and releasable by the unchanged pre-4b scan and release
implementation, including capped rows normalized during expiry. The new nightly
helper also continues with the flag off. A full code revert needs no metadata
rewrite or retained new helper. Frozen pre-change code is exercised by unit and
loopback Firestore tests with the flag off, before and after target restoration.

The existing agent-only `omi-batch-held-expired-volume` alert includes job stock
and projection rows with `projection_state=quarantine_held` and
`held_expired_reason=held_expired`. Unrelated legacy holds do not count. Samples
must be fresh; thresholds remain synthetic 4a defaults, not measured production
levels. No human paging, GCP access or production measurement was performed.
