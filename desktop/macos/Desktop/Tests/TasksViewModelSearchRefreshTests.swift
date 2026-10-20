import XCTest

@testable import Omi_Computer

/// Search rows are a SQLite snapshot from when the query ran, and the view model
/// rebuilds its lists whenever `TasksStore` publishes a change. A task deleted or
/// completed while a search is active must not come back in its old state on
/// that rebuild: the query is re-read instead of the snapshot being reused.
@MainActor
final class TasksViewModelSearchRefreshTests: XCTestCase {
  override func setUp() async throws {
    TasksStore.shared.resetSessionState()
  }

  override func tearDown() async throws {
    TasksStore.shared.resetSessionState()
  }

  func testDeletedSearchResultStaysGoneAfterTheStorePublishesTheDelete() async throws {
    let kept = task(id: "kept", description: "Budget review")
    let deleted = task(id: "deleted", description: "Budget draft")
    // Stands in for the local SQLite rows the production search reads.
    var localRows = [kept, deleted]
    var requeryObserved = false
    let requeried = expectation(description: "search re-reads local rows after the delete")
    TasksStore.shared.incompleteTasks = [kept, deleted]
    let defaults = try makeIsolatedDefaults()
    let viewModel = TasksViewModel(
      searchLoader: { _, _ in
        if !requeryObserved, !localRows.contains(where: { $0.id == deleted.id }) {
          requeryObserved = true
          requeried.fulfill()
        }
        return localRows
      },
      bulkDeleteOperation: { ids in
        // The local tombstone hides the row from every later search.
        localRows.removeAll { ids.contains($0.id) }
        return .deletedEverywhere
      },
      bulkDeleteConfirmation: { _ in true },
      orderingDefaults: defaults
    )

    viewModel.searchText = "budget"
    for _ in 0..<100 {
      if viewModel.searchResults.count == 2, !viewModel.isSearching { break }
      await Task.yield()
    }
    XCTAssertEqual(Set(viewModel.displayTasks.map(\.id)), Set([kept.id, deleted.id]))

    viewModel.toggleMultiSelectMode()
    viewModel.toggleTaskSelection(deleted)
    await viewModel.deleteSelectedTasks()
    XCTAssertEqual(viewModel.displayTasks.map(\.id), [kept.id])

    // Committing the delete drops the row from the store, as
    // `TasksStore.deleteMultipleTasks` does. The view model rebuilds its lists
    // from that publication once the store's debounce settles.
    viewModel.store.incompleteTasks.removeAll { $0.id == deleted.id }
    await fulfillment(of: [requeried], timeout: 5)
    for _ in 0..<100 {
      if viewModel.searchResults.map(\.id) == [kept.id] { break }
      await Task.yield()
    }

    XCTAssertEqual(viewModel.searchResults.map(\.id), [kept.id])
    XCTAssertEqual(viewModel.displayTasks.map(\.id), [kept.id])
  }

  func testTaskCompletedWhileSearchingLeavesTheToDoResults() async throws {
    let open = task(id: "open", description: "Budget review")
    let finished = task(id: "finished", description: "Budget draft")
    let finishedCompleted = task(id: "finished", description: "Budget draft", completed: true)
    var localRows = [open, finished]
    var requeryObserved = false
    let requeried = expectation(description: "search re-reads local rows after the completion")
    TasksStore.shared.incompleteTasks = [open, finished]
    let defaults = try makeIsolatedDefaults()
    let viewModel = TasksViewModel(
      searchLoader: { _, _ in
        if !requeryObserved, localRows.contains(where: \.completed) {
          requeryObserved = true
          requeried.fulfill()
        }
        return localRows
      },
      orderingDefaults: defaults
    )

    viewModel.searchText = "budget"
    for _ in 0..<100 {
      if viewModel.searchResults.count == 2, !viewModel.isSearching { break }
      await Task.yield()
    }
    XCTAssertEqual(Set(viewModel.displayTasks.map(\.id)), Set([open.id, finished.id]))

    // Completing a task writes SQLite first, then moves the row between the
    // store's lists, as `TasksStore.toggleTask` does.
    localRows = [open, finishedCompleted]
    viewModel.store.incompleteTasks.removeAll { $0.id == finished.id }
    viewModel.store.completedTasks.insert(finishedCompleted, at: 0)
    await fulfillment(of: [requeried], timeout: 5)
    for _ in 0..<100 {
      if viewModel.searchResults.contains(where: { $0.id == finished.id && $0.completed }) { break }
      await Task.yield()
    }

    XCTAssertEqual(viewModel.displayTasks.map(\.id), [open.id])
  }

  private func task(id: String, description: String, completed: Bool = false) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: description,
      completed: completed,
      createdAt: Date(timeIntervalSince1970: 0)
    )
  }
}
