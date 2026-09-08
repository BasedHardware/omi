import XCTest

@testable import Omi_Computer

/// Regression coverage for the "Load more tasks" button crash.
///
/// The button used to force-unwrap `displayTasks.last!` inside an async Task.
/// The emptiness guard was render-time only, so if the store emptied the list
/// (e.g. `resetSessionState()` on an account switch, or the debounced recompute)
/// between the click and the Task running, the force-unwrap crashed. The action
/// now reads `displayTasks.last` at execution time and no-ops when empty.
@MainActor
final class TasksViewModelLoadMoreTappedTests: XCTestCase {
  override func tearDown() async throws {
    TasksStore.shared.resetSessionState()
  }

  func testLoadMoreTappedIsNoOpWhenListEmptied() async {
    let store = TasksStore.shared
    store.resetSessionState()
    let vm = TasksViewModel()
    vm.selectedTags = [.todo]

    // The list is empty at execution time (the store was reset). The old
    // displayTasks.last! would have crashed here; loadMoreTapped must return.
    XCTAssertTrue(vm.displayTasks.isEmpty)
    await vm.loadMoreTapped()
    XCTAssertTrue(vm.displayTasks.isEmpty, "no-op load-more must not fabricate rows")
  }
}
