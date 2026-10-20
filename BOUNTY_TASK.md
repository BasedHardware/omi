# Bounty Objective: [Bounty Proposal] Fix LocalWalSyncImpl async flush frame-buffer wipe & stale device clear on reconnect (#22912)
Target: BasedHardware/omi Issue #22940
URL: https://github.com/BasedHardware/omi/issues/22940

## Issue Description
## Scope & Problem Statement

In #22912, `test/unit/capture_live_recovery_test.dart` (`device reconnect finishes stopping the old session before starting the new one`) fails with `Expected: <210>`, `Actual: <200>` (losing the 10 `orphanPendant` frames emitted while the previous session stop is in flight):

1. **`LocalWalSyncImpl.onAudioCodecChanged` & `stop` (`app/lib/services/wals/local_wal_sync.dart`):**
   - `_drainPendantTail(generation)`, `_chunk(generation)`, and `_flush(generation)` are scheduled across separate `_enqueueBuffer` calls, and `_frames = []; _pendingPhoneOnly = false; _frameSynced = [];` is executed **after** `await _enqueueBuffer(() => _flush(generation))` returns.
   - Because `onFrameCaptured` is synchronous and does not wait on `_bufferQueue`, frames arriving while `_flush(generation)` awaits disk I/O (`File.writeAsBytes` / `_saveWalsToFile`) are appended to `_frames` under the old `_codec` and `_sourceClockEpoch`, and then wiped out when `_flush` finishes and `_frames = []` runs.
2. **`CaptureController._stopDeviceSessionBody` (`app/lib/services/capture/capture_controller.dart`):**
   - `_stopDeviceSessionBody(cleanDevice: true)` calls `_updateRecordingDeviceBody(null)` after `await _wal.getSyncs().phone.finalizeCurrentSession()` without checking `!_deviceIdentityStale(deviceRevision)`, clobbering any newer `_recordingDevice` set by `updateRecordingDevice(pendant)` while `finalizeCurrentSession()` was awaiting disk I/O.

## Deliverables & Verification
- Fix `LocalWalSyncImpl.stop` and `LocalWalSyncImpl.onAudioCodecChanged` so `_drainPendantTailFrames`, `_chunk`, `_frames` reset, and `_codec`/`_sourceClockEpoch` rotation happen synchronously before `await _flush(generation)` yields for disk I/O.
- Guard `_updateRecordingDeviceBody(null)` in `_stopDeviceSessionBody` with `!_deviceIdentityStale(deviceRevision)`.
- Add deterministic unit test coverage in `app/test/unit/local_wal_sync_test.dart` verifying that frames captured while `persistWals` disk I/O is in flight during `onAudioCodecChanged` are preserved with the updated `sourceClockEpoch`.
- **Implementation PR:** #22939 (Fixes #22912)

---
**Designated Payout Rail — EVM (Base / Arbitrum / Polygon USDC):** `0x484eD370DEd0D36e36AAD469a2AFE5D69B1A005D`


## Instructions for Kuro (Autonomous Solver):
1. Use skills: `systematic-debugging` and `code-review-and-quality`.
2. Inspect the repository structure, locate relevant files, and understand the bug/feature.
3. Apply the minimal, robust fix or implementation.
4. Run any existing test suites or linters in the workspace.
5. Ensure the fix adheres to the project's existing code style.
6. When done, output a summary of files modified and verification results.
