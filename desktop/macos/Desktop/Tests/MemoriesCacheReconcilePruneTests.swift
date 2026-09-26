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

  override func setUp() async throws {
    authSnapshot = RewindStorageTestIsolation.captureAuthSnapshot()
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memories-reconcile-prune")
    userDir = fixture.userDir
    RewindStorageTestIsolation.signInForTests(userId: fixture.testUserId)
  }

  override func tearDown() async throws {
    if let authSnapshot {
      RewindStorageTestIsolation.restoreAuthSnapshot(authSnapshot)
    }
    if let userDir {
      await RewindStorageTestIsolation.tearDown(userDir: userDir)
    }
  }

  private func page(
    _ memories: [ServerMemory],
    truncated: Bool = false
  ) -> APIClient.MemoryListPage {
    APIClient.MemoryListPage(
      memories: memories,
      nextCursor: nil,
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

  func testEmptyPullPrunesNothing() async throws {
    let existing = makeMemory(id: "existing", tier: .longTerm)
    try await MemoryStorage.shared.syncServerMemories([existing])

    await makeViewModel(returning: page([])).reconcileCacheIfNeeded()

    let record = try await MemoryStorage.shared.getMemoryByBackendId("existing")
    XCTAssertEqual(
      record?.deleted, false,
      "an empty read is far more likely to be a failure than an empty account")
  }
}
