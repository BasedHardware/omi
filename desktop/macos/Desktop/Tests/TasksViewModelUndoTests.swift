import XCTest

@testable import Omi_Computer

@MainActor
final class TasksViewModelUndoTests: XCTestCase {
  override func setUp() async throws {
    TasksStore.shared.resetSessionState()
  }

  override func tearDown() async throws {
    TasksStore.shared.resetSessionState()
  }

  /// Regression for #13329: the backend restore mints a replacement ID, so
  /// Undo must render the task returned by the store instead of resurrecting
  /// the deleted task snapshot (and its dead backend ID) from the undo stack.
  func testUndoUsesCanonicalRestoredTaskInEveryDisplayProjection() async {
    let deletedTask = task(id: "deleted-backend-id")
    let canonicalTask = task(id: "replacement-backend-id")
    let viewModel = TasksViewModel(restoreTaskOperation: { task in
      XCTAssertEqual(task.id, deletedTask.id)
      return canonicalTask
    })
    viewModel.recomputeDisplayCaches()
    viewModel.undoStack = [
      TasksViewModel.UndoableAction(task: deletedTask, timestamp: Date())
    ]

    await viewModel.undoLastDelete()

    XCTAssertEqual(viewModel.displayTasks.map(\.id), [canonicalTask.id])
    XCTAssertEqual(viewModel.categorizedTasks[.today]?.map(\.id), [canonicalTask.id])
    XCTAssertFalse(viewModel.displayTasks.contains { $0.id == deletedTask.id })
  }

  /// If the local restore cannot commit (for example after an owner change),
  /// the UI must not show a row whose backing task does not exist.
  func testUndoDoesNotRenderDeletedSnapshotWhenRestoreFails() async {
    let deletedTask = task(id: "deleted-backend-id")
    let viewModel = TasksViewModel(restoreTaskOperation: { _ in nil })
    viewModel.recomputeDisplayCaches()
    viewModel.undoStack = [
      TasksViewModel.UndoableAction(task: deletedTask, timestamp: Date())
    ]

    await viewModel.undoLastDelete()

    XCTAssertTrue(viewModel.displayTasks.isEmpty)
    XCTAssertTrue(viewModel.categorizedTasks.values.allSatisfy(\.isEmpty))
  }

  private func task(id: String) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: "restored task",
      completed: false,
      createdAt: Date(timeIntervalSince1970: 0)
    )
  }
}
