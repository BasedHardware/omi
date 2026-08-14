import XCTest

@testable import Omi_Computer

/// `TaskActionItem.isPendingSuggestion` still names AI-captured action items so
/// proactive nudges can skip leftover extractor rows. Those rows are ordinary
/// due-date tasks on the Tasks page; Candidate review is a separate surface.
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

  func testDashboardLanesExcludeUnreviewedAICaptures() {
    XCTAssertFalse(DashboardTaskLanePolicy.admits(task(source: "screenshot")))
    XCTAssertFalse(DashboardTaskLanePolicy.admits(task(source: "transcription:omi")))
    XCTAssertTrue(DashboardTaskLanePolicy.admits(task(source: "manual")))
    XCTAssertTrue(DashboardTaskLanePolicy.admits(task(source: "recurring")))
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
