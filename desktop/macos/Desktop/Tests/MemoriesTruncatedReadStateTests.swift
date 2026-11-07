import XCTest

@testable import Omi_Computer

/// Regression tests for issue #24722:
/// Truncated reads must remain distinguishable from complete-empty history,
/// must not claim zero total memories or "No memories yet", and must reset cleanly.
@MainActor
final class MemoriesTruncatedReadStateTests: XCTestCase {
  func testDefaultTruncatedStateIsFalse() {
    let vm = MemoriesViewModel()
    XCTAssertFalse(vm.isTruncated, "new view model must not be truncated")
  }

  func testResetSessionStateClearsTruncatedFlag() {
    let vm = MemoriesViewModel()
    // Establish truncated state first so reset is genuinely exercised
    vm.isTruncated = true
    XCTAssertTrue(vm.isTruncated, "view model must be truncated before reset")

    vm.resetSessionState()
    XCTAssertFalse(vm.isTruncated, "resetSessionState must reset isTruncated")
  }

  func testRuntimeOwnerChangeResetsTruncatedState() {
    let vm = MemoriesViewModel()
    // Establish truncated state first so notification handler is genuinely exercised
    vm.isTruncated = true
    XCTAssertTrue(vm.isTruncated, "view model must be truncated before notification")

    NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)
    XCTAssertFalse(vm.isTruncated, "runtime owner change must reset isTruncated")
  }

  func testMemoryListPageTruncatedPagingSafety() {
    let memory = ServerMemory(
      id: "mem-1",
      content: "Test memory",
      category: .system,
      tier: .longTerm,
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
      isLocked: false,
      isShared: false
    )

    // Truncated page with memories and nextCursor must NOT allow paging further
    let truncatedPageWithCursor = APIClient.MemoryListPage(
      memories: [memory],
      nextCursor: "cursor-123",
      canonicalLifecycleExposed: true,
      deviceScopeSupported: true,
      defaultMemoryDeleteSupported: true,
      truncated: true
    )
    XCTAssertTrue(truncatedPageWithCursor.truncated)
    XCTAssertEqual(truncatedPageWithCursor.nextCursor, "cursor-123")
    XCTAssertFalse(
      MemoriesViewModel.hasMoreAfterPage(truncatedPageWithCursor, received: 1),
      "Truncated page must refuse pagination even when nextCursor is present"
    )

    // Non-truncated page with nextCursor must allow paging
    let normalPageWithCursor = APIClient.MemoryListPage(
      memories: [memory],
      nextCursor: "cursor-123",
      canonicalLifecycleExposed: true,
      deviceScopeSupported: true,
      defaultMemoryDeleteSupported: true,
      truncated: false
    )
    XCTAssertTrue(
      MemoriesViewModel.hasMoreAfterPage(normalPageWithCursor, received: 1),
      "Normal page with nextCursor must allow pagination"
    )
  }
}
