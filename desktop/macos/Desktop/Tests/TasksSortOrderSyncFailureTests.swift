import XCTest

@testable import Omi_Computer

final class TasksSortOrderSyncFailureTests: XCTestCase {
    func testSyncFailureMessageNamesBothFailedDestinations() {
        let failure = TaskSortOrderSyncFailure(
            storageErrorDescription: "database is locked",
            backendErrorDescription: "offline"
        )

        XCTAssertEqual(
            failure.message,
            "Could not save task order to this Mac or Omi Cloud. Retry when your connection is available."
        )
    }

    func testSyncFailureMessageNamesBackendOnlyFailure() {
        let failure = TaskSortOrderSyncFailure(
            storageErrorDescription: nil,
            backendErrorDescription: "offline"
        )

        XCTAssertEqual(
            failure.message,
            "Task order was saved on this Mac, but not synced to Omi Cloud. Retry when your connection is available."
        )
    }

    @MainActor
    func testSortOrderSyncFailuresArePublishedWithPendingRetry() {
        let viewModel = TasksViewModel()

        viewModel.recordSortOrderSyncFailure(
            storageErrorDescription: nil,
            backendErrorDescription: "offline",
            updates: [(id: "task-1", sortOrder: 1000, indentLevel: 0)]
        )

        XCTAssertEqual(
            viewModel.sortOrderSyncFailure?.message,
            "Task order was saved on this Mac, but not synced to Omi Cloud. Retry when your connection is available."
        )
        XCTAssertTrue(viewModel.hasPendingSortOrderRetry)
    }
}
