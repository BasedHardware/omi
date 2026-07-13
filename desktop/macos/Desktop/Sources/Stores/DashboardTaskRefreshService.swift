import Foundation

@MainActor
enum DashboardTaskRefreshService {
    private struct InFlightRefresh {
        let id: UUID
        let authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
        let task: Task<Void, Never>
    }

    private static var inFlightRefreshes: [String: InFlightRefresh] = [:]

    static func refresh(
        store: TasksStore,
        expectedOwnerID: String,
        authorizationSnapshot suppliedAuthorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
    ) async {
        let authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
        if let suppliedAuthorizationSnapshot {
            guard suppliedAuthorizationSnapshot.ownerID == expectedOwnerID,
                  isCurrent(suppliedAuthorizationSnapshot) else { return }
            authorizationSnapshot = suppliedAuthorizationSnapshot
        } else {
            guard let captured = RuntimeOwnerIdentity.captureAuthorizationSnapshot(
                expectedOwnerID: expectedOwnerID
            ) else { return }
            authorizationSnapshot = captured
        }
        if let inFlight = inFlightRefreshes[expectedOwnerID],
           isCurrent(inFlight.authorizationSnapshot) {
            await inFlight.task.value
            guard isCurrent(authorizationSnapshot) else { return }
            await store.loadDashboardTasks(
                expectedOwnerID: expectedOwnerID,
                authorizationSnapshot: authorizationSnapshot
            )
            return
        }

        let id = UUID()
        let task = Task { @MainActor in
            await refreshNow(
                store: store,
                authorizationSnapshot: authorizationSnapshot
            )
        }
        inFlightRefreshes[expectedOwnerID] = InFlightRefresh(
            id: id,
            authorizationSnapshot: authorizationSnapshot,
            task: task
        )
        await task.value
        if inFlightRefreshes[expectedOwnerID]?.id == id {
            inFlightRefreshes[expectedOwnerID] = nil
        }
    }

    private static func refreshNow(
        store: TasksStore,
        authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
    ) async {
        guard isCurrent(authorizationSnapshot) else { return }
        let expectedOwnerID = authorizationSnapshot.ownerID
        guard DashboardTaskRefreshPolicy.shouldSyncFromServer else {
            await store.loadDashboardTasks(
                expectedOwnerID: expectedOwnerID,
                authorizationSnapshot: authorizationSnapshot
            )
            return
        }
        guard AuthService.shared.isSignedIn else {
            await store.loadDashboardTasks(
                expectedOwnerID: expectedOwnerID,
                authorizationSnapshot: authorizationSnapshot
            )
            return
        }

        await store.loadDashboardTasks(
            expectedOwnerID: expectedOwnerID,
            authorizationSnapshot: authorizationSnapshot
        )
        guard isCurrent(authorizationSnapshot) else { return }

        let dashboardIds = Set((store.overdueTasks + store.todaysTasks + store.tasksWithoutDueDate)
            .map(\.id)
            .filter { !$0.hasPrefix("local_") && !$0.hasPrefix("staged_") })

        do {
            let calendar = Calendar.current
            let now = Date()
            let windowItems = try await fetchDashboardWindowItems(
                now: now,
                calendar: calendar,
                authorizationSnapshot: authorizationSnapshot
            )
            guard isCurrent(authorizationSnapshot) else { return }
            let serverTruth = await fetchExactServerTruth(
                forDashboardIds: dashboardIds,
                authorizationSnapshot: authorizationSnapshot
            )
            guard isCurrent(authorizationSnapshot) else { return }
            let plan = DashboardTaskReconciliationPlanner.plan(
                localDashboardIds: dashboardIds,
                dashboardWindowServerItems: windowItems,
                exactServerItemsById: serverTruth.itemsById,
                missingServerIds: serverTruth.missingIds,
                now: now,
                calendar: calendar
            )

            let authorization = localMutationAuthorization(snapshot: authorizationSnapshot)
            if !plan.itemsToSync.isEmpty {
                try await ActionItemStorage.shared.syncTaskActionItems(
                    plan.itemsToSync,
                    authorization: authorization
                )
                guard isCurrent(authorizationSnapshot) else { return }
                let visibilityReconciled = try await ActionItemStorage.shared.reconcileDashboardVisibilityFields(
                    plan.itemsToSync,
                    authorization: authorization
                )
                guard isCurrent(authorizationSnapshot) else { return }
                if visibilityReconciled > 0 {
                    log("DashboardTaskRefreshService: Reconciled \(visibilityReconciled) dashboard visibility field updates")
                }
            }
            for backendId in plan.backendIdsToHardDelete {
                guard isCurrent(authorizationSnapshot) else { return }
                try await ActionItemStorage.shared.hardDeleteByBackendId(
                    backendId,
                    authorization: authorization
                )
            }
            guard isCurrent(authorizationSnapshot) else { return }
            log(
                "DashboardTaskRefreshService: Dashboard freshness reconciled sync=\(plan.itemsToSync.count), hardDeleted=\(plan.backendIdsToHardDelete.count), visible=\(plan.dashboardVisibleServerIds.count), completed=\(plan.completedServerIds.count), movedOut=\(plan.movedOutServerIds.count) without loading Tasks page list"
            )
        } catch {
            if isCurrent(authorizationSnapshot) {
                logError("DashboardTaskRefreshService: Dashboard freshness sync failed", error: error)
            }
        }

        guard isCurrent(authorizationSnapshot) else { return }
        await store.loadDashboardTasks(
            expectedOwnerID: expectedOwnerID,
            authorizationSnapshot: authorizationSnapshot
        )
    }

    private static func fetchDashboardWindowItems(
        now: Date,
        calendar: Calendar,
        authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
    ) async throws -> [TaskActionItem] {
        let expectedOwnerID = authorizationSnapshot.ownerID
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
                dueEndDate: endOfToday,
                expectedOwnerId: expectedOwnerID,
                authorizationSnapshot: authorizationSnapshot
            )
        }
        async let recentItems = fetchDashboardWindowPages(limit: limit) { offset in
            try await APIClient.shared.getActionItems(
                limit: limit,
                offset: offset,
                completed: false,
                startDate: sevenDaysAgo,
                expectedOwnerId: expectedOwnerID,
                authorizationSnapshot: authorizationSnapshot
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
        forDashboardIds ids: Set<String>,
        authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
    ) async -> (itemsById: [String: TaskActionItem], missingIds: Set<String>, hadAuthFailure: Bool) {
        guard !ids.isEmpty else { return ([:], [], false) }
        let expectedOwnerID = authorizationSnapshot.ownerID

        let sortedIds = ids.sorted()
        let results = await DashboardExactTaskFetchLimiter.fetch(ids: sortedIds) { id in
            do {
                let item = try await APIClient.shared.getActionItem(
                    id: id,
                    expectedOwnerId: expectedOwnerID,
                    authorizationSnapshot: authorizationSnapshot
                )
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
                }
            }
        }

        if failedCount > 0 {
            log("DashboardTaskRefreshService: Exact task refresh skipped \(failedCount) stale classifications")
        }

        return (itemsById, missingIds, hadAuthFailure)
    }

    private nonisolated static func isCurrent(
        _ snapshot: RuntimeOwnerAuthorizationSnapshot
    ) -> Bool {
        RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot)
    }

    private nonisolated static func localMutationAuthorization(
        snapshot: RuntimeOwnerAuthorizationSnapshot
    ) -> LocalMutationAuthorization {
        LocalMutationAuthorization {
            isCurrent(snapshot)
        }
    }
}
