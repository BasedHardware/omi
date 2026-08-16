import XCTest

@testable import Omi_Computer

/// The composer's "Today" button assigns a due date that lands the task in the
/// Today section — end of the current day, so it never rolls into Tomorrow.
@MainActor
final class InlineTaskTodayButtonTests: XCTestCase {

  override func tearDown() async throws {
    TasksStore.shared.resetSessionState()
  }

  func testTodayDueAtIsEndOfCurrentDay() throws {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "America/New_York"))
    let now = Date(timeIntervalSince1970: 1_755_100_000)  // fixed instant, not wall clock

    let dueAt = TasksViewModel.todayDueAt(now: now, calendar: calendar)

    let due = try XCTUnwrap(dueAt)
    XCTAssertTrue(calendar.isDate(due, inSameDayAs: now), "due date must stay on the same day")
    let components = calendar.dateComponents([.hour, .minute], from: due)
    XCTAssertEqual(components.hour, 23)
    XCTAssertEqual(components.minute, 59)
  }

  func testTaskWithTodayDueAtAppearsInTodayCategory() {
    let store = TasksStore.shared
    store.resetSessionState()
    let todayTask = TaskActionItem(
      id: "today-button-task",
      description: "created via Today button",
      completed: false,
      createdAt: Date(),
      dueAt: TasksViewModel.todayDueAt()
    )
    let undatedTask = TaskActionItem(
      id: "undated-task",
      description: "no due date",
      completed: false,
      createdAt: Date()
    )
    store.incompleteTasks = [todayTask, undatedTask]

    let vm = TasksViewModel()
    vm.selectedTags = [.todo]

    XCTAssertEqual(vm.getOrderedTasks(for: .today).map(\.id), ["today-button-task"])
    XCTAssertEqual(vm.getOrderedTasks(for: .noDeadline).map(\.id), ["undated-task"])
  }
}
