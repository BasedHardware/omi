import Foundation

enum DashboardTaskRefreshPolicy {
  static let shouldSyncFromServer = true
  static let shouldMarkIncompleteTasksLoaded = false
  static let shouldAssignTasksPageList = false
  static let serverFetchLimit = 100
  /// Dashboard freshness reads are page-limited to avoid a full Tasks-page load,
  /// but must not silently rely on only offset=0. Fetch a bounded number of
  /// pages for each dashboard-scoped bucket, then let exact-ID refresh handle
  /// the currently visible rows that moved out of those buckets.
  static let maxServerFetchPages = 3
}

enum DashboardExactTaskFetchPolicy {
  static let maxConcurrentRequests = 6

  static func chunks(ids: [String]) -> [[String]] {
    guard !ids.isEmpty else { return [] }

    return stride(from: 0, to: ids.count, by: maxConcurrentRequests).map { start in
      let end = min(start + maxConcurrentRequests, ids.count)
      return Array(ids[start..<end])
    }
  }
}

enum DashboardExactTaskFetchLimiter {
  static func fetch<Result: Sendable>(
    ids: [String],
    operation: @escaping @Sendable (String) async -> Result
  ) async -> [Result] {
    var results: [Result] = []

    for chunk in DashboardExactTaskFetchPolicy.chunks(ids: ids) {
      let chunkResults = await withTaskGroup(of: Result.self, returning: [Result].self) { group in
        for id in chunk {
          group.addTask {
            await operation(id)
          }
        }

        var chunkResults: [Result] = []
        for await result in group {
          chunkResults.append(result)
        }
        return chunkResults
      }
      results.append(contentsOf: chunkResults)
    }

    return results
  }
}

struct DashboardTaskReconciliationPlan {
  let itemsToSync: [TaskActionItem]
  let backendIdsToHardDelete: Set<String>
  let dashboardVisibleServerIds: Set<String>
  let completedServerIds: Set<String>
  let movedOutServerIds: Set<String>

  var shouldMarkIncompleteTasksLoaded: Bool {
    DashboardTaskRefreshPolicy.shouldMarkIncompleteTasksLoaded
  }

  var shouldAssignTasksPageList: Bool {
    DashboardTaskRefreshPolicy.shouldAssignTasksPageList
  }
}

enum DashboardTaskReconciliationPlanner {
  static func plan(
    localDashboardIds: Set<String>,
    dashboardWindowServerItems: [TaskActionItem],
    exactServerItemsById: [String: TaskActionItem],
    missingServerIds: Set<String>,
    now: Date = Date(),
    calendar: Calendar = .current
  ) -> DashboardTaskReconciliationPlan {
    var itemsById = dashboardWindowServerItems.reduce(into: [String: TaskActionItem]()) { result, item in
      result[item.id] = item
    }
    exactServerItemsById.values.forEach { item in
      itemsById[item.id] = item
    }

    var dashboardVisibleServerIds = Set<String>()
    var completedServerIds = Set<String>()
    var movedOutServerIds = Set<String>()

    for item in exactServerItemsById.values {
      if item.completed || item.deleted == true {
        completedServerIds.insert(item.id)
      } else if isDashboardVisible(item, now: now, calendar: calendar) {
        dashboardVisibleServerIds.insert(item.id)
      } else {
        movedOutServerIds.insert(item.id)
      }
    }

    for item in dashboardWindowServerItems where isDashboardVisible(item, now: now, calendar: calendar) {
      dashboardVisibleServerIds.insert(item.id)
    }

    return DashboardTaskReconciliationPlan(
      itemsToSync: Array(itemsById.values),
      backendIdsToHardDelete: missingServerIds.intersection(localDashboardIds),
      dashboardVisibleServerIds: dashboardVisibleServerIds,
      completedServerIds: completedServerIds,
      movedOutServerIds: movedOutServerIds
    )
  }

  static func isDashboardVisible(
    _ item: TaskActionItem,
    now: Date = Date(),
    calendar: Calendar = .current
  ) -> Bool {
    guard !item.completed, item.deleted != true else { return false }

    let startOfToday = calendar.startOfDay(for: now)
    guard
      let endOfToday = calendar.date(byAdding: .day, value: 1, to: startOfToday),
      let sevenDaysAgo = calendar.date(byAdding: .day, value: -7, to: now)
    else { return false }

    if let dueAt = item.dueAt {
      return dueAt >= sevenDaysAgo && dueAt < endOfToday
    }

    return item.createdAt >= sevenDaysAgo
  }
}
