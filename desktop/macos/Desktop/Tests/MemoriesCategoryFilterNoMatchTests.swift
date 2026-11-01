import Combine
import XCTest

@testable import Omi_Computer

/// A category filter decides what the Memories list shows from the category
/// selection, not from whether its query found anything. A category with no
/// memories must read as no results instead of falling back to every memory
/// under the active filter chip.
@MainActor
final class MemoriesCategoryFilterNoMatchTests: XCTestCase {
  private var userDir: URL?
  private var authSnapshot: RewindStorageTestIsolation.AuthSnapshot?

  override func setUp() async throws {
    authSnapshot = RewindStorageTestIsolation.captureAuthSnapshot()
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memories-category-no-match")
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

  func testCategoryWithNoMatchesShowsNoMemoriesInsteadOfEveryMemory() async throws {
    let aboutYou = makeMemory(id: "about-you", category: .system, createdAt: 2)
    let insight = makeMemory(id: "insight", category: .interesting, createdAt: 1)
    try await MemoryStorage.shared.syncServerMemories([aboutYou, insight])
    let viewModel = MemoriesViewModel(deleteMemoryRequest: { _ in })
    viewModel.memories = [aboutYou, insight]
    XCTAssertEqual(viewModel.filteredMemories.map(\.id), [aboutYou.id, insight.id])

    await select([.workflow], on: viewModel)

    XCTAssertEqual(
      viewModel.filteredMemories.map(\.id), [],
      "No memory is in Workflow, so the filtered list must be empty, not every loaded memory"
    )
  }

  func testCategoryWithMatchesShowsOnlyThoseMemories() async throws {
    let aboutYou = makeMemory(id: "about-you", category: .system, createdAt: 2)
    let insight = makeMemory(id: "insight", category: .interesting, createdAt: 1)
    try await MemoryStorage.shared.syncServerMemories([aboutYou, insight])
    let viewModel = MemoriesViewModel(deleteMemoryRequest: { _ in })
    viewModel.memories = [aboutYou, insight]

    await select([.interesting], on: viewModel)

    XCTAssertEqual(viewModel.filteredMemories.map(\.id), [insight.id])
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
