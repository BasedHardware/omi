import XCTest

@testable import Omi_Computer

final class TaskSortOrderPlannerTests: XCTestCase {
  func testMovedRowWritesOnlyThatIDIntoAnExistingGap() {
    let result = plan(
      orderedIDs: ["first", "moved", "last"],
      existingRanks: ["first": 100, "moved": 50, "last": 950],
      affectedIDs: ["moved"]
    )

    XCTAssertEqual(result, .incremental(["moved": 525]))
  }

  func testFirstInsertionUsesCategoryBaseSentinel() {
    let result = plan(
      orderedIDs: ["moved", "anchor"],
      existingRanks: ["moved": 390, "anchor": 350],
      affectedIDs: ["moved"],
      categoryIndex: 3,
      bandWidth: 100
    )

    XCTAssertEqual(result, .incremental(["moved": 325]))
  }

  func testLastInsertionUsesCategoryUpperBoundSentinel() {
    let result = plan(
      orderedIDs: ["anchor", "moved"],
      existingRanks: ["anchor": 350, "moved": 310],
      affectedIDs: ["moved"],
      categoryIndex: 3,
      bandWidth: 100
    )

    XCTAssertEqual(result, .incremental(["moved": 375]))
  }

  func testSamePositionProducesNoUpdate() {
    let result = plan(
      orderedIDs: ["first", "moved", "last"],
      existingRanks: ["first": 100, "moved": 525, "last": 950],
      affectedIDs: ["moved"]
    )

    XCTAssertEqual(result, .incremental([:]))
  }

  func testConsecutiveAffectedRowsAreAllocatedInIncreasingOrder() {
    let result = plan(
      orderedIDs: ["first", "move-a", "move-b", "last"],
      existingRanks: ["first": 100, "move-a": 900, "move-b": 50, "last": 950],
      affectedIDs: ["move-a", "move-b"]
    )

    XCTAssertEqual(result, .incremental(["move-a": 383, "move-b": 666]))
  }

  func testExhaustedIntegerGapNeedsRebalance() {
    let result = plan(
      orderedIDs: ["first", "moved", "last"],
      existingRanks: ["first": 100, "moved": 400, "last": 101],
      affectedIDs: ["moved"]
    )

    XCTAssertEqual(result, .needsRebalance)
  }

  func testInvalidLegacyRanksNeedRebalance() {
    let cases: [(String, [String: Int])] = [
      (
        "duplicate",
        ["first": 110, "moved": 130, "last": 110]
      ),
      (
        "nil",
        ["first": 110, "moved": 130]
      ),
      (
        "out-of-band",
        ["first": 99, "moved": 130, "last": 150]
      ),
      (
        "category-base-sentinel",
        ["first": 100, "moved": 130, "last": 150]
      ),
    ]

    for (label, existingRanks) in cases {
      XCTAssertEqual(
        plan(
          orderedIDs: ["first", "moved", "last"],
          existingRanks: existingRanks,
          affectedIDs: ["moved"],
          categoryIndex: 1,
          bandWidth: 100
        ),
        .needsRebalance,
        label
      )
    }
  }

  func testLocalRowsParticipateInSQLiteRanksWhileStagedRowsRemainExcluded() {
    let result = plan(
      orderedIDs: ["anchor", "local_draft", "moved", "staged_draft", "tail"],
      existingRanks: ["anchor": 100, "local_draft": 900, "moved": 50, "tail": 950],
      affectedIDs: ["local_draft", "moved", "staged_draft"]
    )

    XCTAssertEqual(result, .incremental(["local_draft": 383, "moved": 666]))
  }

  func testFilteredDesiredOrderKeepsHiddenRowAsAnUnchangedAnchor() {
    // This is the full canonical order after a filtered drag. The hidden row
    // remains present so the moved row is allocated around its existing rank.
    let result = plan(
      orderedIDs: ["top", "moved", "hidden", "bottom"],
      existingRanks: ["top": 100, "moved": 900, "hidden": 400, "bottom": 800],
      affectedIDs: ["moved"]
    )

    XCTAssertEqual(result, .incremental(["moved": 250]))
  }

  func testHiddenRowRebaseUsesPreMutationRankForMovedRow() {
    let canonical = TasksViewModel.canonicalPreMutationTaskIDs(
      currentTasks: [
        (id: "hidden-before", sortOrder: 100),
        (id: "hidden-middle", sortOrder: 300),
        (id: "moved", sortOrder: 450),
        (id: "bottom", sortOrder: 800),
      ],
      originalSortOrders: ["moved": 200]
    )

    XCTAssertEqual(canonical, ["hidden-before", "moved", "hidden-middle", "bottom"])
    XCTAssertEqual(
      TasksViewModel.rebaseVisibleTaskIDs(
        fullOrder: canonical,
        reorderedVisibleIDs: ["bottom", "moved"]
      ),
      ["hidden-before", "bottom", "hidden-middle", "moved"]
    )
  }

  func testDeletedPendingIDCannotConsumeRebaseReplacementSlot() {
    XCTAssertEqual(
      TasksViewModel.rebaseVisibleTaskIDs(
        fullOrder: ["first", "second", "third"],
        reorderedVisibleIDs: ["second", "deleted-during-debounce", "first"]
      ),
      ["second", "first", "third"]
    )
  }

  func testPendingReorderRemapsLocalIDAfterBackendPromotion() {
    let promoted = TasksViewModel.remappedTaskIDs(
      ["anchor", "local_42", "tail"],
      using: ["local_42": "backend-42"]
    )

    XCTAssertEqual(promoted, ["anchor", "backend-42", "tail"])
    XCTAssertEqual(
      TasksViewModel.persistedTaskIDs(
        reorderedIDs: promoted,
        currentIDs: ["anchor", "backend-42", "tail"]
      ),
      promoted,
      "the promoted row must remain in the pending order used for persistence"
    )
  }

  func testPendingReorderReloadsCompleteSnapshotAfterLateBackendPromotion() {
    // The SQLite snapshot may have been read while the row still surfaced as
    // local_42, then promotion can be observed before planning finishes. The
    // refreshed snapshot must use the same backend identity as the remapped
    // pending order instead of silently dropping the moved row.
    let refreshedSnapshot = TasksViewModel.remappedTaskIDs(
      ["anchor", "local_42", "tail"],
      using: ["local_42": "backend-42"]
    )

    XCTAssertEqual(refreshedSnapshot, ["anchor", "backend-42", "tail"])
    XCTAssertEqual(
      TasksViewModel.persistedTaskIDs(
        reorderedIDs: ["tail", "backend-42", "anchor"],
        currentIDs: refreshedSnapshot
      ),
      ["tail", "backend-42", "anchor"]
    )
  }

  private func plan(
    orderedIDs: [String],
    existingRanks: [String: Int],
    affectedIDs: Set<String>,
    categoryIndex: Int = 0,
    bandWidth: Int = 1_000
  ) -> TaskSortOrderPlanner.Result {
    TaskSortOrderPlanner.plan(
      orderedIDs: orderedIDs,
      existingRanks: existingRanks,
      affectedIDs: affectedIDs,
      categoryIndex: categoryIndex,
      bandWidth: bandWidth
    )
  }
}
