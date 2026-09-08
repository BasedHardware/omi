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

  func testSelectAllCompletionFromAbandonedSelectionSessionIsIgnored() async {
    let censusStarted = expectation(description: "selection census starts")
    var resumeCensus: CheckedContinuation<[String], Never>?
    let viewModel = TasksViewModel(selectionSnapshotLoader: { _ in
      censusStarted.fulfill()
      return await withCheckedContinuation { continuation in
        resumeCensus = continuation
      }
    })
    viewModel.toggleMultiSelectMode()

    let selectionTask = Task { @MainActor in
      await viewModel.selectAllTasks()
    }
    await fulfillment(of: [censusStarted], timeout: 1)

    // Leave and re-enter the mode while the old request is suspended. The
    // response must not select IDs in this new session.
    viewModel.toggleMultiSelectMode()
    viewModel.toggleMultiSelectMode()
    resumeCensus?.resume(returning: ["stale-task"])
    await selectionTask.value

    XCTAssertEqual(viewModel.multiSelection.selectionCount, 0)
    XCTAssertFalse(viewModel.allTasksInSelectionScopeSelected)
  }

  func testSelectAllCompletionAfterEscapeDoesNotRepopulateSelection() async {
    let censusStarted = expectation(description: "selection census starts")
    var resumeCensus: CheckedContinuation<[String], Never>?
    let viewModel = TasksViewModel(selectionSnapshotLoader: { _ in
      censusStarted.fulfill()
      return await withCheckedContinuation { continuation in
        resumeCensus = continuation
      }
    })
    viewModel.toggleMultiSelectMode()

    let selectionTask = Task { @MainActor in
      await viewModel.selectAllTasks()
    }
    await fulfillment(of: [censusStarted], timeout: 1)
    XCTAssertTrue(viewModel.handleEscape())

    resumeCensus?.resume(returning: ["stale-task"])
    await selectionTask.value

    XCTAssertFalse(viewModel.isMultiSelectMode)
    XCTAssertFalse(viewModel.isSelectingAllTasks)
    XCTAssertEqual(viewModel.multiSelection.selectionCount, 0)
  }

  func testBulkDeleteBusyFlagClearsAfterSelectionChangesDuringRequest() async {
    let deleteStarted = expectation(description: "bulk delete starts")
    var resumeDelete: CheckedContinuation<TasksStore.BulkDeleteOutcome, Never>?
    let viewModel = TasksViewModel(
      bulkDeleteOperation: { _ in
        return await withCheckedContinuation { continuation in
          resumeDelete = continuation
          deleteStarted.fulfill()
        }
      },
      bulkDeleteConfirmation: { _ in true }
    )
    let first = TaskActionItem(id: "first", description: "First", completed: false, createdAt: Date())
    let second = TaskActionItem(id: "second", description: "Second", completed: false, createdAt: Date())
    viewModel.store.incompleteTasks = [first, second]
    viewModel.recomputeDisplayCaches()
    viewModel.toggleMultiSelectMode()
    viewModel.toggleTaskSelection(first)

    let deleteTask = Task { @MainActor in
      await viewModel.deleteSelectedTasks()
    }
    await fulfillment(of: [deleteStarted], timeout: 1)

    // This fences the old request without exiting the mode. Its completion
    // must not leave the busy flag stuck after the generation changes.
    viewModel.toggleTaskSelection(second)
    resumeDelete?.resume(returning: .localFailure(remoteDeletedIDs: []))
    await deleteTask.value

    XCTAssertFalse(viewModel.bulkDeleteInFlight)
    XCTAssertTrue(viewModel.displayTasks.contains(where: { $0.id == first.id }))
  }

  func testRejectedBulkDeleteRestoresOptimisticRowsAndKeepsSelection() async {
    let viewModel = TasksViewModel(
      bulkDeleteOperation: { _ in .remoteFailure(confirmedIDs: []) },
      bulkDeleteConfirmation: { _ in true }
    )
    let first = TaskActionItem(id: "first", description: "First", completed: false, createdAt: Date())
    let second = TaskActionItem(id: "second", description: "Second", completed: false, createdAt: Date())
    viewModel.store.incompleteTasks = [first, second]
    viewModel.recomputeDisplayCaches()
    viewModel.toggleMultiSelectMode()
    viewModel.toggleTaskSelection(first)
    viewModel.toggleTaskSelection(second)

    await viewModel.deleteSelectedTasks()

    XCTAssertEqual(Set(viewModel.displayTasks.map(\.id)), Set([first.id, second.id]))
    XCTAssertEqual(Set(viewModel.multiSelection.selectedIDs(in: nil)), Set([first.id, second.id]))
    XCTAssertEqual(
      viewModel.bulkTaskErrorMessage,
      "The selected tasks could not be deleted from your account. Nothing was removed from this Mac. "
        + "Locked tasks require a paid plan; otherwise, check your connection and retry."
    )
  }

  func testOwnerChangedBulkDeleteRestoresOptimisticRows() async {
    let viewModel = TasksViewModel(
      bulkDeleteOperation: { _ in .ownerChanged },
      bulkDeleteConfirmation: { _ in true }
    )
    let task = TaskActionItem(id: "task", description: "Task", completed: false, createdAt: Date())
    viewModel.store.incompleteTasks = [task]
    viewModel.recomputeDisplayCaches()
    viewModel.toggleMultiSelectMode()
    viewModel.toggleTaskSelection(task)

    await viewModel.deleteSelectedTasks()

    XCTAssertEqual(viewModel.displayTasks.map(\.id), [task.id])
    XCTAssertEqual(viewModel.multiSelection.selectedIDs(in: nil), [task.id])
  }

  func testSearchResultsFromOlderQueryCannotOverwriteNewerQuery() async {
    let alphaStarted = expectation(description: "alpha search starts")
    let betaStarted = expectation(description: "beta search starts")
    var resumeAlpha: CheckedContinuation<[TaskActionItem], Never>?
    var resumeBeta: CheckedContinuation<[TaskActionItem], Never>?
    let alpha = TaskActionItem(id: "alpha", description: "Alpha", completed: false, createdAt: Date())
    let beta = TaskActionItem(id: "beta", description: "Beta", completed: false, createdAt: Date())
    let viewModel = TasksViewModel(searchLoader: { query, _ in
      if query == "alpha" {
        return await withCheckedContinuation { continuation in
          resumeAlpha = continuation
          alphaStarted.fulfill()
        }
      }
      return await withCheckedContinuation { continuation in
        resumeBeta = continuation
        betaStarted.fulfill()
      }
    })

    viewModel.searchText = "alpha"
    await fulfillment(of: [alphaStarted], timeout: 1)
    viewModel.searchText = "beta"
    await fulfillment(of: [betaStarted], timeout: 1)

    resumeBeta?.resume(returning: [beta])
    for _ in 0..<100 {
      if viewModel.searchResults == [beta] { break }
      await Task.yield()
    }
    resumeAlpha?.resume(returning: [alpha])
    await Task.yield()

    XCTAssertEqual(viewModel.searchResults, [beta])
  }

  func testSelectAllRejectsPriorSearchResultsWhileReplacementSearchIsLoading() async {
    let replacementStarted = expectation(description: "replacement search starts")
    var resumeReplacement: CheckedContinuation<[TaskActionItem], Never>?
    let prior = TaskActionItem(id: "prior", description: "Prior", completed: false, createdAt: Date())
    let replacement = TaskActionItem(
      id: "replacement",
      description: "Replacement",
      completed: false,
      createdAt: Date()
    )
    let viewModel = TasksViewModel(searchLoader: { query, _ in
      if query == "prior" {
        return [prior]
      }
      return await withCheckedContinuation { continuation in
        resumeReplacement = continuation
        replacementStarted.fulfill()
      }
    })

    viewModel.searchText = "prior"
    for _ in 0..<100 {
      if viewModel.searchResults == [prior], !viewModel.isSearching { break }
      await Task.yield()
    }
    XCTAssertEqual(viewModel.searchResults, [prior])
    viewModel.toggleMultiSelectMode()

    viewModel.searchText = "replacement"
    await fulfillment(of: [replacementStarted], timeout: 1)
    await viewModel.selectAllTasks()

    XCTAssertTrue(viewModel.isMultiSelectMode)
    XCTAssertTrue(viewModel.multiSelection.selectedIDs.isEmpty)
    XCTAssertFalse(viewModel.allTasksInSelectionScopeSelected)
    XCTAssertEqual(
      viewModel.bulkTaskErrorMessage,
      "Could not reach your complete task list. No additional tasks were selected. Please retry."
    )

    resumeReplacement?.resume(returning: [replacement])
    for _ in 0..<100 {
      if viewModel.searchResults == [replacement], !viewModel.isSearching { break }
      await Task.yield()
    }
    XCTAssertEqual(viewModel.searchResults, [replacement])
  }
}
