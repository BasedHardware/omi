import XCTest

@testable import Omi_Computer

/// The lanes behind the voice `get_tasks` tool, the About-user card, and the
/// assistant's task grounding.
///
/// They are the only read of the user's tasks that is not the Tasks page, and
/// they used to answer a different question than the page did. Two filters did
/// it: a seven-day recency window on both the overdue and the undated bucket,
/// and a source filter that dropped every AI-capture row. On a real account —
/// a month-old backlog, captured from conversations before capture became
/// suggestion-only — all three buckets computed to zero while the Tasks page
/// showed thirty tasks, and the assistant answered "you don't have any tasks
/// overdue or due today" to someone looking at their list.
@MainActor
final class DashboardTaskLaneReachTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?
  private var previousOwnerID: String?
  private var previousAuth: RewindStorageTestIsolation.AuthSnapshot?

  override func setUp() async throws {
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "dashboard-lane-reach")
    self.fixture = fixture
    previousAuth = RewindStorageTestIsolation.captureAuthSnapshot()
    previousOwnerID = RuntimeOwnerIdentity.currentOwnerId()
    await transitionOwner(to: fixture.testUserId)
    RewindStorageTestIsolation.signInForTests(userId: fixture.testUserId)
    TasksStore.shared.resetSessionState()
  }

  override func tearDown() async throws {
    TasksStore.shared.resetSessionState()
    if let previousAuth { RewindStorageTestIsolation.restoreAuthSnapshot(previousAuth) }
    await transitionOwner(to: previousOwnerID)
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
  }

  /// Every row the Tasks page would show under "Today" and "No Deadline" has to
  /// reach the lanes the assistant reads, whatever its age and whoever captured
  /// it. The four rows below are the four ways the old filters lost one.
  func testTheAssistantsLanesReachEveryTaskTheTasksPageShows() async throws {
    let now = Date()
    let calendar = Calendar.current
    let startOfToday = calendar.startOfDay(for: now)

    try await ActionItemStorage.shared.syncTaskActionItems(
      [
        item(
          id: "overdue-by-a-month",
          description: "Visit parents",
          dueAt: calendar.date(byAdding: .day, value: -34, to: startOfToday),
          createdAt: now.addingTimeInterval(-35 * 86_400),
          source: "manual"),
        item(
          id: "overdue-and-captured",
          description: "Apply to the matcha and mahjong event",
          dueAt: calendar.date(byAdding: .day, value: -34, to: startOfToday),
          createdAt: now.addingTimeInterval(-35 * 86_400),
          source: "conversation"),
        item(
          id: "due-today",
          description: "Finish the demo",
          dueAt: calendar.date(byAdding: .hour, value: 9, to: startOfToday),
          createdAt: now,
          source: "manual"),
        item(
          id: "undated-and-old",
          description: "Keep fishing for a stronger hook",
          dueAt: nil,
          createdAt: now.addingTimeInterval(-30 * 86_400),
          source: "legacy"),
      ],
      authorization: .unrestricted)

    await TasksStore.shared.loadDashboardTasks()

    let overdue = Set(TasksStore.shared.overdueTasks.map(\.id))
    XCTAssertTrue(
      overdue.contains("overdue-by-a-month"),
      "a task overdue by more than a week is still on the user's list — the page has no lower bound")
    XCTAssertTrue(
      overdue.contains("overdue-and-captured"),
      "capture is suggestion-only now (INV-TASK-2), so a row in action_items is already the user's")
    XCTAssertEqual(
      TasksStore.shared.todaysTasks.map(\.id), ["due-today"],
      "a task due today belongs to today's bucket and nowhere else")
    XCTAssertEqual(
      TasksStore.shared.tasksWithoutDueDate.map(\.id), ["undated-and-old"],
      "an undated task does not age out of the list it has always been sitting in")
  }

  /// The spoken answer is assembled from the three buckets, so an empty answer
  /// has to mean an empty list.
  func testAnEmptyAnswerMeansAnEmptyList() async throws {
    await TasksStore.shared.loadDashboardTasks()

    XCTAssertTrue(TasksStore.shared.overdueTasks.isEmpty)
    XCTAssertTrue(TasksStore.shared.todaysTasks.isEmpty)
    XCTAssertTrue(TasksStore.shared.tasksWithoutDueDate.isEmpty)
  }

  private func item(
    id: String,
    description: String,
    dueAt: Date?,
    createdAt: Date,
    source: String
  ) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: description,
      completed: false,
      createdAt: createdAt,
      dueAt: dueAt,
      source: source)
  }

  private func transitionOwner(to ownerID: String?) async {
    do {
      _ = try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
        plannedNextOwner: { _, _ in ownerID },
        quiesceVoice: { _, _ in },
        retargetLocalStorage: { _, _ in },
        ownerDidChange: {},
        { defaults in
          defaults.removeObject(forKey: .automationOwnerOverride)
          if let ownerID {
            defaults.set(ownerID, forKey: .authUserId)
          } else {
            defaults.removeObject(forKey: .authUserId)
          }
        })
    } catch {
      XCTFail("owner transition failed: \(error)")
    }
  }
}
