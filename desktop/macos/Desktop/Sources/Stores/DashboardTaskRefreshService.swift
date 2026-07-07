import Foundation

@MainActor
enum DashboardTaskRefreshService {
    private static var inFlightRefreshTask: Task<Void, Never>?

    static func refresh(store: TasksStore) async {
        if let inFlightRefreshTask {
            await inFlightRefreshTask.value
            await store.loadDashboardTasks()
            return
        }

        let task = Task {
            await refreshNow(store: store)
        }
        inFlightRefreshTask = task
        await task.value
        inFlightRefreshTask = nil
    }

    private static func refreshNow(store: TasksStore) async {
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

        await store.loadDashboardTasks()

        let dashboardIds = Set((store.overdueTasks + store.todaysTasks + store.tasksWithoutDueDate)
            .map(\.id)
            .filter { !$0.hasPrefix("local_") && !$0.hasPrefix("staged_") })

        do {
            let calendar = Calendar.current
            let now = Date()
            let windowItems = try await fetchDashboardWindowItems(now: now, calendar: calendar)
            let serverTruth = await fetchExactServerTruth(forDashboardIds: dashboardIds)
            let plan = DashboardTaskReconciliationPlanner.plan(
                localDashboardIds: dashboardIds,
                dashboardWindowServerItems: windowItems,
                exactServerItemsById: serverTruth.itemsById,
                missingServerIds: serverTruth.missingIds,
                now: now,
                calendar: calendar
            )

            if !plan.itemsToSync.isEmpty {
                try await ActionItemStorage.shared.syncTaskActionItems(plan.itemsToSync)
                let visibilityReconciled = try await ActionItemStorage.shared.reconcileDashboardVisibilityFields(plan.itemsToSync)
                if visibilityReconciled > 0 {
                    log("DashboardTaskRefreshService: Reconciled \(visibilityReconciled) dashboard visibility field updates")
                }
            }
            for backendId in plan.backendIdsToHardDelete {
                try await ActionItemStorage.shared.hardDeleteByBackendId(backendId)
            }
            log(
                "DashboardTaskRefreshService: Dashboard freshness reconciled sync=\(plan.itemsToSync.count), hardDeleted=\(plan.backendIdsToHardDelete.count), visible=\(plan.dashboardVisibleServerIds.count), completed=\(plan.completedServerIds.count), movedOut=\(plan.movedOutServerIds.count) without loading Tasks page list"
            )
            if !serverTruth.hadAuthFailure {
                AuthBackoffTracker.shared.reportSuccess()
            }
        } catch {
            if case APIError.unauthorized = error {
                AuthBackoffTracker.shared.reportAuthFailure()
            }
            logError("DashboardTaskRefreshService: Dashboard freshness sync failed", error: error)
        }

        await store.loadDashboardTasks()
    }

    private static func fetchDashboardWindowItems(now: Date, calendar: Calendar) async throws -> [TaskActionItem] {
        let startOfToday = calendar.startOfDay(for: now)
        guard let endOfToday = calendar.date(byAdding: .day, value: 1, to: startOfToday) else {
            return []
        }
        let sevenDaysAgo = calendar.date(byAdding: .day, value: -7, to: now) ?? now
        let limit = DashboardTaskRefreshPolicy.serverFetchLimit

        async let dueWindowItems = fetchDashboardWindowPages(limit: limit) { offset in
            try await APIClient.shared.getActionItems(
                limit: limit,
                offset: offset,
                completed: false,
                dueStartDate: sevenDaysAgo,
                dueEndDate: endOfToday
            )
        }
        async let recentItems = fetchDashboardWindowPages(limit: limit) { offset in
            try await APIClient.shared.getActionItems(
                limit: limit,
                offset: offset,
                completed: false,
                startDate: sevenDaysAgo
            )
        }

        let (dueWindow, recent) = try await (dueWindowItems, recentItems)
        return dueWindow + recent
    }

    private static func fetchDashboardWindowPages(
        limit: Int,
        fetch: (Int) async throws -> ActionItemsListResponse
    ) async throws -> [TaskActionItem] {
        var items: [TaskActionItem] = []
        for page in 0..<DashboardTaskRefreshPolicy.maxServerFetchPages {
            let response = try await fetch(page * limit)
            items.append(contentsOf: response.items)
            if !response.hasMore || response.items.count < limit { break }
        }
        return items
    }

    private static func fetchExactServerTruth(
        forDashboardIds ids: Set<String>
    ) async -> (itemsById: [String: TaskActionItem], missingIds: Set<String>, hadAuthFailure: Bool) {
        guard !ids.isEmpty else { return ([:], [], false) }

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
        var hadAuthFailure = false

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
                    hadAuthFailure = true
                    AuthBackoffTracker.shared.reportAuthFailure()
                }
            }
        }

        if failedCount > 0 {
            log("DashboardTaskRefreshService: Exact task refresh skipped \(failedCount) stale classifications")
        }

        return (itemsById, missingIds, hadAuthFailure)
    }
}
