# Settle parked conversation status (SCA-3590)

A lazy desktop intake can store the transcript and title as completed while the
existing deferred flag still reserves enrichment for the first detail open.
Opening claims the flag and returns processing while enrichment runs. A failed
attempt re-arms the same completed/deferred state so the next open can retry.
Desktop detail follows each server response, including the first response after
a cold cache open that discarded the deferred flag. Polls from desktop do not
claim enrichment, so a failed attempt can show its completed/deferred state
and retry on a later open.
An accepted deletion settles a previously processing row in its existing
tombstone transaction. The status changes preserve the discard and deletion
flags and the existing restore and erasure contracts.

The default-on `CONVERSATION_PARKED_TERMINAL_STATUS_ENABLED` switch controls new
parked status writes. Set it to `off` to stop them. First-open still accepts
either stored status, including rows already migrated.

## Historical migration

Use `backend/scripts/settle_parked_conversations.py` with a fixed six-hour-or-older
UTC cutoff and private checkpoints. Run one `dry-run` with `ro-prod` before apply.
After the compatible revision is serving and the full migration review is clear,
run `canary` with `prod-operator` and a separate checkpoint. Review its exact
status-only readback before running `apply --accept-canary` with that same apply
checkpoint. Each apply call visits at most 2,000 rows. Clean batch stops can
resume. An uncertain write or incomplete readback leaves the checkpoint blocked
until the operator reconciles the affected range. Disable the writer switch and stop invocation of the runner
to halt the rollout.

The runner reads projected status and custody metadata. It checks the scanned
row revision and authoritative job, outbox, and tombstone state in the same
transaction that writes the status. Missing binding evidence leaves the affected
rows for their current owner. No transcript or audio is read or changed. The
canary writes at most 50 statuses. Each pass is capped at 450,000 inspected rows
and reserves at most 3.5M document reads including the canary readback. Record
the scanned, written, and fenced counts on SCA-3590 and compare the bounded
processing-older-than-six-hours count against the stored baseline after apply.
