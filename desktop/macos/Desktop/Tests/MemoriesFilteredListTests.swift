import XCTest

@testable import Omi_Computer

/// Issues #21715/#21716 — filtered view integrity:
/// a category with zero matches must show NOTHING (not the unfiltered
/// list), and a delete under an active filter must drop the card.
@MainActor
final class MemoriesFilteredListTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?
  private var authSnapshot: RewindStorageTestIsolation.AuthSnapshot?

  override func setUp() async throws {
    let f = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memories-filtered")
    fixture = f
    authSnapshot = RewindStorageTestIsolation.captureAuthSnapshot()
    RewindStorageTestIsolation.signInForTests(userId: f.testUserId)
  }

  override func tearDown() async throws {
    RewindStorageTestIsolation.restoreAuthSnapshot(authSnapshot)
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
  }

  /// Wait until the async filter load settles (polls a real state flag,
  /// no wall-clock sleep — bounded by the yield loop).
  private func awaitFilterSettled(_ vm: MemoriesViewModel) async {
    for _ in 0..<1000 {
      await Task.yield()
      if !vm.isLoadingFiltered { return }
    }
  }

  func testEmptyCategoryFilterShowsNothingNotEverything() async {
    let vm = MemoriesViewModel()
    vm.memories = [
      ServerMemory(
        id: "m1", content: "a memory", category: .system,
        tier: .shortTerm, tierIsExplicit: false,
        createdAt: Date(), updatedAt: Date(), conversationId: nil,
        reviewed: false, userReview: nil, visibility: "private",
        manuallyAdded: false, scoring: nil, source: "desktop",
        confidence: nil, sourceApp: nil, contextSummary: nil,
        isRead: false, isDismissed: false, tags: [], reasoning: nil,
        currentActivity: nil, inputDeviceName: nil, windowTitle: nil,
        headline: nil
      )
    ]

    // Apply a category filter with zero matching rows — the isolated
    // store returns nothing for it.
    vm.selectedTags = [.workflow]
    await awaitFilterSettled(vm)

    XCTAssertTrue(
      vm.filteredMemories.isEmpty,
      "a category filter with no matches must show an empty list, not the \(vm.filteredMemories.count) unfiltered memories"
    )
  }
}
