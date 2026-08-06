/// Screen-lock sync continuation policy (#7221).
///
/// [RecordingTransferCoordinator] is foreground-only by design (#9763). When the
/// user locks the screen with a large upload/reconcile backlog, Flutter is
/// suspended within seconds and overnight drain stalls (~5% of 1000+ files).
///
/// This policy decides whether a **bounded cloud-only grace pass** should run
/// while iOS still grants background execution time. BLE device drains stay
/// deferred — they need an active Flutter BLE loop and fight platform limits.
library;

/// What to do when the app leaves the foreground with pending sync work.
enum SyncContinuationAction {
  /// Wait for the next foreground/startup wake (default #9763 contract).
  deferToForeground,

  /// Run one cloud upload + server-reconcile pass; skip BLE device drains.
  runCloudGracePass,
}

/// Max local-upload batches for one screen-locked grace pass.
///
/// Each batch is at most 5 WALs (`local_wal_sync`). Three batches ≈ 15 files —
/// enough to make overnight progress under `beginBackgroundTask` without
/// attempting a full 1000+ backlog in one suspended window.
const int kScreenLockedCloudGraceMaxBatches = 3;

/// Whether locking the screen should start a cloud-only grace wake.
///
/// [hasMissLocalWals] — phone-disk WALs still `miss` (bytes ready to upload).
/// [hasUploadedWals] — WALs waiting on server job reconcile ("processing").
/// [autoUploadEnabled] — user auto-sync preference (userRetry is foreground-only).
SyncContinuationAction decideScreenLockedSyncContinuation({
  required bool autoUploadEnabled,
  required bool hasMissLocalWals,
  required bool hasUploadedWals,
}) {
  // Uploaded jobs must keep moving or the Sync UI stays at "processing 0%".
  if (hasUploadedWals) return SyncContinuationAction.runCloudGracePass;
  if (autoUploadEnabled && hasMissLocalWals) {
    return SyncContinuationAction.runCloudGracePass;
  }
  return SyncContinuationAction.deferToForeground;
}
