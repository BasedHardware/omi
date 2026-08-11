import XCTest

@testable import Omi_Computer

@MainActor
final class TasksViewModelSelectAllTests: XCTestCase {
  private enum SelectionFailure: LocalizedError {
    case unavailable

    var errorDescription: String? { "selection census unavailable" }
  }

  override func tearDown() async throws {
    TasksStore.shared.resetSessionState()
  }

  func testSelectAllUsesCompleteIdentityCensusInsteadOfRenderedRows() async {
    let allIDs = (0..<250).map { "task-\($0)" }
    let viewModel = TasksViewModel(selectionSnapshotLoader: { completed in
      XCTAssertFalse(completed)
      return allIDs
    })
    viewModel.toggleMultiSelectMode()

    await viewModel.selectAllTasks()

    XCTAssertEqual(viewModel.multiSelection.selectionCount, 250)
    XCTAssertEqual(Set(viewModel.multiSelection.selectedIDs(in: nil)), Set(allIDs))
    XCTAssertTrue(viewModel.allTasksInSelectionScopeSelected)
    XCTAssertNil(viewModel.bulkTaskErrorMessage)
  }

  func testDeselectAllClearsOffPageIdentityCensusSelection() async {
    let allIDs = (0..<250).map { "task-\($0)" }
    let viewModel = TasksViewModel(selectionSnapshotLoader: { _ in allIDs })
    viewModel.toggleMultiSelectMode()
    await viewModel.selectAllTasks()

    await viewModel.toggleSelectAllTasks()

    XCTAssertTrue(viewModel.isMultiSelectMode)
    XCTAssertEqual(viewModel.multiSelection.selectionCount, 0)
    XCTAssertFalse(viewModel.allTasksInSelectionScopeSelected)
  }

  func testChangingCompletionBucketClearsExistingSelection() async {
    let viewModel = TasksViewModel(selectionSnapshotLoader: { _ in ["todo-1", "todo-2"] })
    viewModel.toggleMultiSelectMode()
    await viewModel.selectAllTasks()

    viewModel.showCompleted = true

    XCTAssertTrue(viewModel.isMultiSelectMode)
    XCTAssertEqual(viewModel.multiSelection.selectionCount, 0)
    XCTAssertFalse(viewModel.allTasksInSelectionScopeSelected)
  }

  func testChangingSearchScopeClearsExistingSelection() async {
    let viewModel = TasksViewModel(selectionSnapshotLoader: { _ in ["todo-1", "todo-2"] })
    viewModel.toggleMultiSelectMode()
    await viewModel.selectAllTasks()

    viewModel.searchText = "follow up"

    XCTAssertTrue(viewModel.isMultiSelectMode)
    XCTAssertEqual(viewModel.multiSelection.selectionCount, 0)
    XCTAssertFalse(viewModel.allTasksInSelectionScopeSelected)
  }

  func testSelectAllFailurePreservesExistingSelectionAndSurfacesError() async {
    let viewModel = TasksViewModel(selectionSnapshotLoader: { _ in throw SelectionFailure.unavailable })
    viewModel.toggleMultiSelectMode()
    viewModel.mutateMultiSelection { state in
      _ = state.click("visible", modifiers: .command, visibleIDs: ["visible"])
    }

    await viewModel.selectAllTasks()

    XCTAssertEqual(viewModel.multiSelection.selectedIDs(in: ["visible"]), ["visible"])
    XCTAssertEqual(
      viewModel.bulkTaskErrorMessage,
      "Could not reach your complete task list. No additional tasks were selected. Please retry."
    )
    XCTAssertFalse(viewModel.isSelectingAllTasks)
  }
}
