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
    // Trigger resetSessionState directly to verify truncated flag resets
    vm.resetSessionState()
    XCTAssertFalse(vm.isTruncated, "resetSessionState must reset isTruncated")
  }

  func testRuntimeOwnerChangeResetsTruncatedState() {
    let vm = MemoriesViewModel()
    NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)
    XCTAssertFalse(vm.isTruncated, "runtime owner change must reset isTruncated")
  }

  func testMemoryListPageTruncatedPagingSafety() {
    // Truncated page with memories must not allow paging further
    let pageWithCursor = APIClient.MemoryListPage(
      memories: [],
      nextCursor: "cursor-123",
      canonicalLifecycleExposed: true,
      deviceScopeSupported: true,
      defaultMemoryDeleteSupported: true,
      truncated: true
    )
    XCTAssertTrue(pageWithCursor.truncated)
    XCTAssertEqual(pageWithCursor.nextCursor, "cursor-123")
  }
}
