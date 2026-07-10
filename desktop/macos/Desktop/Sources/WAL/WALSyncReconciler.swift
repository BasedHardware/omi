import Foundation
import OmiWAL
import os.log

/// Resolves `.uploaded` WALs by polling `GET /v2/sync-local-files/{job_id}`.
/// Mirrors mobile `LocalWalSyncImpl.reconcileUploadedWals` (single pass, no blocking loop).
@MainActor
final class WALSyncReconciler {

  static let shared = WALSyncReconciler()

  private let logger = Logger(subsystem: "me.omi.desktop", category: "WALSyncReconciler")
  private let apiClient: APIClient
  private let fileExists: (WALEntry, URL?) -> Bool

  init(
    apiClient: APIClient = .shared,
    fileExists: @escaping (WALEntry, URL?) -> Bool = WALSyncReconciler.defaultFileExists
  ) {
    self.apiClient = apiClient
    self.fileExists = fileExists
  }

  private static func defaultFileExists(wal: WALEntry, walDirectory: URL?) -> Bool {
    guard let filePath = wal.filePath, let walDirectory else { return false }
    return FileManager.default.fileExists(atPath: walDirectory.appendingPathComponent(filePath).path)
  }

  /// Poll each distinct `jobId` among `.uploaded` WALs once and apply terminal transitions.
  func reconcileUploadedWals(
    wals: inout [WALEntry],
    walDirectory: URL?
  ) async -> Bool {
    var byJob: [String: [WALEntry]] = [:]
    for wal in wals where wal.status == .uploaded {
      guard let jobId = wal.jobId, !jobId.isEmpty else { continue }
      byJob[jobId, default: []].append(wal)
    }
    guard !byJob.isEmpty else { return false }

    var changed = false
    let entries = Array(byJob.keys)

    for jobId in entries {
      guard let members = byJob[jobId] else { continue }
      let memberIds = members.map(\.id)
      let fetch = await apiClient.fetchSyncJobStatus(jobId: jobId)
      let didChange = WALCloudSyncLogic.applyReconcileFetch(
        wals: &wals,
        memberWalIds: memberIds,
        fetch: fetch,
        fileExists: { wal in self.fileExists(wal, walDirectory) }
      )
      if didChange {
        changed = true
        logger.info("Reconciled job \(jobId) for \(memberIds.count) WAL(s)")
      }
    }

    return changed
  }
}
