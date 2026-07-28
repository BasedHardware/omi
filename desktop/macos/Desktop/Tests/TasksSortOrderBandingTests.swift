import XCTest

@testable import Omi_Computer

/// Covers the two remaining tasks-integrity defects fixed in this slice:
///   - BL-016: the sortOrder scheme must keep every item inside its category's
///     numeric band, even for large categories that overflowed the old fixed
///     1000-spacing (hard ceiling ~100 items → cross-band collision).
///   - BL-030: end-of-drag reset must be task-id-scoped so a late deinit from a
///     prior drag can't clear a newer drag's dim state.
final class TasksSortOrderBandingTests: XCTestCase {

  // MARK: - BL-016: band containment (logic)

  private var categoryCount: Int { TaskCategory.allCases.count }

  /// A category with far more than the old ~100-item ceiling must keep every
  /// order strictly inside its own band and strictly increasing.
  func testLargeCategoryStaysInsideItsBandAndIsMonotonic() {
    let band = TasksViewModel.sortOrderBandWidth
    let count = 150  // TASK-04 exercises 150 reorders; comfortably past the old ceiling

    for categoryIndex in 0..<categoryCount {
      let lower = categoryIndex * band
      let upper = (categoryIndex + 1) * band
      var previous = Int.min
      for itemIndex in 0..<count {
        let value = TasksViewModel.sortOrder(
          categoryIndex: categoryIndex, itemIndex: itemIndex, itemCount: count)
        XCTAssertGreaterThanOrEqual(
          value, lower, "item \(itemIndex) fell below category \(categoryIndex)'s band")
        XCTAssertLessThan(
          value, upper,
          "item \(itemIndex) of \(count) overflowed category \(categoryIndex)'s band (BL-016)")
        XCTAssertGreaterThan(
          value, previous, "sortOrder must be strictly increasing within a category")
        previous = value
      }
    }
  }

  /// The direct cross-band collision from BL-016: at scale, the last item of one
  /// category must stay below the first item of the next category's band.
  func testAdjacentCategoriesDoNotCollideAtScale() {
    let count = 150
    for categoryIndex in 0..<(categoryCount - 1) {
      let lastOfThis = TasksViewModel.sortOrder(
        categoryIndex: categoryIndex, itemIndex: count - 1, itemCount: count)
      let firstOfNext = TasksViewModel.sortOrder(
        categoryIndex: categoryIndex + 1, itemIndex: 0, itemCount: count)
      XCTAssertLessThan(
        lastOfThis, firstOfNext,
        "category \(categoryIndex)'s last item collided into category \(categoryIndex + 1)'s band (BL-016)")
    }
  }

  /// Regression: the old fixed scheme (`categoryIndex*band + (itemIndex+1)*1000`)
  /// overflowed the band at ~100 items; the new scheme must not.
  func testOldFixedSchemeOverflowedButNewSchemeDoesNot() {
    let band = TasksViewModel.sortOrderBandWidth
    let count = 150
    let overflowIndex = 100  // the 101st item — old value = 101 * 1000 = 101_000 ≥ band

    let oldValue = 0 * band + (overflowIndex + 1) * 1000
    XCTAssertGreaterThanOrEqual(
      oldValue, band, "sanity: the old fixed scheme is expected to overflow here")

    let newValue = TasksViewModel.sortOrder(
      categoryIndex: 0, itemIndex: overflowIndex, itemCount: count)
    XCTAssertLessThan(
      newValue, band, "new scheme must keep the 101st item inside its band (BL-016)")
  }

  /// Copilot boundary review: once `itemCount >= bandWidth` the derived integer
  /// spacing floors to 0, so a naive `(itemIndex+1)*max(1,spacing)` would land the
  /// last item on the next band's base. The degenerate branch must keep every item
  /// strictly inside its band (ordering non-decreasing) even at that unreachable scale.
  func testDegenerateOversizedCategoryStaysInsideBand() {
    let band = TasksViewModel.sortOrderBandWidth
    let categoryIndex = 2
    let base = categoryIndex * band
    for count in [band, band + 1, band + 5000] {
      var previous = Int.min
      for itemIndex in [0, 1, count / 2, count - 2, count - 1] {
        let value = TasksViewModel.sortOrder(
          categoryIndex: categoryIndex, itemIndex: itemIndex, itemCount: count)
        XCTAssertGreaterThanOrEqual(
          value, base, "count \(count) item \(itemIndex) underflowed its band")
        XCTAssertLessThan(
          value, base + band,
          "count \(count) item \(itemIndex) overflowed its band (degenerate boundary)")
        XCTAssertGreaterThanOrEqual(
          value, previous, "degenerate ordering must stay non-decreasing")
        previous = value
      }
    }
  }

  /// Backward compatibility: small categories keep the historical sparse 1000
  /// spacing, so orders already persisted under the old scheme are unchanged.
  func testSmallCategoryKeepsHistoricalSparseSpacing() {
    let band = TasksViewModel.sortOrderBandWidth
    let count = 5
    for categoryIndex in 0..<categoryCount {
      for itemIndex in 0..<count {
        let value = TasksViewModel.sortOrder(
          categoryIndex: categoryIndex, itemIndex: itemIndex, itemCount: count)
        let legacy = categoryIndex * band + (itemIndex + 1) * 1000
        XCTAssertEqual(
          value, legacy,
          "small category spacing must match the legacy 1000 scheme for compatibility")
      }
    }
  }

  // MARK: - BL-016 + BL-030: source-scrape guards against regression

  private func tasksPageSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Pages/TasksPage.swift")
    return try String(contentsOf: sourceURL)
  }

  /// Both reorder sites must band through the shared helper, and the fixed
  /// `(index + 1) * 1000` / `(index + 1) * 1000` literals must be gone.
  ///
  /// The drag path bands via `applyReorder` (which `moveTask` delegates to so it
  /// rewrites every mirrored array — see `TaskReorderMirroredArraysTests`); the sync
  /// path bands via `collectSortOrderUpdates`. Both call `Self.sortOrder`.
  func testBothSortSitesUseSharedHelper() throws {
    let source = try tasksPageSource()

    XCTAssertTrue(
      source.contains("static func sortOrder(categoryIndex: Int, itemIndex: Int, itemCount: Int) -> Int"),
      "the shared sortOrder helper must exist so both sort sites agree (BL-016)")

    // applyReorder (drag path) + collectSortOrderUpdates (sync path) → two call sites.
    let callSites = source.components(separatedBy: "Self.sortOrder(categoryIndex:").count - 1
    XCTAssertGreaterThanOrEqual(
      callSites, 2,
      "both reorder sites (applyReorder + collectSortOrderUpdates) must call the shared helper (BL-016)")

    // moveTask must route its reorder through applyReorder, so its banding — and the
    // mirrored-array agreement it guarantees — goes through the shared helper too.
    XCTAssertTrue(
      source.contains("Self.applyReorder("),
      "moveTask must band via applyReorder rather than an inline scheme (BL-016 / TASK-07)")

    XCTAssertFalse(
      source.contains("categoryOffset + (index + 1) * 1000"),
      "the fixed-spacing scheme with a hard ~100-item ceiling must be gone (BL-016)")
  }

  /// The end-of-drag reset must be task-id-scoped, not merely non-nil-gated.
  func testDragEndResetIsTaskIdScoped() throws {
    let source = try tasksPageSource()

    XCTAssertTrue(
      source.contains("guard viewModel.draggedTaskId == endedId else { return }"),
      "drag-end must clear only when the ending task is still the dragged one (BL-030)")
    XCTAssertFalse(
      source.contains("guard viewModel.draggedTaskId != nil else { return }"),
      "the non-scoped drag-end guard let a stale prior-drag deinit clobber a new drag (BL-030)")
  }

  /// The provider must carry its own task id and pass it through deinit so a
  /// late release from a prior drag identifies itself.
  func testDragItemProviderPassesItsOwnTaskId() throws {
    let source = try tasksPageSource()

    XCTAssertTrue(
      source.contains("private let taskId: String"),
      "TaskDragItemProvider must retain the dragged task's id (BL-030)")
    XCTAssertTrue(
      source.contains("let onEnd: @Sendable (String) -> Void"),
      "TaskDragItemProvider must fire an id-carrying end callback (BL-030)")
    XCTAssertTrue(
      source.contains("DispatchQueue.main.async { cb(endedId) }"),
      "deinit must forward its own task id to the id-scoped end handler (BL-030)")
  }
}
