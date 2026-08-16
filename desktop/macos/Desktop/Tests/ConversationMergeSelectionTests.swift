import XCTest

@testable import Omi_Computer

/// Regression coverage for `ConversationMergeSelection`, the pure selection logic
/// behind the conversation multi-select / merge feature. Two things it guards:
/// (1) the feature now has a reachable entry point at all, and (2) "Select All"
/// is scoped to the currently displayed list, so in search mode it selects the
/// visible search results rather than the entire conversation list.
final class ConversationMergeSelectionTests: XCTestCase {

  func testSelectAllOverDisplayedListAddsAllDisplayed() {
    let displayed = ["a", "b", "c"]
    let result = ConversationMergeSelection.toggledSelectAll(displayedIds: displayed, current: [])
    XCTAssertEqual(result, ["a", "b", "c"])
  }

  func testSelectAllIsScopedToDisplayedListInSearchMode() {
    // Full list is a,b,c,d but only search results a,b are displayed. Select
    // All must select only the displayed results, not the whole list.
    let displayed = ["a", "b"]
    let result = ConversationMergeSelection.toggledSelectAll(displayedIds: displayed, current: [])
    XCTAssertEqual(result, ["a", "b"])
    XCTAssertFalse(result.contains("c"))
    XCTAssertFalse(result.contains("d"))
  }

  func testDeselectAllRemovesOnlyDisplayedAndKeepsOthers() {
    // Selection includes an id from another view (x). Deselecting the
    // displayed set must leave that untouched.
    let displayed = ["a", "b"]
    let current: Set<String> = ["a", "b", "x"]
    let result = ConversationMergeSelection.toggledSelectAll(displayedIds: displayed, current: current)
    XCTAssertEqual(result, ["x"])
  }

  func testAllDisplayedSelectedReflectsDisplayedSubset() {
    XCTAssertTrue(
      ConversationMergeSelection.allDisplayedSelected(
        displayedIds: ["a", "b"], current: ["a", "b", "x"]))
    XCTAssertFalse(
      ConversationMergeSelection.allDisplayedSelected(
        displayedIds: ["a", "b", "c"], current: ["a", "b"]))
  }

  func testEmptyDisplayedListIsNeverAllSelectedAndIsANoOp() {
    XCTAssertFalse(
      ConversationMergeSelection.allDisplayedSelected(displayedIds: [], current: ["a"]))
    XCTAssertEqual(
      ConversationMergeSelection.toggledSelectAll(displayedIds: [], current: ["a"]), ["a"])
  }
}
