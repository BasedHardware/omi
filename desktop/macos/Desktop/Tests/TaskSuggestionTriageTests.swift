import XCTest

@testable import Omi_Computer

/// `TaskActionItem.isPendingSuggestion` still names AI-captured action items so
/// proactive nudges can skip leftover extractor rows. Those rows are ordinary
/// due-date tasks everywhere the user or the assistant reads the list; Candidate
/// review is a separate surface.
final class TaskSuggestionTriageTests: XCTestCase {

  private func task(
    source: String?,
    completed: Bool = false,
    deleted: Bool? = nil
  ) -> TaskActionItem {
    TaskActionItem(
      id: "t1",
      description: "Send the investor update email to Bob",
      completed: completed,
      createdAt: Date(),
      source: source,
      deleted: deleted
    )
  }

  func testAICapturedOpenTaskIsAPendingSuggestion() {
    XCTAssertTrue(task(source: "screenshot").isPendingSuggestion)
    XCTAssertTrue(task(source: "transcription:omi").isPendingSuggestion)
    XCTAssertTrue(task(source: "transcription:desktop").isPendingSuggestion)
  }

  func testUserCreatedTasksAreNeverSuggestions() {
    XCTAssertFalse(task(source: "manual").isPendingSuggestion)
    XCTAssertFalse(task(source: nil).isPendingSuggestion)
    XCTAssertFalse(task(source: "legacy").isPendingSuggestion)
  }

  func testRecurringSpawnsAreNotPendingSuggestions() {
    XCTAssertFalse(task(source: "recurring").isPendingSuggestion)
  }

  func testCompletedOrDeletedCapturesAreNotPendingSuggestions() {
    XCTAssertFalse(task(source: "screenshot", completed: true).isPendingSuggestion)
    XCTAssertFalse(task(source: "screenshot", deleted: true).isPendingSuggestion)
  }

  /// The dashboard/realtime lanes used to drop these rows as "unreviewed". They
  /// no longer do — capture is suggestion-only under INV-TASK-2, so a row that
  /// reached `action_items` is already the user's, and hiding it only made the
  /// assistant contradict the Tasks page. `DashboardTaskLaneReachTests` pins
  /// that reach. The classification survives for proactive nudges, which is the
  /// one consumer still asking "did a capture pipeline write this?".
  func testTheClassificationSurvivesForProactiveNudgesOnly() {
    XCTAssertTrue(task(source: "screenshot").isPendingSuggestion)
    XCTAssertFalse(task(source: "manual").isPendingSuggestion)
  }
}

/// Removing the sparkle Suggestions category put leftover AI captures back into
/// the due-date list, so keyboard nav and select-all must include them.
@MainActor
final class TasksPageAICaptureNavigationTests: XCTestCase {
  override func setUp() async throws {
    TasksStore.shared.resetSessionState()
  }

  override func tearDown() async throws {
    TasksStore.shared.resetSessionState()
  }

  func testAICapturedTasksAreIncludedInKeyboardNavAndSelectAll() {
    let accepted = TaskActionItem(
      id: "accepted", description: "Send the investor update email to Bob",
      completed: false, createdAt: Date(timeIntervalSince1970: 0), source: "manual")
    let capture = TaskActionItem(
      id: "capture", description: "AI capture from a screenshot",
      completed: false, createdAt: Date(timeIntervalSince1970: 0), source: "screenshot")
    TasksStore.shared.incompleteTasks = [accepted, capture]
    let vm = TasksViewModel()
    vm.selectedTags = [.todo]
    XCTAssertEqual(Set(vm.navigationOrder.map(\.id)), Set(["accepted", "capture"]))
    XCTAssertEqual(Set(vm.visibleTaskIDsForSelection), Set(["accepted", "capture"]))
    XCTAssertEqual(vm.getOrderedTasks(for: .noDeadline).map(\.id).sorted(), ["accepted", "capture"])
    XCTAssertTrue(TaskCategory.allCases.map(\.rawValue).allSatisfy { $0 != "Suggestions" })
  }
}
