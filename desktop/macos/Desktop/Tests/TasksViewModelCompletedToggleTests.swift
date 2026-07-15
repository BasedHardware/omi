import XCTest

@testable import Omi_Computer

/// Mobile-parity contract for the simplified Tasks view: one completed toggle
/// switches between To Do and Done, and the categorized To Do list can never
/// show completed rows even if they leak into the source arrays (e.g. a task
/// completed on another device mid-merge).
@MainActor
final class TasksViewModelCompletedToggleTests: XCTestCase {

  override func tearDown() async throws {
    TasksStore.shared.resetSessionState()
    try await super.tearDown()
  }

  func testToggleFlipsBetweenTodoAndDoneViews() {
    let vm = TasksViewModel()
    XCTAssertEqual(vm.selectedTags, [.todo], "default view is To Do, like mobile")
    XCTAssertFalse(vm.showCompleted)

    vm.toggleShowCompletedView()
    XCTAssertEqual(vm.selectedTags, [.done])
    XCTAssertTrue(vm.showCompleted)

    vm.toggleShowCompletedView()
    XCTAssertEqual(vm.selectedTags, [.todo])
    XCTAssertFalse(vm.showCompleted)
  }

  func testCategorizedTodoViewNeverShowsCompletedTasks() {
    let store = TasksStore.shared
    store.resetSessionState()
    let active = task(id: "active", completed: false)
    let completedStray = task(id: "completed-on-mobile", completed: true)
    // Simulate the leak: a completed row still sitting in the incomplete array
    // (stale merge window before reconciliation catches up).
    store.incompleteTasks = [active, completedStray]

    let vm = TasksViewModel()
    vm.selectedTags = [.todo]

    let categorized = TaskCategory.allCases.flatMap { vm.getOrderedTasks(for: $0) }
    XCTAssertEqual(
      categorized.map(\.id), [active.id],
      "completed tasks must never appear in the categorized To Do list")
  }

  func testDoneViewShowsOnlyCompletedTasks() {
    let store = TasksStore.shared
    store.resetSessionState()
    store.completedTasks = [task(id: "done-1", completed: true)]
    store.incompleteTasks = [task(id: "active", completed: false)]

    let vm = TasksViewModel()
    vm.toggleShowCompletedView()

    XCTAssertTrue(vm.showCompleted)
    XCTAssertEqual(vm.displayTasks.map(\.id), ["done-1"])
  }

  private func task(id: String, completed: Bool) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: id,
      completed: completed,
      createdAt: Date(timeIntervalSince1970: 0))
  }
}
