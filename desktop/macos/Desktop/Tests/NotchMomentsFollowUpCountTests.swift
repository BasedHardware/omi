import XCTest

@testable import Omi_Computer

/// Regression tests for the conversation-end "N follow-ups ready" count.
/// The count must reflect only follow-ups the just-ended conversation produced —
/// never the whole open-task backlog, and never older tasks that pagination or a
/// cross-device sync brings in mid-session (new ids, but stale `createdAt`).
final class NotchMomentsFollowUpCountTests: XCTestCase {
  private func task(_ id: String, createdAt: Date) -> TaskActionItem {
    TaskActionItem(id: id, description: id, completed: false, createdAt: createdAt)
  }

  private let sessionStart = Date(timeIntervalSince1970: 1_000_000)

  func testExcludesPreExistingBacklog() {
    // Two tasks already open when the conversation started → baseline. No new tasks.
    let baseline: Set<String> = ["a", "b"]
    let tasks = [
      task("a", createdAt: sessionStart.addingTimeInterval(-3600)),
      task("b", createdAt: sessionStart.addingTimeInterval(-60)),
    ]
    XCTAssertEqual(
      NotchMomentsCoordinator.followUpCount(tasks: tasks, baselineIds: baseline, since: sessionStart), 0)
  }

  func testCountsOnlyTasksCreatedDuringSession() {
    let baseline: Set<String> = ["a"]
    let tasks = [
      task("a", createdAt: sessionStart.addingTimeInterval(-3600)),  // backlog
      task("new1", createdAt: sessionStart.addingTimeInterval(30)),  // produced now
      task("new2", createdAt: sessionStart.addingTimeInterval(90)),  // produced now
    ]
    XCTAssertEqual(
      NotchMomentsCoordinator.followUpCount(tasks: tasks, baselineIds: baseline, since: sessionStart), 2)
  }

  func testExcludesPaginatedOrSyncedOlderTasks() {
    // A new id (not in baseline) but with a `createdAt` before the session start —
    // e.g. an older task paginated in or synced from another device mid-recording.
    let baseline: Set<String> = ["a"]
    let tasks = [
      task("a", createdAt: sessionStart.addingTimeInterval(-3600)),
      task("older", createdAt: sessionStart.addingTimeInterval(-120)),  // must NOT count
      task("new", createdAt: sessionStart.addingTimeInterval(45)),  // counts
    ]
    XCTAssertEqual(
      NotchMomentsCoordinator.followUpCount(tasks: tasks, baselineIds: baseline, since: sessionStart), 1)
  }

  func testNilStartFallsBackToBaselineDiff() {
    // When the start time is unknown, fall back to id-diff only.
    let baseline: Set<String> = ["a"]
    let tasks = [
      task("a", createdAt: sessionStart),
      task("new", createdAt: sessionStart),
    ]
    XCTAssertEqual(
      NotchMomentsCoordinator.followUpCount(tasks: tasks, baselineIds: baseline, since: nil), 1)
  }

  func testReceiptRequiresMatchingActiveCanonicalTask() {
    let observed = task("task-1", createdAt: sessionStart)
    let canonical = task("task-1", createdAt: sessionStart)

    XCTAssertTrue(NotchMomentsCoordinator.isReceiptConfirmation(observed, canonical))
    XCTAssertFalse(
      NotchMomentsCoordinator.isReceiptConfirmation(
        observed,
        task("different-task", createdAt: sessionStart)),
      "a different canonical task must never acknowledge the observed cache insert")
  }

  func testReceiptRejectsCompletedOrRetiredCanonicalTask() {
    let observed = task("task-1", createdAt: sessionStart)
    let completed = TaskActionItem(id: "task-1", description: "task-1", completed: true, createdAt: sessionStart)
    let retired = TaskActionItem(
      id: "task-1", description: "task-1", completed: false, createdAt: sessionStart, deleted: true)

    XCTAssertFalse(NotchMomentsCoordinator.isReceiptConfirmation(observed, completed))
    XCTAssertFalse(NotchMomentsCoordinator.isReceiptConfirmation(observed, retired))
  }
}
