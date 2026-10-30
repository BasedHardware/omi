import Foundation

// MARK: - Cache Maintenance

extension MemoriesViewModel {

  /// Reconcile's server page transport. Extracted from `MemoriesPage.swift`
  /// to keep that file inside its line-count ceiling; behavior unchanged.
  func fetchReconcilePage(
    limit: Int,
    cursor: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> APIClient.MemoryListPage {
    if let reconcilePageFetch {
      return try await reconcilePageFetch(limit, cursor, authorizationSnapshot)
    }
    // Archive is included so the pulled population matches the scope the prune
    // claims; a default-scope pull would read Archive rows as absent.
    return try await APIClient.shared.getMemoriesPage(
      limit: limit,
      cursor: cursor,
      includeArchive: true,
      authorizationSnapshot: authorizationSnapshot)
  }

  /// Give stranded local-only rows a bounded fate: purge them once per launch
  /// per user, next to the reconcile. See
  /// `MemoryStorage.purgeStaleLocalOnlyMemories(olderThan:now:)` for why rows
  /// younger than the bound are kept.
  func purgeStaleLocalOnlyMemoriesIfNeeded() async {
    let userId = UserDefaults.standard.string(forKey: .authUserId) ?? "unknown"
    guard !LocalOnlyPurgeLatch.purgedUserIDs.contains(userId) else { return }
    do {
      let purged = try await MemoryStorage.shared.purgeStaleLocalOnlyMemories()
      LocalOnlyPurgeLatch.purgedUserIDs.insert(userId)
      if purged > 0 {
        log("MemoriesViewModel: Purged \(purged) stranded local-only memories (older than 30 days)")
      }
    } catch {
      // No latch on failure: retry on the next load this launch or the next launch.
      logError("MemoriesViewModel: Stale local-only purge failed (will retry)", error: error)
    }
  }

  /// Purge runs once per launch per user, mirroring the reconcile latch.
  @MainActor private enum LocalOnlyPurgeLatch {
    static var purgedUserIDs: Set<String> = []
  }
}
