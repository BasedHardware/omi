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
checkpoint. Each canary or apply call visits at most 2,000 rows. Clean stops can
resume on the same UTC day. A resumed canary counts all its prior writes toward
the 50-write limit. If the canary exhausts the range with zero writes, record
that outcome and close the pass. An uncertain write or incomplete readback
blocks the checkpoint until the operator reconciles the affected range. Disable
the writer switch and stop invocation of the runner to halt the rollout.

The operator can select `--scope discard-deletion` for a separately approved
pass that excludes deferred rows. Dry-run, canary and apply use the same scope
and fixed cutoff. An apply checkpoint must match its canary's scope. Both
scopes share the daily dry-run and apply limits. Keep the production forward
writer switch off while Release qualifies the readers for deferred rows.

The runner reads projected status and custody metadata. It checks the scanned
row revision and authoritative job, outbox, and tombstone state in the same
transaction that writes the status. Missing binding evidence leaves the affected
rows for their current owner. No transcript or audio is read or changed. The
canary writes at most 50 statuses. Each pass is capped at 450,000 inspected rows
and 3,499,000 document reads including the canary readback. The remaining daily
read allowance covers bounded aggregates. Record scanned, written and fenced
counts on SCA-3590. After apply, compare the bounded processing-older-than-six-hours
count against the stored baseline.
