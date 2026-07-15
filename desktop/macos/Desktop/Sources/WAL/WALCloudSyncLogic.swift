import Foundation
import OmiWAL

/// Pure state transitions for WAL cloud upload — testable without network I/O.
enum WALCloudSyncLogic {

  /// Apply a server upload acknowledgement. Never marks `.synced` without 200/202 ack.
  static func applyUploadResult(
    to wal: inout WALEntry,
    result: UploadLocalFilesResult,
    now: Int = Int(Date().timeIntervalSince1970)
  ) {
    switch result {
    case .done:
      wal.status = .synced
      wal.jobId = nil
      wal.uploadedAt = 0
    case .queued(let jobId):
      wal.status = .uploaded
      wal.jobId = jobId
      wal.uploadedAt = now
    }
  }

  /// Re-apply reconciled WAL transitions onto the current live array by id.
  ///
  /// `reconcileUploadedWals` runs per-job network `await`s on the main actor, so it
  /// operates on a value-type SNAPSHOT of `wals` taken before those suspensions. During
  /// the awaits, other main-actor work (the chunk timer's `createWalFromCurrentFrames`,
  /// SD/WiFi `createSdCardWal`, write-completion mutations) can append new WALs to the
  /// live array. Assigning the snapshot back wholesale (`wals = workingWals`) silently
  /// drops those appended WALs — permanent data loss for an in-progress recording.
  ///
  /// This merges only the fields reconcile owns (`status`, `jobId`, `uploadedAt`),
  /// matched by id, and only when reconcile actually changed them. Entries present in
  /// `live` but absent from `snapshot`/`reconciled` (appended during the awaits) are
  /// preserved, and concurrent updates to other fields of untouched entries are not
  /// clobbered.
  static func mergeReconciledUploads(
    live: [WALEntry],
    snapshot: [WALEntry],
    reconciled: [WALEntry]
  ) -> [WALEntry] {
    var snapshotById: [String: WALEntry] = [:]
    for wal in snapshot { snapshotById[wal.id] = wal }
    var reconciledById: [String: WALEntry] = [:]
    for wal in reconciled { reconciledById[wal.id] = wal }

    var result = live
    for index in result.indices {
      let id = result[index].id
      guard let updated = reconciledById[id], let original = snapshotById[id] else { continue }
      guard updated.status != original.status
        || updated.jobId != original.jobId
        || updated.uploadedAt != original.uploadedAt
      else { continue }
      result[index].status = updated.status
      result[index].jobId = updated.jobId
      result[index].uploadedAt = updated.uploadedAt
    }
    return result
  }

  /// Reconcile one job's WAL members after a status fetch. Returns whether any WAL changed.
  @discardableResult
  static func applyReconcileFetch(
    wals: inout [WALEntry],
    memberWalIds: [String],
    fetch: SyncJobFetch,
    fileExists: (WALEntry) -> Bool,
    now: Int = Int(Date().timeIntervalSince1970)
  ) -> Bool {
    guard !memberWalIds.isEmpty else { return false }

    switch fetch.outcome {
    case .transient:
      return false

    case .notFound, .forbidden:
      var changed = false
      for walId in memberWalIds {
        guard let index = wals.firstIndex(where: { $0.id == walId }) else { continue }
        changed = true
        wals[index].jobId = nil
        if fileExists(wals[index]) {
          wals[index].status = .miss
        } else {
          wals[index].status = .corrupted
        }
        wals[index].uploadedAt = 0
        _ = now
      }
      return changed

    case .ok:
      guard let status = fetch.status else { return false }
      if !status.isTerminal {
        return false
      }
      if status.status == "completed" {
        var changed = false
        for walId in memberWalIds {
          guard let index = wals.firstIndex(where: { $0.id == walId }) else { continue }
          changed = true
          wals[index].status = .synced
          wals[index].jobId = nil
          wals[index].uploadedAt = 0
        }
        return changed
      }
      // failed / partial_failure — revert to miss for re-upload when file remains.
      // We requeue both cases: for partial_failure, the failed segments may be
      // retryable on the next upload (transient backend failures). Re-uploading
      // successful segments is safe — the backend dedupes by conversation/timestamp.
      var changed = false
      for walId in memberWalIds {
        guard let index = wals.firstIndex(where: { $0.id == walId }) else { continue }
        changed = true
        wals[index].jobId = nil
        wals[index].uploadedAt = 0
        wals[index].status = fileExists(wals[index]) ? .miss : .corrupted
      }
      return changed
    }
  }
}
