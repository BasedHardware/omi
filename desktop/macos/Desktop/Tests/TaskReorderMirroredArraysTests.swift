import XCTest

@testable import Omi_Computer

/// TASK-07: a reorder must keep the three source arrays the displayed task list can
/// be backed by — `store.incompleteTasks`, `filteredFromDatabase`, `searchResults` —
/// in agreement. `TasksViewModel.moveTask` writes the new sortOrders to all three via
/// the single `applyReorder` helper; writing to only one diverges when filters/search
/// are active (BL-030, fixed in #9121). These pin that helper's guarantees: the same
/// order yields identical sortOrders for shared ids, monotonic with position, disjoint
/// per category band, and leaves ids outside the order untouched.
final class TaskReorderMirroredArraysTests: XCTestCase {

  private func item(_ id: String, sortOrder: Int? = nil) -> TaskActionItem {
    TaskActionItem(
      id: id, description: id, completed: false,
      createdAt: Date(timeIntervalSince1970: 0), dueAt: nil, sortOrder: sortOrder)
  }

  private func sortOrder(_ arr: [TaskActionItem], _ id: String) -> Int? {
    arr.first { $0.id == id }?.sortOrder
  }

  func testSharedIdsGetIdenticalSortOrderAcrossArrays() {
    // The three arrays hold overlapping-but-different subsets in shuffled positions,
    // exactly the filters/search-active case BL-030 was about.
    let order = ["a", "b", "c", "d"]
    let categoryIndex = 1
    var incomplete = [item("d"), item("a"), item("b"), item("c")]  // full set, shuffled
    var filtered = [item("b"), item("a")]  // subset
    var search = [item("c"), item("d"), item("a")]  // different subset

    TasksViewModel.applyReorder(order, categoryIndex: categoryIndex, to: &incomplete)
    TasksViewModel.applyReorder(order, categoryIndex: categoryIndex, to: &filtered)
    TasksViewModel.applyReorder(order, categoryIndex: categoryIndex, to: &search)

    for id in order {
      let values = [
        sortOrder(incomplete, id), sortOrder(filtered, id), sortOrder(search, id),
      ].compactMap { $0 }
      guard let first = values.first else { continue }
      XCTAssertTrue(
        values.allSatisfy { $0 == first },
        "id \(id) must have the SAME sortOrder in every array that holds it; got \(values)")
    }
  }

  func testSortOrderIsMonotonicAndUniqueWithOrderPosition() {
    let order = ["a", "b", "c", "d"]
    var arr = [item("c"), item("a"), item("d"), item("b")]
    TasksViewModel.applyReorder(order, categoryIndex: 0, to: &arr)

    let orders = order.compactMap { sortOrder(arr, $0) }
    XCTAssertEqual(orders.count, order.count, "every reordered id gets a sortOrder")
    XCTAssertEqual(
      orders, orders.sorted(),
      "sortOrder must increase with position in `order` so the displayed order matches")
    XCTAssertEqual(Set(orders).count, orders.count, "sortOrders within a category must be unique")
  }

  func testIdsAbsentFromOrderKeepTheirSortOrder() {
    // A task not part of the reordered category must not be re-banded — the reorder is
    // scoped to `order`, so a stale/other-category row is left alone.
    let order = ["a", "b"]
    var arr = [item("a"), item("b"), item("z", sortOrder: 12345)]
    TasksViewModel.applyReorder(order, categoryIndex: 2, to: &arr)

    XCTAssertEqual(sortOrder(arr, "z"), 12345, "an id outside `order` must keep its sortOrder")
    XCTAssertNotNil(sortOrder(arr, "a"), "an id in `order` is assigned a sortOrder")
    XCTAssertNotNil(sortOrder(arr, "b"))
  }

  func testDifferentCategoriesBandIntoDisjointRanges() {
    // categoryIndex bands sortOrders so categories never interleave; two arrays under
    // different category indices must not collide.
    let order = ["a", "b", "c"]
    var cat0 = [item("a"), item("b"), item("c")]
    var cat1 = [item("a"), item("b"), item("c")]
    TasksViewModel.applyReorder(order, categoryIndex: 0, to: &cat0)
    TasksViewModel.applyReorder(order, categoryIndex: 1, to: &cat1)

    let cat0Max = cat0.compactMap { $0.sortOrder }.max() ?? .max
    let cat1Min = cat1.compactMap { $0.sortOrder }.min() ?? .min
    XCTAssertLessThan(cat0Max, cat1Min, "category 0's band must sit entirely below category 1's")
  }

  /// BL-030 regression guard: `moveTask` must fan the reorder out to ALL THREE mirrored
  /// arrays — dropping any one diverges when filters/search are active. `moveTask` is
  /// `@MainActor` and needs the full store/state, so the fan-out is source-pinned by the
  /// exact call sites (the helper's own correctness is covered behaviourally above).
  func testMoveTaskFansReorderOutToAllThreeMirroredArrays() throws {
    let source = try tasksPageSource()
    for target in ["&incomplete", "&filteredFromDatabase", "&searchResults"] {
      XCTAssertTrue(
        source.contains("Self.applyReorder(order, categoryIndex: categoryIndex, to: \(target))"),
        "moveTask must apply the reorder to \(target) so all three mirrored arrays agree (BL-030)")
    }
  }

  private func tasksPageSource() throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Pages/TasksPage.swift")
    return try String(contentsOf: url, encoding: .utf8)
  }
}
