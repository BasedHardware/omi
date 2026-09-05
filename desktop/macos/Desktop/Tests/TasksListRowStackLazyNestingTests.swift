import XCTest

@testable import Omi_Computer

/// The Tasks list must never nest a lazy container inside a lazy item.
///
/// The regression this guards was a full app freeze, not a slow frame: each
/// category section (`TaskCategorySection`) is an item of the `LazyVStack` in
/// `tasksListView`, and the section laid its rows out in a nested `LazyVStack`.
/// A lazy stack nested inside a lazy item makes the section's measured height
/// non-convergent — the inner stack reports estimates while the outer measures
/// it and real heights once it is placed — so every layout pass mutated
/// lazy-item phases and re-signaled prefetch, each scheduling another
/// transaction. The transaction flush never drained and the main thread
/// beachballed permanently on scroll (QA freeze: 2627/2627 main-thread samples
/// inside `GraphHost.flushTransactions`, dominated by
/// `LazyStack<>.measureEstimates` and `LazyLayoutViewCache.updateItemPhase`).
///
/// The contract below is structural, so it is held by source inspection: a unit
/// test cannot reach SwiftUI's transaction machinery without hosting a run.
final class TasksListRowStackLazyNestingTests: XCTestCase {
  /// The section source, scoped so a lazy container elsewhere in the page
  /// (the outer list, a popover grid) cannot satisfy or trip this contract.
  private func taskCategorySectionSource() throws -> String {
    let source = try sourceFile("MainWindow/Pages/TasksPage.swift")
    let start = try XCTUnwrap(
      source.range(of: "struct TaskCategorySection: View {"),
      "TaskCategorySection moved or was renamed; update this guard's anchor"
    )
    let end = try XCTUnwrap(
      source.range(of: "\nstruct TaskDragDropModifier: ViewModifier {", range: start.upperBound..<source.endIndex),
      "TaskCategorySection's end anchor moved; update this guard"
    )
    return String(source[start.lowerBound..<end.lowerBound])
  }

  func testCategoryRowsAreNotLaidOutInALazyContainer() throws {
    let section = try taskCategorySectionSource()

    // omi-test-quality: source-inspection -- static contract: no lazy container may nest
    // inside the outer list's lazy items; the livelock it causes is invisible to a
    // value-level unit test.
    for lazyContainer in ["LazyVStack", "LazyHStack", "LazyVGrid", "LazyHGrid"] {
      XCTAssertFalse(
        section.contains(lazyContainer),
        "\(lazyContainer) inside TaskCategorySection re-creates the non-convergent lazy-in-lazy layout that beachballed the Tasks page on scroll"
      )
    }
  }

  func testCategoryRowsKeepTheirEagerStack() throws {
    let section = try taskCategorySectionSource()

    XCTAssertTrue(
      section.contains("VStack(spacing: OmiSpacing.sm) {"),
      "the category row stack disappeared; the rows must still sit in one eager container so the outer lazy list's section heights converge"
    )
  }

  func testTheOuterListStaysTheLazyVirtualizer() throws {
    let source = try sourceFile("MainWindow/Pages/TasksPage.swift")

    XCTAssertTrue(
      source.contains("LazyVStack(alignment: .leading, spacing: OmiSpacing.lg) {"),
      "tasksListView's outer LazyVStack is the page's virtualizer; eagerness belongs to the rows inside a section, not to the list itself"
    )
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
