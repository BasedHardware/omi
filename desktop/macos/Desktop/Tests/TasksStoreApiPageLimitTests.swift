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

  /// Auto-refresh must clamp only the API page, never the local-cache reload.
  /// A user paginated past 500 incomplete tasks previously had the clamped
  /// limit reused for the local reload, so `mergeWithoutAdding` dropped every
  /// row beyond 500 and the list collapsed back to 500 on app activation/Cmd+R.
  func testRefreshLimitsClampApiButPreserveLoadedRows() {
    let limits = TasksStore.refreshLimits(pageSize: 50, loadedCount: 620)
    XCTAssertEqual(limits.api, TasksStore.apiPageLimitCap, "API page must stay within the backend 422 cap")
    XCTAssertEqual(limits.local, 620, "local reload must keep every loaded row, not be capped to 500")
  }

  func testRefreshLimitsUsePageSizeFloorWhenListIsSmall() {
    let limits = TasksStore.refreshLimits(pageSize: 50, loadedCount: 10)
    XCTAssertEqual(limits.api, 50)
    XCTAssertEqual(limits.local, 50)
  }
}
