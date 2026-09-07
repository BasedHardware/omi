import Foundation

/// A Rewind frame with its bytes loaded, ready to hand to a model request or
/// stage as a chat attachment.
struct LoadedRewindFrame: Equatable {
  let data: Data
  let appName: String
  let windowTitle: String?
  let timestamp: Date
}

/// Loads Rewind frames for chat surfaces that need "the screen" without
/// photographing Omi itself.
///
/// The periodic capture already skips Omi and the user's excluded apps, but
/// that guarantee is only forward-looking: removing an app from the exclusion
/// list never purges its existing rows (`RewindSettings.excludedApps` writes
/// defaults and generation markers only, and the store has no delete-by-app),
/// so pre-exclusion password-manager rows persist in the database. Exclusion
/// is therefore re-applied at READ time, here, where every consumer of frames
/// for chat funnels through.
@MainActor
final class RewindFrameLoader {
  static let shared = RewindFrameLoader()

  /// Names Omi ships under. `RewindSettings.defaultExcludedApps` already lists
  /// these, but that list is user-editable and a frame of Omi describing
  /// itself is the exact defect this loader exists to prevent, so they are
  /// filtered unconditionally rather than trusted to the setting.
  static let omiAppNames: Set<String> = [
    "Omi Computer", "Omi Beta", "Omi", "Omi Dev",
  ]

  struct Environment: Sendable {
    /// Newest-first rows from the Rewind store.
    var recentScreenshots: @Sendable (_ limit: Int) async throws -> [Screenshot]
    /// Path of the video chunk still being written; its frames cannot be
    /// decoded mid-write.
    var activeChunkPath: @Sendable () async -> String?
    /// Decodes one row's bytes (JPEG), retrying after storage initialization.
    var loadData: @Sendable (Screenshot) async throws -> Data
    /// The user's capture exclusion list.
    var excludedApps: @Sendable () -> Set<String>

    /// Computed rather than stored: every access re-wraps the same static
    /// dependencies, and a stored global of even a Sendable closure type is
    /// the kind of shared mutable state this loader exists to avoid.
    static var live: Environment {
      Environment(
        recentScreenshots: { limit in
          // The store opens lazily — on a fresh install where the capture loop
          // has never run, nothing else may have opened it, and the row query
          // would throw not-initialized and read as "no frames". Idempotent
          // and a no-op when the pool is already open for this owner.
          try await RewindDatabase.shared.initialize()
          return try await RewindDatabase.shared.getRecentScreenshots(limit: limit)
        },
        activeChunkPath: { await VideoChunkEncoder.shared.currentChunkPath },
        loadData: { screenshot in
          try await ScreenContextWorkContextBuilder.loadScreenshotDataEnsuringStorage(for: screenshot)
        },
        excludedApps: { RewindSettings.shared.excludedApps }
      )
    }
  }

  private let environment: Environment

  init(environment: Environment = .live) {
    self.environment = environment
  }

  /// Whether a row may ever be surfaced: not Omi itself, not a capture-excluded
  /// app (privacy — exclusion is not retroactive), and not a frame inside the
  /// video chunk still being written.
  func isAttachable(_ screenshot: Screenshot, activeChunkPath: String?) -> Bool {
    guard !Self.omiAppNames.contains(screenshot.appName) else { return false }
    guard !environment.excludedApps().contains(screenshot.appName) else { return false }
    if screenshot.usesVideoStorage, let chunk = screenshot.videoChunkPath, chunk == activeChunkPath {
      return false
    }
    return true
  }

  /// Newest-first attachable rows, metadata only — no decode. Cheap enough to
  /// consult per send for a staleness decision, and the picker's row source.
  func attachableRows(limit: Int) async -> [Screenshot] {
    let rows = (try? await environment.recentScreenshots(limit)) ?? []
    let activeChunk = await environment.activeChunkPath()
    return rows.filter { isAttachable($0, activeChunkPath: activeChunk) }
  }

  /// The newest attachable row, metadata only.
  func latestAttachableRow(limit: Int = 25) async -> Screenshot? {
    await attachableRows(limit: limit).first
  }

  /// The newest attachable frame with its bytes loaded. A row whose bytes fail
  /// to load falls through to the next older one; rows are newest-first, so
  /// the first one past the age bound ends the search.
  func loadLatestAttachableFrame(
    limit: Int = 25,
    maxAgeSeconds: TimeInterval? = nil,
    now: Date = Date()
  ) async -> LoadedRewindFrame? {
    for row in await attachableRows(limit: limit) {
      if let maxAgeSeconds, now.timeIntervalSince(row.timestamp) > maxAgeSeconds { return nil }
      guard let data = try? await environment.loadData(row) else { continue }
      return LoadedRewindFrame(
        data: data,
        appName: row.appName,
        windowTitle: row.windowTitle,
        timestamp: row.timestamp
      )
    }
    return nil
  }

  /// Bytes for a row the user picked.
  func loadData(for row: Screenshot) async -> Data? {
    try? await environment.loadData(row)
  }

  /// Bytes for a row the picker offered by id. Re-reads the newest rows to
  /// resolve the id: the query is a bounded indexed read, and the picker's
  /// rows are metadata only, so this keeps the row model free of storage
  /// types.
  func loadData(forRowID rowID: Int64, limit: Int = 25) async -> Data? {
    guard
      let row = await attachableRows(limit: limit).first(where: { $0.id == rowID })
    else { return nil }
    return await loadData(for: row)
  }
}
