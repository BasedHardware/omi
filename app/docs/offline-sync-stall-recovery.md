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

## Startup transfer admission (#23223)

The recovery coordinator must admit the account before its first asynchronous
native keep-alive acquisition. Reconciliation and device discovery do not need
a new upload first. Previously, `SyncProvider._admittedWorkGeneration` stayed
at -1 until a drain or manual upload started: startup could acknowledge a
completed server job without surfacing its conversation, and skip device
discovery and the coordinator's inventory refresh entirely.

`RecordingTransferCoordinator.onTransferAdmitted` now binds the existing
provider session generation synchronously for a new transfer run. Native
keep-alive acquisition and an extra hold for abandoned work remain separate:
neither re-admits an old pass, and an abandoned body blocks new admission until
it exits. Each reconciliation binds its callback to the admitted generation;
`SyncReconciler.poke` snapshots that callback with its phone owner before an
await. Reattachment cannot hand an old account's results to a replacement
callback. Discovery, refresh, drain and reconnect-retry reset respect that
same admitted generation. Auto-sync opt-out still allows discovery and
reconciliation but never an automatic upload.

No storage, job API, codec, timestamp, backend or firmware contract changes.
Queued server work stays pending; only an authoritative completed response
acknowledges it. This does not reprocess an audio file or invent its transcript.

The Discord screenshot shows the On the Way sync queue, not the on-device
transcription banner: 381 recordings, 42 hours of audio and nine almost ready.
Audio duration is not elapsed server-processing time. This screenshot alone
does not identify a missing handle, a queued server job, a failed upload or
whether all audio is retained. Existing #22484 addresses dead-handle poll
starvation; #21999 remains an open proposal for legacy sequenced-job staleness.
Neither is proof of this reporter's cause. Codemagic iOS build #4162 resolves
to 1.0.570+1430 at
`b859b78f821217c0df0082359cbcf70b6f29987d`; ancestry confirms #22484 is
included. Public iOS 1.0.570 was visible on the App Store on 2026-10-22.
The public page does not expose its binary build number, and this customer
only reported "latest", so their installed build remains unverified. Internal
TestFlight versions after 1.0.570 are not proof of a public release.

### Startup recovery checklist

- [x] Reproduce four production failures on unchanged main: missing completed
  conversation delivery, skipped device discovery, replacement-account polling
  after native acquisition, and callback adoption after reattachment.
- [x] Bind startup recovery at the existing transfer owner, preserve opt-out,
  and keep genuinely queued work pending without duplicate uploads.
- [x] Finish focused verification (41 passed), analyzer ratchet (unchanged
  baseline), mobile journeys (six journeys / 23 checks) and local preflight
  (25 checks). Full app run: 7,062 passed, four skipped, one unrelated paywall
  failure (`trial_paywall_free` finder in `trial_paywall_navigation_test.dart`),
  reproduced with the three production sync files restored to unchanged
  main `a8fdd3889d`. Repair the stale test to exercise the actual system-back
  and close dismissal controls during checkout; all four paywall navigation
  tests now pass with the restore, no-pop and late-completion assertions
  intact. No paywall production code or analyzer baseline changes. Remote CI
  must confirm the complete suite on the final commit.
- [ ] Merge and release the mobile fix after CI/review; this change itself
  needs no backend deployment or firmware release.
- [ ] Verify this customer's exact app build and diagnostic/job responses,
  then confirm the backlog declines and the corresponding conversations open.
  Keep recordings and app data intact while investigating; do not prescribe
  deletion, sign-out, reinstall or reset as queue recovery.

Focused regression: `flutter test
test/providers/sync_provider_background_admission_test.dart
test/providers/sync_provider_startup_reconciliation_test.dart
test/providers/sync_provider_session_generation_test.dart
test/services/wals/recording_transfer_coordinator_test.dart` (from `app/`).

## Request refusals and deliberate recovery (#23049)

A failed HTTP request is not proof that every recording in it is unusable.
The upload owner isolates a refused multi-file 400/413 request into single-file
attempts through the same serialized upload gate. Only a single-file refusal
becomes `uploadRejected`; a successful split does not report the original
request failure as a recording failure. Isolation is bounded to one original
request plus at most one attempt per member in that pass (batches contain at
most 20 files). Each iteration still reselects live-priority work, applies
capture-manifest completeness rules and checks the account generation. File
contents, ownership, capture times and consent are unchanged.

HTTP 401/403 is an authentication pause, not an audio verdict. Stop the current
drain, persist the exhausted retry budget and retain `miss` so a deliberate
retry or the existing connectivity recovery can acquire fresh authentication.
The single-file manual path persists the same pause. Do not recommend logout
or reinstall to obtain new credentials while recordings may remain local.

Historical `uploadRejected` rows do not retain enough evidence to decide
whether one bad sibling, request size or old credentials caused the refusal.
They remain excluded from automatic uploads. The existing explicit Try Again
controls now re-arm those rows, including the error card and when a tap is
coalesced into the transfer coordinator. The card, recording row and individual-file row share
the same retry classification. A mixed recording retries only eligible files.
On-device-only custody is excluded. Missing/corrupt files, confirmed unsupported
audio and the server's recovery-window verdict are not re-armed. Existing
play/share navigation stays available for retained audio.

The original Needs Attention no-op (#21828) is already released in iOS 1.0.566,
confirmed in its public App Store release notes on 2026-10-21. These additional
request-refusal changes need merge and a mobile release; they introduce no
backend API, firmware, bulk migration or data deletion. They do not bypass
server timestamp validation or recover an unknown true recording time.

The supplied support diagnostic excerpt reports stale phone-local backlog but
contains no upload response or terminal reason. It does not establish which
refusal (if any) affected the reported files or guarantee that they can decode.
No customer audio or account records were accessed or modified.

### Implementation / verification checklist

- [x] Reproduce blanket batch refusal, auth classification and unreachable
  persisted-refusal retry against unchanged main.
- [x] Isolate 400/413 members through the existing upload owner and gate.
- [x] Keep authentication failures retryable, durable and bounded.
- [x] Re-arm preserved request refusals only on an explicit user gesture.
- [x] Keep permanent audio/window verdicts and local-only custody excluded.
- [x] Verify focused provider/state/UI tests, analyzer and native simulator
  interaction; capture request counts, retained files and a valid WAV export.
- [x] Complete the final full-suite (7,016 passed / 9 skipped, plus 138 spine
  tests) and 25-check preflight after the error-card fix.
- [ ] Merge and release mobile after CI/review.
- [ ] Verify the customer's affected recordings and exported audio on the
  actual phone; keep the incident open until that outcome is known.

Regression commands (from `app/`):

```sh
flutter test test/unit/wal_upload_resilience_test.dart test/unit/wal_sync_display_state_test.dart test/providers/sync_provider_needs_attention_retry_test.dart test/providers/sync_provider_sync_wal_wake_test.dart test/pages/conversations/offline_sync_recording_blocks_test.dart test/widgets/sync_row_recovery_window_test.dart
```
