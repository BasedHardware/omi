import XCTest

@testable import Omi_Computer

/// `TaskActionItem.isPendingSuggestion` is the single triage rule that keeps
/// AI-captured tasks out of the due-date categories (TasksPage) and out of the
/// dashboard/nudge lanes (TasksStore) until the user accepts them. Regression
/// coverage for the rule that fixed "deleted tasks keep reappearing in Today".
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
    // Tasks predating the source field are user history, not AI spam.
    XCTAssertFalse(task(source: nil).isPendingSuggestion)
    XCTAssertFalse(task(source: "legacy").isPendingSuggestion)
  }

  func testRecurringSpawnsStayInDueDateCategories() {
    // TasksStore spawns recurrence instances with source "recurring"; they derive
    // from a task the user already accepted and must never triage as suggestions.
    XCTAssertFalse(task(source: "recurring").isPendingSuggestion)
  }

  func testAcceptingRewritesSourceSoTheTaskLeavesSuggestions() {
    // Accept = source rewritten to "manual" (TasksStore.acceptSuggestedTask);
    // the same task must then triage out of Suggestions.
    XCTAssertTrue(task(source: "screenshot").isPendingSuggestion)
    XCTAssertFalse(task(source: "manual").isPendingSuggestion)
  }

  func testCompletedOrDeletedCapturesAreNotResurfaced() {
    XCTAssertFalse(task(source: "screenshot", completed: true).isPendingSuggestion)
    XCTAssertFalse(task(source: "screenshot", deleted: true).isPendingSuggestion)
  }
}

/// Collapsed Suggestions render no rows, so keyboard navigation and select-all
/// must skip them too — otherwise arrow keys focus an invisible row and bulk
/// actions silently hit tasks the user cannot see.
@MainActor
final class TasksPageCollapsedSuggestionsNavigationTests: XCTestCase {
  private let expandedKey = "tasksSuggestionsSectionExpanded"
  private var savedExpanded: Any?

  override func setUp() async throws {
    savedExpanded = UserDefaults.standard.object(forKey: expandedKey)
    TasksStore.shared.resetSessionState()
  }

  override func tearDown() async throws {
    if let savedExpanded {
      UserDefaults.standard.set(savedExpanded, forKey: expandedKey)
    } else {
      UserDefaults.standard.removeObject(forKey: expandedKey)
    }
    TasksStore.shared.resetSessionState()
  }

  private func seedViewModel() -> TasksViewModel {
    let accepted = TaskActionItem(
      id: "accepted", description: "Send the investor update email to Bob",
      completed: false, createdAt: Date(timeIntervalSince1970: 0), source: "manual")
    let capture = TaskActionItem(
      id: "capture", description: "AI capture from a screenshot",
      completed: false, createdAt: Date(timeIntervalSince1970: 0), source: "screenshot")
    TasksStore.shared.incompleteTasks = [accepted, capture]
    let vm = TasksViewModel()
    vm.selectedTags = [.todo]
    return vm
  }

  func testCollapsedSuggestionsAreExcludedFromKeyboardNavAndSelectAll() {
    UserDefaults.standard.set(false, forKey: expandedKey)
    let vm = seedViewModel()
    XCTAssertEqual(vm.navigationOrder.map(\.id), ["accepted"])
    XCTAssertEqual(vm.visibleTaskIDsForSelection, ["accepted"])
  }

  func testExpandedSuggestionsAreReachableAgain() {
    UserDefaults.standard.set(true, forKey: expandedKey)
    let vm = seedViewModel()
    XCTAssertEqual(vm.navigationOrder.map(\.id), ["accepted", "capture"])
    XCTAssertEqual(vm.visibleTaskIDsForSelection, ["accepted", "capture"])
  }
}
