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
      guard
        updated.status != original.status
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

    case .notFound, .forbidden, .unauthorized:
      // `.unauthorized` = the status poll could not be authenticated (token mint
      // failed, or a stale 401). Revert to `.miss` like the other durable
      // failures so the authenticated upload path re-uploads and refreshes auth;
      // the poll itself must not invalidate the session (INV-AUTH-1).
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

  /// Synced WALs whose recording start predates the retention cutoff — safe to
  /// delete. Gated on `.synced` (a confirmed backend ack; never `.miss`/
  /// `.uploaded`/`.corrupted`, which still need upload) AND older than the
  /// cutoff, so local audio is only reclaimed after the cloud has it and a
  /// retention buffer has elapsed. Pure so the delete/keep boundary is testable.
  ///
  /// `hardCutoffTimestamp` additionally ages out WALs that never reached
  /// `.synced`. A signed-out, offline, or persistently upload-failing user
  /// accumulates `.miss`/`.uploaded`/`.corrupted` entries that the synced-only
  /// filter kept forever (~30 MB/h of audio); past the hard cutoff the local
  /// copy is reclaimed even though the cloud never acknowledged it.
  static func cleanupCandidates(
    wals: [WALEntry],
    cutoffTimestamp: Int,
    hardCutoffTimestamp: Int? = nil
  ) -> [WALEntry] {
    wals.filter { wal in
      if wal.status == .synced { return wal.timerStart < cutoffTimestamp }
      guard let hardCutoffTimestamp else { return false }
      return wal.timerStart < hardCutoffTimestamp
    }
  }

  /// Oldest-first WALs to evict so the on-disk audio total falls back under
  /// `byteCeiling`. Age cutoffs alone cannot bound the directory: a user who
  /// records continuously while offline exceeds any window's byte total long
  /// before the window elapses, so this is the backstop that actually caps disk.
  /// `.inProgress` entries are never evicted — they are the live recording.
  static func overflowCandidates(
    wals: [WALEntry],
    byteCeiling: Int64,
    fileSize: (WALEntry) -> Int64
  ) -> [WALEntry] {
    let evictable = wals.filter { $0.status != .inProgress }
    var total = evictable.reduce(Int64(0)) { $0 + fileSize($1) }
    guard total > byteCeiling else { return [] }

    var evicted: [WALEntry] = []
    for wal in evictable.sorted(by: { $0.timerStart < $1.timerStart }) {
      guard total > byteCeiling else { break }
      total -= fileSize(wal)
      evicted.append(wal)
    }
    return evicted
  }
}
