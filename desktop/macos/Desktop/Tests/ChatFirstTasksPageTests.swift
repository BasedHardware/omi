import XCTest

@testable import Omi_Computer

final class ChatFirstTasksPageTests: XCTestCase {
  func testScheduleGroupingKeepsOverdueAndTodayWorkTogether() {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(secondsFromGMT: 0)!
    let now = Date(timeIntervalSince1970: 1_719_115_200) // 2024-06-15 00:00 UTC
    let overdue = task(id: "overdue", dueAt: now.addingTimeInterval(-1))
    let today = task(id: "today", dueAt: now.addingTimeInterval(12 * 60 * 60))
    let tomorrow = task(id: "tomorrow", dueAt: now.addingTimeInterval(24 * 60 * 60))
    let unscheduled = task(id: "unscheduled", dueAt: nil)

    XCTAssertEqual(ChatFirstTaskPagePolicy.scheduleGroup(for: overdue, now: now, calendar: calendar), .today)
    XCTAssertEqual(ChatFirstTaskPagePolicy.scheduleGroup(for: today, now: now, calendar: calendar), .today)
    XCTAssertEqual(ChatFirstTaskPagePolicy.scheduleGroup(for: tomorrow, now: now, calendar: calendar), .later)
    XCTAssertEqual(ChatFirstTaskPagePolicy.scheduleGroup(for: unscheduled, now: now, calendar: calendar), .later)
  }

  func testGoalGroupingAndBadgesAvoidRepeatedGoalAffordances() {
    let first = task(
      id: "first",
      goalID: "goal-a",
      conversationID: "capture-a",
      source: "transcription:omi"
    )
    let second = task(id: "second", goalID: "goal-a")
    let standalone = task(id: "standalone")
    let desktopCapture = task(
      id: "desktop-capture",
      conversationID: "desktop-conversation",
      source: "transcription:desktop"
    )

    let groups = ChatFirstTaskPagePolicy.groupedByGoal([first, second, standalone])
    XCTAssertEqual(groups.count, 2)
    XCTAssertEqual(Set(groups.first(where: { $0.goalID == "goal-a" })?.tasks.map(\.id) ?? []), Set(["first", "second"]))
    XCTAssertEqual(ChatFirstTaskPagePolicy.badges(for: first), .init(goalID: "goal-a", captureID: "capture-a"))
    XCTAssertEqual(ChatFirstTaskPagePolicy.badges(for: standalone), .init(goalID: nil, captureID: nil))
    XCTAssertEqual(
      ChatFirstTaskPagePolicy.badges(for: desktopCapture),
      .init(goalID: nil, captureID: nil),
      "only device-originated Omi tasks may deep-link into the strict capture archive"
    )
  }

  func testTaskFocusAcknowledgesOnlyTheVisiblePendingTask() {
    let requested = ChatFirstPendingFocus.task(id: "task-a")

    XCTAssertEqual(
      ChatFirstTaskPagePolicy.focusToAcknowledge(pendingFocus: requested, visibleTaskID: "task-a"),
      requested)
    XCTAssertNil(
      ChatFirstTaskPagePolicy.focusToAcknowledge(pendingFocus: requested, visibleTaskID: "task-b"))
    XCTAssertNil(
      ChatFirstTaskPagePolicy.focusToAcknowledge(
        pendingFocus: .goal(id: "goal-a"),
        visibleTaskID: "task-a"))
  }

  private func task(
    id: String,
    dueAt: Date? = nil,
    goalID: String? = nil,
    conversationID: String? = nil,
    source: String? = nil
  ) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: id,
      completed: false,
      createdAt: Date(timeIntervalSince1970: 0),
      dueAt: dueAt,
      conversationId: conversationID,
      source: source,
      goalId: goalID)
  }
}
