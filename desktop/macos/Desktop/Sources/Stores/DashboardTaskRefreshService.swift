import Foundation

@MainActor
enum DashboardTaskRefreshService {
    private static var isRefreshing = false

    static func refresh(store: TasksStore) async {
        guard DashboardTaskRefreshPolicy.shouldSyncFromServer else {
            await store.loadDashboardTasks()
            return
        }
        guard AuthService.shared.isSignedIn else {
            await store.loadDashboardTasks()
            return
        }
        guard !AuthBackoffTracker.shared.shouldSkipRequest() else {
            await store.loadDashboardTasks()
            return
        }
        guard !isRefreshing else { return }

        isRefreshing = true
        defer { isRefreshing = false }

        await store.loadDashboardTasks()

        let dashboardIds = Set((store.overdueTasks + store.todaysTasks + store.tasksWithoutDueDate)
            .map(\.id)
            .filter { !$0.hasPrefix("local_") && !$0.hasPrefix("staged_") })

        do {
            let calendar = Calendar.current
            let windowItems = try await fetchDashboardWindowItems(calendar: calendar)
            let serverTruth = await fetchExactServerTruth(forDashboardIds: dashboardIds)
            let plan = DashboardTaskReconciliationPlanner.plan(
                localDashboardIds: dashboardIds,
                dashboardWindowServerItems: windowItems,
                exactServerItemsById: serverTruth.itemsById,
                missingServerIds: serverTruth.missingIds,
                calendar: calendar
            )

            if !plan.itemsToSync.isEmpty {
                try await ActionItemStorage.shared.syncTaskActionItems(plan.itemsToSync)
            }
            for backendId in plan.backendIdsToHardDelete {
                try await ActionItemStorage.shared.hardDeleteByBackendId(backendId)
            }
            log(
                "DashboardTaskRefreshService: Dashboard freshness reconciled sync=\(plan.itemsToSync.count), hardDeleted=\(plan.backendIdsToHardDelete.count), visible=\(plan.dashboardVisibleServerIds.count), completed=\(plan.completedServerIds.count), movedOut=\(plan.movedOutServerIds.count) without loading Tasks page list"
            )
            AuthBackoffTracker.shared.reportSuccess()
        } catch {
            if case APIError.unauthorized = error {
                AuthBackoffTracker.shared.reportAuthFailure()
            }
            logError("DashboardTaskRefreshService: Dashboard freshness sync failed", error: error)
        }

        await store.loadDashboardTasks()
    }

    private static func fetchDashboardWindowItems(calendar: Calendar) async throws -> [TaskActionItem] {
        let startOfToday = calendar.startOfDay(for: Date())
        let endOfToday = calendar.date(byAdding: .day, value: 1, to: startOfToday)!
        let sevenDaysAgo = calendar.date(byAdding: .day, value: -7, to: Date()) ?? Date()
        let limit = DashboardTaskRefreshPolicy.serverFetchLimit

        async let dueWindowResponse = APIClient.shared.getActionItems(
            limit: limit,
            offset: 0,
            completed: false,
            dueStartDate: sevenDaysAgo,
            dueEndDate: endOfToday
        )
        async let recentResponse = APIClient.shared.getActionItems(
            limit: limit,
            offset: 0,
            completed: false,
            startDate: sevenDaysAgo
        )

        let (dueWindow, recent) = try await (dueWindowResponse, recentResponse)
        return [dueWindow, recent].flatMap(\.items)
    }

    private static func fetchExactServerTruth(
        forDashboardIds ids: Set<String>
    ) async -> (itemsById: [String: TaskActionItem], missingIds: Set<String>) {
        guard !ids.isEmpty else { return ([:], []) }

        let sortedIds = ids.sorted()
        let results = await DashboardExactTaskFetchLimiter.fetch(ids: sortedIds) { id in
            do {
                let item = try await APIClient.shared.getActionItem(id: id)
                return (id, Result<TaskActionItem?, Error>.success(item))
            } catch APIError.httpError(let statusCode, _) where statusCode == 404 {
                return (id, Result<TaskActionItem?, Error>.success(nil))
            } catch {
                return (id, Result<TaskActionItem?, Error>.failure(error))
            }
        }

        var itemsById: [String: TaskActionItem] = [:]
        var missingIds = Set<String>()
        var failedCount = 0

        for (id, result) in results {
            switch result {
            case .success(.some(let item)):
                itemsById[id] = item
            case .success(.none):
                missingIds.insert(id)
            case .failure(let error):
                failedCount += 1
                logError("DashboardTaskRefreshService: Exact task refresh failed for \(id)", error: error)
                if case APIError.unauthorized = error {
                    AuthBackoffTracker.shared.reportAuthFailure()
                }
            }
        }

        if failedCount > 0 {
            log("DashboardTaskRefreshService: Exact task refresh skipped \(failedCount) stale classifications")
        }

        return (itemsById, missingIds)
    }
}
