# Settle retained batch obligations in existing transactions

David's 2026-11-07 16:24Z ruling (bus de6f03 and addendum c5c481) authorizes
code-owned settlement, with retained audio/custody and no provider replay.
The owner is omi-pipeline. [CONTRACT.md](../../../utils/batch_pipeline/CONTRACT.md)
owns shapes, fences, rollback, metrics and the Firestore cost model.

- Record admission's existing defer stamps a full fourteen-day barrier-failure
  window, then writes `dead/record_barrier_aged` in the same job write. Private
  OIDC `requeue-record` resets only that reason under the normal privacy fence.
  This composes with #24863's age-based barrier backoff in the same defer.
  The existing `BATCH_HELD_DEAD_LETTER_ENABLED=false` restores ordinary retries
  and stops record stock sampling. Net new env flags: zero; flag-budget count
  unchanged (lead2 bus 258db3). The barrier message is shared with its raise site;
  malformed/nonfinite/bool enqueue timestamps remain young/unknown and future
  timestamps have zero age. Backoff tests set their switch on every invocation
  (lead2 bus f85d74).
- Ghost settle stays OFF in every environment (default false). It was tripped
  off on 2026-11-08 at about 02:00Z (lead2 ea819b, f5a331): the ghost branch
  bypassed `_target_restorable`, so rows whose live record target was never
  persisted failed at the head of their owner chain (`SyncAssignmentConflict`
  'batch live target not persisted', about 465 per 15 min), blocking later
  conversations. Turning it on waits for the `_target_restorable` fix
  (lcwake/uicleanup) and a head-error baseline. Ghost settle keeps its own
  independent `BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED` switch; the held
  switch controls record dead-letter and assignment expiry.
- Committed assignment holds that fail the real-held gate use the same stamped
  window and expiry markers as other held receipts. Identity, privacy refusal,
  operator intent, timestamp and multipart-suffix fences remain. Existing held
  expiry metrics, alert and nightly redrive apply. Ghost classification precedes
  expiry; completed receipts awaiting discovery never stamp or expire, even when
  repair is off, capped or waiting on its age/recovery fence. Release still
  requires its original gates. `BATCH_HELD_DEAD_LETTER_ENABLED=false` stops new expiry.

The sync RunMonitoring keep rule and all dev/prod main/sync Stackdriver bridge
allowlists admit the three record-dead-letter metrics used by the alert. Tests
check the producer, declared inventory, both scrape profiles and every bridge.

- Record dead-letter rollback: set `BATCH_HELD_DEAD_LETTER_ENABLED=false` on record-serving roles; stamps, flips and stock sampling stop while ordinary retries/private requeue remain.
- Assignment expiry rollback: set `BATCH_HELD_DEAD_LETTER_ENABLED=false` on serving and worker roles; new held deadlines/expiry and GPU automatic maintenance stop while existing projection recovery/manual requeue remain.
- Ghost settle rollback: set `BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED=false` on both serving roles; ghost hint repairs stop while count-only classification and published results remain.

The held switch does not stop ghost settle; the ghost switch does not stop record
dead-letter or assignment expiry.

No deployed state or production data was inspected or changed for this patch.
