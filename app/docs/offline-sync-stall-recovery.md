# Offline Sync stall recovery

## One custody and recovery pipeline

Pendant audio reaches a durable phone WAL before normal cloud upload. An upload
acknowledgement is not transcription completion: the existing job poller and
`LocalWalSyncImpl.reconcileUploadedWals` own subsequent status reconciliation.
Never delete Pending or All to make a processing counter disappear.

The Android build 1.0.558 (1400) reports in #21279 and Discord describe several
stages, not a proven single deadlock. These fixes have distinct boundaries:

- Merged #21387 installs poll cooldowns after 429; its Delete Pending change
  is explicit destructive cleanup, not recording recovery.
- Merged #21319 packs short WALs into bounded upload batches. It does not
  change BLE speed or speaker quality.
- Merged #21755 repairs legacy backfill dispatcher ownership. Its production
  repair script requires a separate operator decision; this change runs none.
- Merged #21823 quarantines exhausted batch-worker items; it does not replace
  recovery of phone-local recordings or validate this customer's queue.
- #21362 recovers retained uploads with missing job handles and preserves
  honest processing/attention states. It needs client releases after merge.

## Ring transfer liveness

`RingStorageSyncImpl` handles firmware advertising the 3.0.20+ ring protocol.
Previously, READ_BEGIN cancelled the only short timeout. A connected peripheral
that then stopped sending data could hold the transfer until the 30-minute
overall deadline. This is reproduced with the production transfer owner and a
synthetic device; it is not a measurement of the customer's reported 1.4 KB/s.

Keep the existing five-second initial response deadline and 30-minute overall
bound. After a valid BEGIN or nonempty DATA, require further DATA within 15
seconds, matching the legacy SD transfer's idle window. Repeated BEGIN, ACK,
INFO and empty DATA are not progress. Observe arrival before queued custody or
disk work, so slow local I/O does not look like a silent radio. A valid DONE
arrival cancels the radio idle deadline even if its validation is queued behind
custody I/O; the overall deadline still bounds that work.

On idle expiry, stop new notification admission and send STOP on the original
connection/epoch. Drain already accepted notifications and flush complete
records through the existing durable WAL registration. Leave the source WAL
pending; never fabricate DONE, synced state or a frontier advance. Existing
capability-gated custody rules remain authoritative. Older firmware can reclaim
data on BLE delivery before app durability; this change does not repair that
firmware risk or guarantee recovery of incomplete records.

## Implementation / acceptance checklist

- [x] Bound inactivity after BEGIN and after DATA, not just initial response.
- [x] Ignore control chatter and cancel superseded/completed idle timers.
- [x] Keep received records when local custody work is delayed past idle expiry.
- [x] Retain the pending WAL and send no unproven advance after an idle stop.
- [x] Keep healthy DONE and normal durable frontier advancement working.
- [x] Preserve read-command errors with their original stack, cause and phase
  in diagnostic exports while still running transfer cleanup.
- [x] Wait for read admission in custody fixtures instead of guessing with a
  startup sleep; keep the incremental durable-advance assertion unchanged.
- [x] Run ring/custody/capture regressions (129 passed), the selected capture
  journey (3 checks passed), the full app analyzer ratchet and local preflight
  (25 checks passed).
- [ ] Release a mobile build containing the fix after merge.
- [ ] Customer retest with firmware, timestamp and diagnostics: measure BLE
  throughput, verify capture continues/resumes, inspect actual queued job
  responses and confirm retained recordings reach terminal processing.

No customer diagnostic export or firmware version was supplied for the Discord
0/127 case. These tests do not confirm that case's cause, cloud-worker state,
physical microphone behavior, recap dependency or recoverability. A passing
software regression and a merged PR are not a verified customer resolution.
