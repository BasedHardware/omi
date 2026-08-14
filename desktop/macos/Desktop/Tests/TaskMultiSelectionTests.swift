import XCTest

@testable import Omi_Computer

final class TaskMultiSelectionTests: XCTestCase {
  func testPlainCommandAndShiftClicksUseDeterministicAnchorAndRange() {
    var state = TaskMultiSelectionState()
    state.enter()

    XCTAssertTrue(state.click("b", visibleIDs: ["a", "b", "c", "d"]))
    XCTAssertEqual(state.selectedIDs(in: ["a", "b", "c", "d"]), ["b"])
    XCTAssertEqual(state.anchorID, "b")

    XCTAssertTrue(state.click("d", modifiers: .command, visibleIDs: ["a", "b", "c", "d"]))
    XCTAssertEqual(state.selectedIDs(in: ["a", "b", "c", "d"]), ["b", "d"])
    XCTAssertEqual(state.anchorID, "d")

    XCTAssertTrue(state.click("c", modifiers: .shift, visibleIDs: ["a", "b", "c", "d"]))
    XCTAssertEqual(state.selectedIDs(in: ["a", "b", "c", "d"]), ["b", "c", "d"])
    XCTAssertEqual(state.anchorID, "d", "shift-click does not move the range anchor")

    XCTAssertTrue(state.click("b", modifiers: .command, visibleIDs: ["a", "b", "c", "d"]))
    XCTAssertEqual(state.selectedIDs(in: ["a", "b", "c", "d"]), ["c", "d"])
    XCTAssertTrue(state.click("d", modifiers: .command, visibleIDs: ["a", "b", "c", "d"]))
    XCTAssertEqual(state.selectedIDs(in: ["a", "b", "c", "d"]), ["c"])
  }

  func testFilteringReorderingAndRefreshPreserveOnlyExistingSelections() {
    var state = TaskMultiSelectionState()
    state.enter()
    _ = state.click("a", visibleIDs: ["a", "b", "c"])
    _ = state.click("c", modifiers: .command, visibleIDs: ["a", "b", "c"])

    state.reconcile(visibleIDs: ["c", "b"])
    XCTAssertEqual(state.selectedIDs(in: ["c", "b"]), ["c", "a"], "filtered-out a remains selected")

    state.reconcile(visibleIDs: ["b", "c", "a"])
    XCTAssertEqual(state.selectedIDs(in: ["b", "c", "a"]), ["c", "a"], "reorder changes action order only")

    state.reconcile(visibleIDs: ["b", "a"], availableTaskIDs: ["a", "b"])
    XCTAssertEqual(state.selectedIDs(in: ["b", "a"]), ["a"])
    XCTAssertNil(state.anchorID, "refresh/deletion prunes an anchor that no longer exists")
  }

  func testCommandAIsScopedToVisibleRowsAndEscapeExitsExplicitMode() {
    var state = TaskMultiSelectionState()
    state.enter()
    _ = state.click("hidden", visibleIDs: ["hidden", "visible"])
    state.reconcile(visibleIDs: ["visible"])

    XCTAssertTrue(
      state.handleKeyboard(.selectAll, visibleIDs: ["visible"]),
      "Command+A is handled while multi-select mode is active")
    XCTAssertEqual(state.selectedIDs(in: ["visible"]), ["visible", "hidden"])

    XCTAssertTrue(state.handleKeyboard(.escape, visibleIDs: ["visible"]))
    XCTAssertFalse(state.isActive)
    XCTAssertTrue(state.selectedIDs.isEmpty)
    XCTAssertNil(state.anchorID)
  }

  func testSelectAllToggleDoesNotDiscardHiddenSelection() {
    var state = TaskMultiSelectionState()
    state.enter()
    _ = state.click("hidden", visibleIDs: ["hidden", "a"])

    state.toggleSelectAll(visibleIDs: ["a", "b"])
    XCTAssertEqual(state.selectedIDs(in: ["a", "b"]), ["a", "b", "hidden"])

    state.toggleSelectAll(visibleIDs: ["a", "b"])
    XCTAssertEqual(state.selectedIDs(in: ["a", "b"]), ["hidden"])
  }

  func testDeselectAllClearsVisibleAndHiddenRowsButKeepsSelectionModeActive() {
    var state = TaskMultiSelectionState()
    state.enter()
    state.selectAll(visibleIDs: ["visible", "off-page"])
    state.reconcile(visibleIDs: ["visible"])

    state.deselectAll()

    XCTAssertTrue(state.isActive)
    XCTAssertEqual(state.selectionCount, 0)
    XCTAssertTrue(state.selectedIDs.isEmpty)
    XCTAssertNil(state.anchorID)
  }
}
