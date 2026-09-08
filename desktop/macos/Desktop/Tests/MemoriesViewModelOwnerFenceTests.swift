import XCTest

@testable import Omi_Computer

/// Regression: an in-place account switch posts only .runtimeOwnerDidChange
/// (never .userDidSignOut), so owner-bound view models must fence themselves
/// or the previous account's rows keep rendering for the next account.
@MainActor
final class MemoriesViewModelOwnerFenceTests: XCTestCase {
  func testRuntimeOwnerChangeClearsThePreviousAccountsMemories() {
    let vm = MemoriesViewModel()
    vm.memories = [
      ServerMemory(
        id: "previous-account-memory",
        content: "Previous account's memory",
        category: .system,
        tier: .shortTerm,
        tierIsExplicit: false,
        createdAt: Date(timeIntervalSince1970: 1),
        updatedAt: Date(timeIntervalSince1970: 1),
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
    ]

    NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)

    XCTAssertTrue(
      vm.memories.isEmpty,
      "an in-place account switch must clear the previous account's memories")
  }
}
