import XCTest

@testable import Omi_Computer

/// Regression coverage for the Tasks auto-refresh 422.
///
/// `refreshTasksIfNeeded` computed its reload limit as
/// `max(pageSize, incompleteTasks.count)` and passed it straight to
/// `GET /v1/action-items`, whose backend validates `limit … le=500`. A user
/// with more than 500 hydrated incomplete tasks sent `limit > 500`, so every
/// auto-refresh (app activation, Cmd+R) got HTTP 422 and silently failed. The
/// limit is now clamped to the backend cap.
@MainActor
final class TasksStoreApiPageLimitTests: XCTestCase {
  func testClampNeverExceedsBackendCap() {
    XCTAssertEqual(TasksStore.clampedApiPageLimit(742), TasksStore.apiPageLimitCap)
    XCTAssertEqual(TasksStore.clampedApiPageLimit(501), 500)
    XCTAssertEqual(TasksStore.apiPageLimitCap, 500)
  }

  func testClampKeepsInRangeRequestsUnchanged() {
    XCTAssertEqual(TasksStore.clampedApiPageLimit(100), 100)
    XCTAssertEqual(TasksStore.clampedApiPageLimit(500), 500)
  }

  func testClampFloorsToAtLeastOne() {
    XCTAssertEqual(TasksStore.clampedApiPageLimit(0), 1)
    XCTAssertEqual(TasksStore.clampedApiPageLimit(-5), 1)
  }
}
