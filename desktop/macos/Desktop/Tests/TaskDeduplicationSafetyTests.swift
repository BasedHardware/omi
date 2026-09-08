import XCTest

@testable import Omi_Computer

/// Regression test for a data-loss bug in staged-task deduplication: the model's
/// delete_ids were filtered only for existence, never excluding the group's own
/// keep_id. A response like `{keep_id: t1, delete_ids: [t1, t2]}` (a known LLM
/// failure mode for "pick one, delete the rest") hard-deleted BOTH t1 and t2,
/// destroying the task the group said to keep. keep_ids from other groups were
/// unprotected too.
final class TaskDeduplicationSafetyTests: XCTestCase {

  func testKeepIdInSameGroupDeleteIdsIsNotDeleted() {
    let safe = TaskDeduplicationService.safeDeleteIDs(
      deleteIDs: ["t1", "t2"],
      validTaskIDs: ["t1", "t2", "t3"],
      protectedKeepIDs: ["t1"]
    )
    XCTAssertEqual(safe, ["t2"], "the kept task must never be among the deletions")
    XCTAssertFalse(safe.contains("t1"))
  }

  func testKeepIdFromAnotherGroupIsProtected() {
    // t3 is a keep_id of another group but appears in this group's delete_ids.
    let safe = TaskDeduplicationService.safeDeleteIDs(
      deleteIDs: ["t3", "t4"],
      validTaskIDs: ["t2", "t3", "t4"],
      protectedKeepIDs: ["t1", "t3"]
    )
    XCTAssertEqual(safe, ["t4"])
  }

  func testUnknownDeleteIdsAreStillFilteredOut() {
    let safe = TaskDeduplicationService.safeDeleteIDs(
      deleteIDs: ["t2", "ghost"],
      validTaskIDs: ["t1", "t2"],
      protectedKeepIDs: ["t1"]
    )
    XCTAssertEqual(safe, ["t2"])
  }

  func testNormalDuplicateClusterStillDeletesTheRest() {
    let safe = TaskDeduplicationService.safeDeleteIDs(
      deleteIDs: ["t2", "t3"],
      validTaskIDs: ["t1", "t2", "t3"],
      protectedKeepIDs: ["t1"]
    )
    XCTAssertEqual(safe, ["t2", "t3"])
  }
}
