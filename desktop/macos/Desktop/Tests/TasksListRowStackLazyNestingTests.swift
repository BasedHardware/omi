import XCTest

@testable import Omi_Computer

/// The Tasks list must keep exactly ONE lazy level: rows are direct items of
/// the page's single `LazyVStack`.
///
/// Two regressions shaped this contract:
///
/// - Lazy-in-lazy: when each category section was itself a lazy item that laid
///   its rows out in a nested `LazyVStack`, the section's measured height was
///   non-convergent — the inner stack reported estimates while the outer
///   measured it and real heights once placed — so every layout pass mutated
///   lazy-item phases and re-signaled prefetch, each scheduling another
///   transaction. The transaction flush never drained and the main thread
///   beachballed permanently on scroll (QA freeze: 2627/2627 main-thread
///   samples inside `GraphHost.flushTransactions`, dominated by
///   `LazyStack<>.measureEstimates` and `LazyLayoutViewCache.updateItemPhase`).
/// - Eager-in-lazy: fixing that freeze by making the section's row stack eager
///   meant the outer list could not estimate a section's height without laying
///   out all of its rows, so every section materialized: leaving the page tore
///   down all ~330 rows of a loaded profile — ~600 ms of pure main-thread
///   layout on every navigate away.
///
/// The list now flattens each category into interleaved `TasksListItem`
/// values (a header item, then one item per row) so rows virtualize
/// individually and no container of any kind nests inside a lazy item.
///
/// The structural half of this contract is held by source inspection: a unit
/// test cannot reach SwiftUI's lazy-layout machinery without hosting a run.
/// The identity half is behavioral.
final class TasksListRowStackLazyNestingTests: XCTestCase {
  /// tasksListView's source, scoped so lazy containers elsewhere in the page
  /// (the board view, a popover grid) cannot satisfy or trip this contract.
  private func tasksListViewSource() throws -> Substring {
    let source = try sourceFile("MainWindow/Pages/TasksPage.swift")
    let start = try XCTUnwrap(
      source.range(of: "private var tasksListView: some View {"),
      "tasksListView moved or was renamed; update this guard's anchor"
    )
    let end = try XCTUnwrap(
      source.range(of: "private var dashboardNavigationRenderKey: String {", range: start.upperBound..<source.endIndex),
      "tasksListView's end anchor moved; update this guard"
    )
    return source[start.lowerBound..<end.lowerBound]
  }

  func testTheListHasExactlyOneLazyStack() throws {
    let list = try tasksListViewSource()

    // Count instantiations (with the open paren) so prose in comments can
    // neither satisfy nor trip the count.
    let lazyStacks = list.components(separatedBy: "LazyVStack(").count - 1
    XCTAssertEqual(
      lazyStacks, 1,
      "tasksListView must contain exactly one LazyVStack — it is the page's only virtualizer, and a second lazy level re-creates the non-convergent lazy-in-lazy layout livelock"
    )

    for otherLazyContainer in ["LazyHStack(", "LazyVGrid(", "LazyHGrid("] {
      XCTAssertFalse(
        list.contains(otherLazyContainer),
        "\(otherLazyContainer) inside tasksListView re-creates the non-convergent lazy-in-lazy layout that beachballed the Tasks page on scroll"
      )
    }
  }

  func testRowsAreDirectItemsOfTheLazyStackNotANestedContainer() throws {
    let list = try tasksListViewSource()

    XCTAssertTrue(
      list.contains("ForEach(tasksListItems)"),
      "the list must render the flat TasksListItem stream so each row is its own lazy item"
    )
    XCTAssertTrue(
      list.contains("case .taskRow(let task, let category, let sectionTasks):"),
      "row items must render through the per-row taskCategoryRow builder; a section-shaped container re-materializes every row on navigate"
    )
    XCTAssertFalse(
      list.contains("ForEach(visibleTasks)"),
      "the eager per-section row loop is gone; rows come from the flat item stream, not a section-local container"
    )
  }

  func testTheOldEagerSectionContainerIsGone() throws {
    let source = try sourceFile("MainWindow/Pages/TasksPage.swift")

    XCTAssertFalse(
      source.contains("struct TaskCategorySection: View"),
      "TaskCategorySection held an eager stack of ALL its rows inside one lazy item, which is what made navigate-away tear down every row; the flattened TasksListItem stream replaced it"
    )
  }

  func testRowItemsKeepTheTaskIdAsTheirIdentity() {
    // Keyboard navigation scrolls with `scrollProxy.scrollTo(task.id)`, so a
    // row item's identity must stay the task's own id, and header ids must
    // never collide with a task id.
    let task = TaskActionItem(
      id: "backend-action-item",
      description: "Follow up",
      completed: false,
      createdAt: Date(),
      taskId: "canonical-task"
    )

    XCTAssertEqual(
      TasksListItem.taskRow(task, category: .today, sectionTasks: [task]).id,
      task.id,
      "row items must keep the task's id so scrollTo(task.id) still lands on the row inside the virtualized list"
    )
    XCTAssertEqual(
      TasksListItem.sectionHeader(.today, sectionTasks: [task]).id,
      "tasks-section-header-Today",
      "header ids are namespaced and stable per category"
    )
    XCTAssertNotEqual(
      TasksListItem.sectionHeader(.today, sectionTasks: [task]).id,
      task.id
    )
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    // omi-test-quality: source-inspection -- static contract: lazy-in-lazy nesting and flat row virtualization are SwiftUI layout-livelock properties no value-level unit test can observe, so only the page source can hold the shape.
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
