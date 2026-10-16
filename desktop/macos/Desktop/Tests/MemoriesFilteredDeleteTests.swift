import Combine
import XCTest

@testable import Omi_Computer

/// Deleting a memory while a search or category filter is active must take its
/// card off the filtered list right away, the same as in the unfiltered list.
@MainActor
final class MemoriesFilteredDeleteTests: XCTestCase {
  private var userDir: URL?
  private var authSnapshot: RewindStorageTestIsolation.AuthSnapshot?

  override func setUp() async throws {
    authSnapshot = RewindStorageTestIsolation.captureAuthSnapshot()
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memories-filtered-delete")
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

  func testDeletingUnderACategoryFilterRemovesTheCardImmediately() async throws {
    let newer = makeMemory(id: "insight-newer", category: .interesting, createdAt: 3)
    let older = makeMemory(id: "insight-older", category: .interesting, createdAt: 2)
    let aboutYou = makeMemory(id: "about-you", category: .system, createdAt: 1)
    try await MemoryStorage.shared.syncServerMemories([newer, older, aboutYou])
    let viewModel = MemoriesViewModel(deleteMemoryRequest: { _ in })
    viewModel.memories = [newer, older, aboutYou]
    await select([.interesting], on: viewModel)
    XCTAssertEqual(viewModel.filteredMemories.map(\.id), [newer.id, older.id])

    await viewModel.deleteMemory(newer)

    XCTAssertEqual(viewModel.pendingDeleteMemory?.id, newer.id)
    XCTAssertEqual(
      viewModel.filteredMemories.map(\.id), [older.id],
      "The deleted memory's card must leave the filtered list while the undo toast shows"
    )

    await viewModel.confirmDelete().value

    XCTAssertEqual(viewModel.filteredMemories.map(\.id), [older.id])
  }

  /// Selecting a category starts a SQLite read; wait until it settles and the
  /// visible list has been recomputed from its result.
  private func select(_ tags: Set<MemoryTag>, on viewModel: MemoriesViewModel) async {
    let settled = expectation(description: "category query settled")
    let subscription = viewModel.$isLoadingFiltered
      .dropFirst()
      .filter { !$0 }
      .first()
      .sink { _ in settled.fulfill() }
    viewModel.selectedTags = tags
    await fulfillment(of: [settled], timeout: 5)
    subscription.cancel()
  }

  private func makeMemory(id: String, category: MemoryCategory, createdAt: TimeInterval) -> ServerMemory {
    ServerMemory(
      id: id,
      content: "Memory \(id)",
      category: category,
      tier: .longTerm,
      createdAt: Date(timeIntervalSince1970: createdAt),
      updatedAt: Date(timeIntervalSince1970: createdAt),
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
}
