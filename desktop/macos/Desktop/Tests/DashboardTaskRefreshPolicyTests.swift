import XCTest

@testable import Omi_Computer

final class DashboardTaskRefreshPolicyTests: XCTestCase {
  func testDashboardTaskRefreshDoesNotPopulateTasksPageList() {
    XCTAssertTrue(DashboardTaskRefreshPolicy.shouldSyncFromServer)
    XCTAssertFalse(DashboardTaskRefreshPolicy.shouldMarkIncompleteTasksLoaded)
    XCTAssertFalse(DashboardTaskRefreshPolicy.shouldAssignTasksPageList)
    XCTAssertGreaterThan(DashboardTaskRefreshPolicy.serverFetchLimit, 0)
    XCTAssertGreaterThan(
      DashboardTaskRefreshPolicy.maxServerFetchPages,
      1,
      "Dashboard freshness must not silently rely on only the first server page"
    )
  }

  func testDashboardRefreshServiceSharesInflightRefreshAndReloadsLocalStateForWaiters() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Stores/DashboardTaskRefreshService.swift")
    let source = try String(contentsOf: sourceURL)

    XCTAssertTrue(
      source.contains("private static var inFlightRefreshes: [String: InFlightRefresh]"),
      "Dashboard refresh must track shared in-flight work per authenticated owner"
    )
    XCTAssertTrue(
      source.contains("if let inFlight = inFlightRefreshes[expectedOwnerID]")
        && source.contains("isCurrent(inFlight.authorizationSnapshot)")
        && source.contains("await inFlight.task.value"),
      "Concurrent callers may join only the current owner's exact authorized refresh"
    )
    XCTAssertTrue(
      source.contains("await store.loadDashboardTasks(")
        && source.contains("expectedOwnerID: expectedOwnerID")
        && source.contains("authorizationSnapshot: authorizationSnapshot"),
      "A joined caller must reload dashboard state under its admitted owner snapshot"
    )
  }

  func testDashboardExactTaskFetchLimiterCapsConcurrentOperations() async {
    let ids = (0..<125).map { "task-\($0)" }
    let probe = ExactFetchConcurrencyProbe()

    let fetchedIds = await DashboardExactTaskFetchLimiter.fetch(ids: ids) { id in
      await probe.start(id: id)
      try? await Task.sleep(nanoseconds: 1_000_000)
      await probe.finish()
      return id
    }

    XCTAssertEqual(Set(fetchedIds), Set(ids))
    XCTAssertEqual(fetchedIds.count, ids.count)
    let maxActive = await probe.snapshotMaxActive()
    XCTAssertLessThanOrEqual(
      maxActive,
      DashboardExactTaskFetchPolicy.maxConcurrentRequests
    )
    XCTAssertGreaterThan(ids.count, DashboardExactTaskFetchPolicy.maxConcurrentRequests)
  }

  func testDashboardTaskReconciliationPlansStaleRemovalWithoutTasksPageHydration() {
    let calendar = Calendar(identifier: .gregorian)
    let now = Date(timeIntervalSince1970: 1_750_000_000)
    let today = calendar.startOfDay(for: now).addingTimeInterval(10 * 60 * 60)
    let tomorrow = calendar.date(byAdding: .day, value: 1, to: calendar.startOfDay(for: now))!
    let oldNoDeadline = calendar.date(byAdding: .day, value: -10, to: now)!

    let stillVisible = task(id: "still-visible", createdAt: now, dueAt: today)
    let completed = task(id: "completed-remotely", completed: true, createdAt: now, dueAt: today)
    let movedOut = task(id: "moved-out", createdAt: oldNoDeadline, dueAt: tomorrow)
    let newDashboardTask = task(id: "new-dashboard-task", createdAt: now, dueAt: nil)

    let plan = DashboardTaskReconciliationPlanner.plan(
      localDashboardIds: [
        stillVisible.id,
        completed.id,
        "deleted-remotely",
        movedOut.id,
      ],
      dashboardWindowServerItems: [stillVisible, newDashboardTask],
      exactServerItemsById: [
        stillVisible.id: stillVisible,
        completed.id: completed,
        movedOut.id: movedOut,
      ],
      missingServerIds: ["deleted-remotely"],
      now: now,
      calendar: calendar
    )

    XCTAssertEqual(
      Set(plan.itemsToSync.map(\.id)),
      [
        stillVisible.id,
        completed.id,
        movedOut.id,
        newDashboardTask.id,
      ])
    XCTAssertEqual(plan.backendIdsToHardDelete, ["deleted-remotely"])
    XCTAssertEqual(plan.dashboardVisibleServerIds, [stillVisible.id, newDashboardTask.id])
    XCTAssertTrue(plan.terminalServerIds.contains(completed.id))
    XCTAssertTrue(plan.movedOutServerIds.contains(movedOut.id))
    XCTAssertFalse(plan.shouldMarkIncompleteTasksLoaded)
    XCTAssertFalse(plan.shouldAssignTasksPageList)
  }

  func testDashboardDoesNotReintroduceTerminalDetailTask() {
    let calendar = Calendar(identifier: .gregorian)
    let now = Date(timeIntervalSince1970: 1_750_000_000)
    let today = calendar.startOfDay(for: now).addingTimeInterval(10 * 60 * 60)

    for taskStatus in ["cancelled", "superseded"] {
      let terminalTask = task(
        id: "\(taskStatus)-remotely",
        createdAt: now,
        dueAt: today,
        taskStatus: taskStatus
      )

      let plan = DashboardTaskReconciliationPlanner.plan(
        localDashboardIds: [terminalTask.id],
        dashboardWindowServerItems: [],
        exactServerItemsById: [terminalTask.id: terminalTask],
        missingServerIds: [],
        now: now,
        calendar: calendar
      )

      XCTAssertTrue(plan.terminalServerIds.contains(terminalTask.id))
      XCTAssertFalse(plan.dashboardVisibleServerIds.contains(terminalTask.id))
    }
  }

  private func task(
    id: String,
    completed: Bool = false,
    createdAt: Date,
    dueAt: Date?,
    taskStatus: String? = nil
  ) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: id,
      completed: completed,
      createdAt: createdAt,
      dueAt: dueAt,
      taskStatus: taskStatus
    )
  }
}

private actor ExactFetchConcurrencyProbe {
  private var activeCount = 0
  private(set) var maxActive = 0
  private var seenIds = Set<String>()

  func start(id: String) {
    activeCount += 1
    maxActive = max(maxActive, activeCount)
    seenIds.insert(id)
  }

  func finish() {
    activeCount -= 1
  }

  func snapshotMaxActive() -> Int {
    maxActive
  }
}
