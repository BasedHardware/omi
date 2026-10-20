import XCTest

@testable import Omi_Computer

/// A memory deleted on another device must stop appearing on this one.
///
/// The reconcile used to pull the default scope and then refuse to prune, so
/// nothing on the desktop ever removed a row whose backend memory was gone. The
/// cache only grew stale, which is what "they delete on the app, but they do not
/// sync across devices" was. Pruning is only safe when the pull is complete, so
/// these tests pin both directions: absent rows go, and an incomplete pull is
/// treated as no evidence rather than as proof of absence.
@MainActor
final class MemoriesCacheReconcilePruneTests: XCTestCase {
  private var userDir: URL?
  private var authSnapshot: RewindStorageTestIsolation.AuthSnapshot?
  private var testUserId: String?

  override func setUp() async throws {
    authSnapshot = RewindStorageTestIsolation.captureAuthSnapshot()
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memories-reconcile-prune")
    userDir = fixture.userDir
    testUserId = fixture.testUserId
    RewindStorageTestIsolation.signInForTests(userId: fixture.testUserId)
    // Align the process-global owner authority with this throwaway user, the
    // way a real signed-in session does, so the reconcile's owner fence
    // (capture → isAuthorizationCurrent) observes a stable owner.
    RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
    RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: fixture.testUserId)
  }

  override func tearDown() async throws {
    if let authSnapshot {
      RewindStorageTestIsolation.restoreAuthSnapshot(authSnapshot)
      RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
      RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: authSnapshot.userId)
    }
    if let userDir {
      await RewindStorageTestIsolation.tearDown(userDir: userDir)
    }
  }

  private func page(
    _ memories: [ServerMemory],
    nextCursor: String? = nil,
    truncated: Bool = false
  ) -> APIClient.MemoryListPage {
    APIClient.MemoryListPage(
      memories: memories,
      nextCursor: nextCursor,
      canonicalLifecycleExposed: false,
      deviceScopeSupported: true,
      defaultMemoryDeleteSupported: true,
      truncated: truncated
    )
  }

  private func makeViewModel(
    returning page: APIClient.MemoryListPage
  ) -> MemoriesViewModel {
    let viewModel = MemoriesViewModel()
    viewModel.reconcilePageFetch = { _, _, _ in page }
    return viewModel
  }

  private func makeMemory(id: String, tier: MemoryLayer) -> ServerMemory {
    ServerMemory(
      id: id,
      content: "Memory \(id)",
      category: .system,
      tier: tier,
      createdAt: Date(timeIntervalSince1970: 1),
      updatedAt: Date(timeIntervalSince1970: 2),
      conversationId: nil,
      reviewed: false,
      userReview: nil,
      visibility: "private",
      manuallyAdded: false,
      scoring: nil,
      source: "desktop",
      confidence: nil,
      sourceApp: nil,
      contextSummary: nil,
      isRead: false,
      isDismissed: false,
      tags: [],
      reasoning: nil,
      currentActivity: nil,
      inputDeviceName: nil,
      windowTitle: nil,
      headline: nil
    )
  }

  func testPrunesMemoryDeletedOnAnotherDevice() async throws {
    let kept = makeMemory(id: "kept-1", tier: .longTerm)
    let deletedElsewhere = makeMemory(id: "deleted-elsewhere", tier: .longTerm)
    try await MemoryStorage.shared.syncServerMemories([kept, deletedElsewhere])

    await makeViewModel(returning: page([kept])).reconcileCacheIfNeeded()

    let goneRecord = try await MemoryStorage.shared.getMemoryByBackendId("deleted-elsewhere")
    XCTAssertEqual(goneRecord?.deleted, true, "a memory the backend no longer has must be pruned")
    let keptRecord = try await MemoryStorage.shared.getMemoryByBackendId("kept-1")
    XCTAssertEqual(keptRecord?.deleted, false, "a memory the backend still has must survive")
  }

  /// The default-scope pull was the reason pruning was refused. Including
  /// Archive is what makes the keep-set and the prune scope describe the same
  /// population — if the pull ever narrows again, this fails.
  func testPrunesArchiveTierWithoutDeletingArchiveRowsStillPresent()
    async throws
  {
    let archiveKept = makeMemory(id: "archive-kept", tier: .archive)
    let archiveGone = makeMemory(id: "archive-gone", tier: .archive)
    try await MemoryStorage.shared.syncServerMemories([archiveKept, archiveGone])

    await makeViewModel(returning: page([archiveKept])).reconcileCacheIfNeeded()

    let keptRecord = try await MemoryStorage.shared.getMemoryByBackendId("archive-kept")
    XCTAssertEqual(keptRecord?.deleted, false)
    let goneRecord = try await MemoryStorage.shared.getMemoryByBackendId("archive-gone")
    XCTAssertEqual(goneRecord?.deleted, true)
  }

  func testTruncatedPullPrunesNothing() async throws {
    let present = makeMemory(id: "present", tier: .longTerm)
    let unseen = makeMemory(id: "unseen-because-truncated", tier: .longTerm)
    try await MemoryStorage.shared.syncServerMemories([present, unseen])

    await makeViewModel(returning: page([present], truncated: true)).reconcileCacheIfNeeded()

    let record = try await MemoryStorage.shared.getMemoryByBackendId("unseen-because-truncated")
    XCTAssertEqual(
      record?.deleted, false,
      "a truncated pull saw only part of the backend, so absence proves nothing")
  }

  /// A complete pull that returned nothing is an authoritative empty account:
  /// failures throw and truncated pulls return early, so reaching the prune
  /// with an empty keep-set means the server verifiably holds no memories.
  /// Refusing to prune here protected zombie rows forever on wiped accounts.
  func testCompleteEmptyPullPrunesSyncedOrphans() async throws {
    let existing = makeMemory(id: "existing", tier: .longTerm)
    try await MemoryStorage.shared.syncServerMemories([existing])

    await makeViewModel(returning: page([])).reconcileCacheIfNeeded()

    let record = try await MemoryStorage.shared.getMemoryByBackendId("existing")
    XCTAssertEqual(
      record?.deleted, true,
      "a synced row must not outlive a verifiably empty account")
  }

  /// Local-only rows are the only copy and must survive an empty-account prune;
  /// `softDeleteSyncedOrphans` restricts the prune to rows with a backendId.
  func testCompleteEmptyPullKeepsLocalOnlyRows() async throws {
    let stranded = MemoryRecord(
      content: "stranded local-only memory",
      createdAt: Date(timeIntervalSinceNow: -86_400 * 90))
    _ = try await MemoryStorage.shared.insertLocalMemory(stranded)

    await makeViewModel(returning: page([])).reconcileCacheIfNeeded()

    let unsynced = try await MemoryStorage.shared.getUnsyncedMemories()
    XCTAssertEqual(
      unsynced.count, 1,
      "a local-only row must never be pruned by the reconcile, even against an empty account")
    XCTAssertEqual(unsynced.first?.deleted, false)
  }

  /// An owner switch between the pull and the prune must fence the prune: the
  /// keep-set belongs to the owner that pulled it, and `databasePool()` reopens
  /// for the new owner — so pruning with the stale keep-set (worst case: empty,
  /// an apparently wiped account) would tombstone the new owner's synced rows.
  /// The aborted reconcile must also not latch, so the new owner's own
  /// reconcile runs clean.
  func testOwnerChangeBetweenPullAndPruneSkipsPruneAndDoesNotLatch() async throws {
    let synced = makeMemory(id: "new-owner-row", tier: .longTerm)
    try await MemoryStorage.shared.syncServerMemories([synced])

    var fetches = 0
    let viewModel = MemoriesViewModel()
    viewModel.reconcilePageFetch = { [self] _, cursor, _ in
      fetches += 1
      if cursor == nil {
        // First page is empty but continues; the owner switches before the
        // terminal page, i.e. between the pull loop and the prune.
        return page([], nextCursor: "switch-after-this-page")
      }
      RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
      RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: "reconcile-other-owner")
      return page([])
    }

    await viewModel.reconcileCacheIfNeeded()

    XCTAssertEqual(fetches, 2)
    let stillThere = try await MemoryStorage.shared.getMemoryByBackendId("new-owner-row")
    XCTAssertEqual(
      stillThere?.deleted, false,
      "the new owner's rows must not be judged by the previous owner's keep-set")

    // No latch: with this user's authority restored, the reconcile must run
    // again from the top instead of returning before its first fetch.
    guard let testUserId else { return }
    RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
    RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: testUserId)
    viewModel.reconcilePageFetch = { [self] _, _, _ in
      fetches += 1
      return page([])
    }
    await viewModel.reconcileCacheIfNeeded()

    XCTAssertEqual(fetches, 3, "the aborted reconcile must not latch its user")
    let pruned = try await MemoryStorage.shared.getMemoryByBackendId("new-owner-row")
    XCTAssertEqual(
      pruned?.deleted, true,
      "the clean reconcile still treats a verifiably empty account as authoritative")
  }
}
