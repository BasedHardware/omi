import SwiftUI
import Combine

/// Shared store for all tasks - single source of truth
/// Both Dashboard and Tasks tab observe this store
///
/// Tasks are loaded separately for incomplete vs completed to minimize memory usage.
/// By default, only recent (7 days) incomplete tasks are loaded.
@MainActor
class TasksStore: ObservableObject {
    static let shared = TasksStore()

    // MARK: - Published State

    /// Incomplete tasks (To Do) - loaded with 7-day filter by default
    @Published var incompleteTasks: [TaskActionItem] = []
    /// Completed tasks (Done) - loaded on demand when viewing Done tab
    @Published var completedTasks: [TaskActionItem] = []
    /// Soft-deleted tasks (Removed by AI) - loaded on demand when viewing filter
    @Published var deletedTasks: [TaskActionItem] = []

    @Published var isLoadingIncomplete = false
    @Published var isLoadingCompleted = false
    @Published var isLoadingDeleted = false
    @Published var isLoadingMore = false
    @Published var hasMoreIncompleteTasks = true
    @Published var hasMoreCompletedTasks = true
    @Published var hasMoreDeletedTasks = true
    @Published var error: String?

    // Legacy compatibility - combines both lists
    var tasks: [TaskActionItem] {
        incompleteTasks + completedTasks
    }

    var isLoading: Bool {
        isLoadingIncomplete || isLoadingCompleted || isLoadingDeleted
    }

    // MARK: - Private State

    private var incompleteOffset = 0
    private var completedOffset = 0
    private var deletedOffset = 0
    private let pageSize = 100  // Reduced from 1000 for better performance
    private var hasLoadedIncomplete = false
    private var hasLoadedCompleted = false
    private var hasLoadedDeleted = false
    /// Whether we're currently showing all tasks (no date filter) or just recent
    private var cancellables = Set<AnyCancellable>()
    private var isRetryingUnsynced = false

    /// Timestamp of last full reconciliation (paginated API check for absent tasks)
    private var lastReconciliationDate: Date?

    /// Whether the tasks page (or dashboard) is currently visible.
    /// Auto-refresh only runs when active to avoid unnecessary API calls.
    var isActive = false {
        didSet {
            if isActive && !oldValue && hasLoadedIncomplete {
                // Refresh immediately when becoming active
                Task {
                    await refreshTasksIfNeeded()
                    await reconcileWithAPIIfNeeded()
                }
            }
        }
    }

    // MARK: - Computed Properties (for Dashboard)

    /// 7-day cutoff for filtering old tasks (matches Flutter behavior)
    private var sevenDaysAgo: Date {
        Calendar.current.date(byAdding: .day, value: -7, to: Date()) ?? Date()
    }

    /// Source weight for priority sorting within the same day.
    /// Lower weight = higher priority. Manual tasks always appear above AI-generated.
    private static func sourceWeight(for source: String?) -> Int {
        switch source {
        case "manual": return 0
        case let s where s?.hasPrefix("transcription") == true: return 1
        case "screenshot": return 2
        default: return 1  // unknown sources treated as mid-priority
        }
    }

    /// Standard sort matching Python backend: due_at ASC (nulls last), created_at DESC (newest first)
    private static func sortByDueDateThenSource(_ a: TaskActionItem, _ b: TaskActionItem) -> Bool {
        let aDue = a.dueAt ?? .distantFuture
        let bDue = b.dueAt ?? .distantFuture
        if aDue != bDue {
            return aDue < bDue
        }
        // Tie-breaker: created_at descending (newest first) — matches Python backend
        return a.createdAt > b.createdAt
    }

    /// Overdue tasks (due date in the past but within 7 days) — loaded from SQLite
    @Published var overdueTasks: [TaskActionItem] = []

    /// Today's tasks (due today) — loaded from SQLite
    @Published var todaysTasks: [TaskActionItem] = []

    /// Tasks without due date (created within last 7 days) — loaded from SQLite
    @Published var tasksWithoutDueDate: [TaskActionItem] = []

    /// Load dashboard task lists directly from SQLite (avoids pagination issues)
    func loadDashboardTasks() async {
        let calendar = Calendar.current
        let startOfToday = calendar.startOfDay(for: Date())
        let endOfToday = calendar.date(byAdding: .day, value: 1, to: startOfToday)!
        let sevenDaysAgo = calendar.date(byAdding: .day, value: -7, to: Date()) ?? Date()

        do {
            async let overdueResult = ActionItemStorage.shared.getFilteredActionItems(
                limit: 50,
                completedStates: [false],
                dueDateAfter: sevenDaysAgo,
                dueDateBefore: startOfToday
            )
            async let todayResult = ActionItemStorage.shared.getFilteredActionItems(
                limit: 50,
                completedStates: [false],
                dueDateAfter: startOfToday,
                dueDateBefore: endOfToday
            )
            async let noDueDateResult = ActionItemStorage.shared.getFilteredActionItems(
                limit: 50,
                completedStates: [false],
                dueDateIsNull: true,
                createdAfter: sevenDaysAgo
            )

            let (overdue, today, noDueDate) = try await (overdueResult, todayResult, noDueDateResult)
            let sortedOverdue = overdue.sorted(by: Self.sortByDueDateThenSource)
            let sortedToday = today.sorted(by: Self.sortByDueDateThenSource)
            let sortedNoDueDate = noDueDate.sorted(by: Self.sortByDueDateThenSource)
            // Only update @Published properties if values actually changed to avoid unnecessary objectWillChange
            if overdueTasks != sortedOverdue { overdueTasks = sortedOverdue }
            if todaysTasks != sortedToday { todaysTasks = sortedToday }
            if tasksWithoutDueDate != sortedNoDueDate { tasksWithoutDueDate = sortedNoDueDate }
            log("TasksStore: Dashboard loaded from SQLite - overdue: \(overdue.count), today: \(today.count), noDeadline: \(noDueDate.count)")
        } catch {
            logError("TasksStore: Failed to load dashboard tasks from SQLite", error: error)
        }
    }

    var todoCount: Int {
        incompleteTasks.count
    }

    var doneCount: Int {
        completedTasks.count
    }

    var deletedCount: Int {
        deletedTasks.count
    }

    // MARK: - Initialization

    private init() {
        // Auto-refresh tasks every 30 seconds
        Timer.publish(every: 30.0, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in
                Task { await self?.refreshTasksIfNeeded() }
            }
            .store(in: &cancellables)

    }

    /// Refresh tasks if already loaded (for auto-refresh)
    /// Uses local-first pattern: sync API to cache, then reload from cache
    /// Merges changes in-place to avoid wholesale array replacement (which kills SwiftUI gestures)
    private func refreshTasksIfNeeded() async {
        // Skip if not signed in
        guard AuthService.shared.isSignedIn else { return }

        // Skip if page is not visible
        guard isActive else { return }

        // Skip if currently loading
        guard !isLoadingIncomplete, !isLoadingCompleted, !isLoadingDeleted, !isLoadingMore else { return }

        // Only refresh if we've already loaded tasks
        guard hasLoadedIncomplete else { return }

        // Silently sync and reload incomplete tasks (local-first, like Memories)
        do {
            let reloadLimit = max(pageSize, incompleteTasks.count)
            let response = try await APIClient.shared.getActionItems(
                limit: reloadLimit,
                offset: 0,
                completed: false
            )

            // Sync API results to local cache
            try await ActionItemStorage.shared.syncTaskActionItems(response.items)

            // Reconcile: if we got the full set, hard-delete local tasks absent from API
            // (completed/deleted on mobile). Safe: only deletes synced records.
            if response.items.count < reloadLimit {
                let apiIds = Set(response.items.map { $0.id })
                let reconciled = try await ActionItemStorage.shared.hardDeleteAbsentTasks(apiIds: apiIds)
                if reconciled > 0 {
                    log("TasksStore: Reconciled: hard-deleted \(reconciled) absent tasks during auto-refresh")
                }
            }

            // Reload from local cache (respects local changes like completions/deletions)
            let mergedTasks = try await ActionItemStorage.shared.getLocalActionItems(
                limit: reloadLimit,
                offset: 0,
                completed: false
            )

            // Merge without triggering @Published unless something actually changed
            let merged = mergeWithoutAdding(source: mergedTasks, current: incompleteTasks)
            if merged != incompleteTasks {
                // Log what actually changed
                let currentIds = Set(incompleteTasks.map { $0.id })
                let mergedIds = Set(merged.map { $0.id })
                let removed = currentIds.subtracting(mergedIds)
                let added = mergedIds.subtracting(currentIds)
                let updated = merged.filter { m in
                    if let c = incompleteTasks.first(where: { $0.id == m.id }), c != m { return true }
                    return false
                }
                log("RENDER: Auto-refresh diff: \(incompleteTasks.count)->\(merged.count) items, removed=\(removed.count), added=\(added.count), updated=\(updated.count) properties changed")
                if !removed.isEmpty { log("RENDER: Removed IDs: \(removed.prefix(5).joined(separator: ", "))") }
                if !updated.isEmpty { log("RENDER: Updated IDs: \(updated.prefix(3).map { $0.id.prefix(8) }.joined(separator: ", "))") }

                incompleteTasks = merged
                incompleteOffset = merged.count
                log("TasksStore: Auto-refresh updated incomplete tasks (\(merged.count) items)")
            } else {
                log("RENDER: Auto-refresh: no changes detected, skipping update")
            }
            let newHasMore = mergedTasks.count >= reloadLimit
            if hasMoreIncompleteTasks != newHasMore { hasMoreIncompleteTasks = newHasMore }
            await loadDashboardTasks()
        } catch {
            // Silently ignore errors during auto-refresh
            logError("TasksStore: Auto-refresh failed", error: error)
        }

        // Also refresh completed if loaded
        if hasLoadedCompleted {
            do {
                let response = try await APIClient.shared.getActionItems(
                    limit: pageSize,
                    offset: 0,
                    completed: true
                )

                // Sync to cache
                try await ActionItemStorage.shared.syncTaskActionItems(response.items)

                // Reload from cache
                let mergedTasks = try await ActionItemStorage.shared.getLocalActionItems(
                    limit: pageSize,
                    offset: 0,
                    completed: true
                )
                let merged = mergeWithoutAdding(source: mergedTasks, current: completedTasks)
                if merged != completedTasks {
                    completedTasks = merged
                    completedOffset = merged.count
                }
                let newHasMore = mergedTasks.count >= pageSize
                if hasMoreCompletedTasks != newHasMore { hasMoreCompletedTasks = newHasMore }
            } catch {
                logError("TasksStore: Auto-refresh completed tasks failed", error: error)
            }
        }

        // Also refresh deleted if loaded
        if hasLoadedDeleted {
            do {
                let response = try await APIClient.shared.getActionItems(
                    limit: pageSize,
                    offset: 0,
                    deleted: true
                )

                // Sync to cache
                try await ActionItemStorage.shared.syncTaskActionItems(response.items)

                // Reload from cache
                let mergedTasks = try await ActionItemStorage.shared.getLocalActionItems(
                    limit: pageSize,
                    offset: 0,
                    includeDeleted: true
                )
                // Filter to only deleted
                let newDeleted = mergedTasks.filter { $0.deleted == true }
                let merged = mergeWithoutAdding(source: newDeleted, current: deletedTasks)
                if merged != deletedTasks {
                    deletedTasks = merged
                    deletedOffset = merged.count
                }
                if hasMoreDeletedTasks != response.hasMore { hasMoreDeletedTasks = response.hasMore }
            } catch {
                logError("TasksStore: Auto-refresh deleted tasks failed", error: error)
            }
        }
    }

    /// Full reconciliation: paginate ALL incomplete task IDs from API, then hard-delete
    /// local tasks not present. Throttled to run at most every 5 minutes.
    /// Catches cases where the user has more tasks than one page of auto-refresh can cover.
    private func reconcileWithAPIIfNeeded() async {
        guard AuthService.shared.isSignedIn else { return }

        // Throttle: skip if last reconciliation was < 5 minutes ago
        if let last = lastReconciliationDate, Date().timeIntervalSince(last) < 300 {
            return
        }

        let batchSize = 500
        var allApiIds = Set<String>()
        var offset = 0

        do {
            while true {
                let response = try await APIClient.shared.getActionItems(
                    limit: batchSize,
                    offset: offset,
                    completed: false
                )
                allApiIds.formUnion(response.items.map { $0.id })
                offset += response.items.count
                if response.items.count < batchSize { break }
            }

            let deleted = try await ActionItemStorage.shared.hardDeleteAbsentTasks(apiIds: allApiIds)
            lastReconciliationDate = Date()

            if deleted > 0 {
                log("TasksStore: Full reconciliation: hard-deleted \(deleted) absent tasks")
                // Reload from cache to reflect deletions in UI
                let reloadLimit = max(pageSize, incompleteTasks.count)
                let refreshed = try await ActionItemStorage.shared.getLocalActionItems(
                    limit: reloadLimit,
                    offset: 0,
                    completed: false
                )
                if refreshed != incompleteTasks {
                    incompleteTasks = refreshed
                    incompleteOffset = refreshed.count
                }
                await loadDashboardTasks()
            }
        } catch {
            logError("TasksStore: Full reconciliation failed", error: error)
        }
    }

    /// Build a merged result from source and current: update changed items, remove gone ones.
    /// Does NOT add new items — new tasks only appear on explicit load (initial load, tab switch).
    /// Returns a new array only if different from current (caller compares with == before assigning
    /// to @Published property, preventing unnecessary objectWillChange notifications).
    private func mergeWithoutAdding(source: [TaskActionItem], current: [TaskActionItem]) -> [TaskActionItem] {
        let sourceById = Dictionary(uniqueKeysWithValues: source.map { ($0.id, $0) })
        let sourceIds = Set(source.map { $0.id })

        var result = current

        // Update existing items
        for i in result.indices {
            if let updated = sourceById[result[i].id], updated != result[i] {
                result[i] = updated
            }
        }

        // Remove items no longer in source (e.g. completed/deleted by another device)
        result.removeAll { !sourceIds.contains($0.id) }

        return result
    }

    // MARK: - Reload from Local Cache

    /// Reload tasks from SQLite without hitting the API.
    /// Call this when the local database has been modified externally (e.g., by an AI tool call).
    func reloadFromLocalCache() async {
        guard hasLoadedIncomplete else { return }

        do {
            let reloadLimit = max(pageSize, incompleteTasks.count + 10)
            let cachedTasks = try await ActionItemStorage.shared.getLocalActionItems(
                limit: reloadLimit,
                offset: 0,
                completed: false
            )
            if cachedTasks != incompleteTasks {
                incompleteTasks = cachedTasks
                incompleteOffset = cachedTasks.count
                log("TasksStore: Reloaded \(cachedTasks.count) incomplete tasks from local cache (external change)")
            }
        } catch {
            logError("TasksStore: Failed to reload incomplete tasks from cache", error: error)
        }

        // Also reload completed if already loaded
        if hasLoadedCompleted {
            do {
                let cachedCompleted = try await ActionItemStorage.shared.getLocalActionItems(
                    limit: pageSize,
                    offset: 0,
                    completed: true
                )
                if cachedCompleted != completedTasks {
                    completedTasks = cachedCompleted
                    completedOffset = cachedCompleted.count
                    log("TasksStore: Reloaded \(cachedCompleted.count) completed tasks from local cache (external change)")
                }
            } catch {
                logError("TasksStore: Failed to reload completed tasks from cache", error: error)
            }
        }
    }

    // MARK: - Load Tasks

    /// Load incomplete tasks if not already loaded (call this on app launch)
    func loadTasksIfNeeded() async {
        guard !hasLoadedIncomplete else { return }
        await loadIncompleteTasks()
        await loadDashboardTasks()
        // Also load deleted tasks in background so the filter count is ready
        if !hasLoadedDeleted {
            await loadDeletedTasks()
        }
    }

    /// Legacy method - loads incomplete tasks
    func loadTasks() async {
        await loadIncompleteTasks()
        await loadDashboardTasks()
        // Also load deleted tasks so the "Removed by AI" filter count is ready
        if !hasLoadedDeleted {
            await loadDeletedTasks()
        }
        // Kick off one-time full sync in background (populates SQLite with all tasks)
        // Then retry pushing any locally-created tasks that failed to sync
        Task {
            await performFullSyncIfNeeded()
            await migrateAITasksToStagedIfNeeded()
            await migrateConversationItemsToStagedIfNeeded()
            await retryUnsyncedItems()
        }
        // Backfill relevance scores for unscored tasks (independent of full sync)
        Task {
            let userId = UserDefaults.standard.string(forKey: "auth_userId") ?? "unknown"
            await backfillRelevanceScoresIfNeeded(userId: userId)
        }
        // Ensure minimum promoted tasks on startup — insert directly, no full reload
        Task {
            let promoted = await TaskPromotionService.shared.ensureMinimumOnStartup()
            if !promoted.isEmpty {
                self.incompleteTasks.append(contentsOf: promoted)
                log("TasksStore: Inserted \(promoted.count) promoted tasks on startup")
            }
        }
    }

    /// Load incomplete tasks (To Do) using local-first pattern (like Memories)
    /// Step 1: Show cached data instantly. Step 2: Sync API to cache, reload from cache.
    func loadIncompleteTasks() async {
        guard !isLoadingIncomplete else { return }

        isLoadingIncomplete = true
        error = nil
        incompleteOffset = 0

        // Step 1: Load from local cache first for instant display
        do {
            let cachedTasks = try await ActionItemStorage.shared.getLocalActionItems(
                limit: pageSize,
                offset: 0,
                completed: false
            )
            if !cachedTasks.isEmpty {
                incompleteTasks = cachedTasks
                incompleteOffset = cachedTasks.count
                hasMoreIncompleteTasks = cachedTasks.count >= pageSize
                isLoadingIncomplete = false  // Show cached data immediately
                log("TasksStore: Loaded \(cachedTasks.count) incomplete tasks from local cache")
            }
        } catch {
            log("TasksStore: Local cache unavailable for incomplete tasks, falling back to API")
        }

        // Step 2: Fetch from API, sync to cache, reload from cache
        do {
            let response = try await APIClient.shared.getActionItems(
                limit: pageSize,
                offset: 0,
                completed: false
            )
            hasLoadedIncomplete = true
            log("TasksStore: Fetched \(response.items.count) incomplete tasks from API")

            // Sync API data to local cache
            do {
                try await ActionItemStorage.shared.syncTaskActionItems(response.items)
            } catch {
                logError("TasksStore: Failed to sync incomplete tasks to local cache", error: error)
            }

            // Reload from cache to get merged data (local changes + API data)
            let mergedTasks = try await ActionItemStorage.shared.getLocalActionItems(
                limit: pageSize,
                offset: 0,
                completed: false
            )
            incompleteTasks = mergedTasks
            incompleteOffset = mergedTasks.count
            hasMoreIncompleteTasks = mergedTasks.count >= pageSize
            log("TasksStore: Showing \(mergedTasks.count) incomplete tasks from merged local cache")
        } catch {
            if incompleteTasks.isEmpty {
                self.error = error.localizedDescription
            }
            logError("TasksStore: Failed to load incomplete tasks from API", error: error)
        }

        isLoadingIncomplete = false
        NotificationCenter.default.post(name: .tasksPageDidLoad, object: nil)
    }

    /// Load completed tasks (Done) - called when user views Done tab
    /// Uses local-first pattern
    func loadCompletedTasks() async {
        guard !isLoadingCompleted else { return }

        isLoadingCompleted = true
        error = nil
        completedOffset = 0

        // Step 1: Load from local cache first
        do {
            let cachedTasks = try await ActionItemStorage.shared.getLocalActionItems(
                limit: pageSize,
                offset: 0,
                completed: true
            )
            if !cachedTasks.isEmpty {
                completedTasks = cachedTasks
                completedOffset = cachedTasks.count
                hasMoreCompletedTasks = cachedTasks.count >= pageSize
                isLoadingCompleted = false
                log("TasksStore: Loaded \(cachedTasks.count) completed tasks from local cache")
            }
        } catch {
            log("TasksStore: Local cache unavailable for completed tasks")
        }

        // Step 2: Fetch from API and sync
        do {
            let response = try await APIClient.shared.getActionItems(
                limit: pageSize,
                offset: 0,
                completed: true
            )
            hasLoadedCompleted = true
            log("TasksStore: Fetched \(response.items.count) completed tasks from API")

            // Step 3: Sync and reload from cache
            do {
                try await ActionItemStorage.shared.syncTaskActionItems(response.items)

                let mergedTasks = try await ActionItemStorage.shared.getLocalActionItems(
                    limit: pageSize,
                    offset: 0,
                    completed: true
                )
                completedTasks = mergedTasks
                completedOffset = mergedTasks.count
                hasMoreCompletedTasks = mergedTasks.count >= pageSize
                log("TasksStore: Showing \(mergedTasks.count) completed tasks from merged local cache")
            } catch {
                logError("TasksStore: Failed to sync/reload completed tasks", error: error)
                completedTasks = response.items
                completedOffset = response.items.count
                hasMoreCompletedTasks = response.hasMore
            }
        } catch {
            if completedTasks.isEmpty {
                self.error = error.localizedDescription
            }
            logError("TasksStore: Failed to load completed tasks from API", error: error)
        }

        isLoadingCompleted = false
        NotificationCenter.default.post(name: .tasksPageDidLoad, object: nil)
    }

    /// Load deleted tasks (Removed by AI) - called when user views the filter
    /// Uses local-first pattern
    func loadDeletedTasks() async {
        guard !isLoadingDeleted else { return }

        isLoadingDeleted = true
        error = nil
        deletedOffset = 0

        // Step 1: Load from local cache first
        do {
            let cachedTasks = try await ActionItemStorage.shared.getLocalActionItems(
                limit: pageSize,
                offset: 0,
                completed: nil,
                includeDeleted: true
            )
            let deleted = cachedTasks.filter { $0.deleted == true }
            if !deleted.isEmpty {
                deletedTasks = deleted
                deletedOffset = deleted.count
                hasMoreDeletedTasks = deleted.count >= pageSize
                isLoadingDeleted = false
                log("TasksStore: Loaded \(deleted.count) deleted tasks from local cache")
            }
        } catch {
            log("TasksStore: Local cache unavailable for deleted tasks")
        }

        // Step 2: Fetch from API and sync
        do {
            let response = try await APIClient.shared.getActionItems(
                limit: pageSize,
                offset: 0,
                deleted: true
            )
            hasLoadedDeleted = true
            log("TasksStore: Fetched \(response.items.count) deleted tasks from API")

            // Step 3: Sync and reload from cache
            do {
                try await ActionItemStorage.shared.syncTaskActionItems(response.items)

                let allTasks = try await ActionItemStorage.shared.getLocalActionItems(
                    limit: pageSize,
                    offset: 0,
                    completed: nil,
                    includeDeleted: true
                )
                let mergedDeleted = allTasks.filter { $0.deleted == true }
                deletedTasks = mergedDeleted
                deletedOffset = mergedDeleted.count
                hasMoreDeletedTasks = response.hasMore
                log("TasksStore: Showing \(mergedDeleted.count) deleted tasks from merged local cache")
            } catch {
                logError("TasksStore: Failed to sync/reload deleted tasks", error: error)
                deletedTasks = response.items
                deletedOffset = response.items.count
                hasMoreDeletedTasks = response.hasMore
            }
        } catch {
            if deletedTasks.isEmpty {
                self.error = error.localizedDescription
            }
            logError("TasksStore: Failed to load deleted tasks from API", error: error)
        }

        isLoadingDeleted = false
        NotificationCenter.default.post(name: .tasksPageDidLoad, object: nil)
    }

    /// One-time background sync that fetches ALL tasks from the API and stores in SQLite.
    /// Ensures filter/search queries have the full dataset. Keyed per user so it runs once per account.
    private func performFullSyncIfNeeded() async {
        let userId = UserDefaults.standard.string(forKey: "auth_userId") ?? "unknown"
        let syncKey = "tasksFullSyncCompleted_v9_\(userId)"

        guard !UserDefaults.standard.bool(forKey: syncKey) else {
            log("TasksStore: Full sync already completed for user \(userId)")
            return
        }

        log("TasksStore: Starting full sync for user \(userId)")

        var totalSynced = 0
        let batchSize = 500

        do {
            // Sync all incomplete tasks (start at 0 — initial load uses a date filter so it's a different dataset)
            var allIncompleteApiIds = Set<String>()
            var offset = 0
            while true {
                let response = try await APIClient.shared.getActionItems(
                    limit: batchSize,
                    offset: offset,
                    completed: false
                )
                if response.items.isEmpty { break }
                try await ActionItemStorage.shared.syncTaskActionItems(response.items, overrideStagedDeletions: true)
                allIncompleteApiIds.formUnion(response.items.map { $0.id })
                totalSynced += response.items.count
                offset += response.items.count
                log("TasksStore: Full sync progress - \(totalSynced) tasks synced (incomplete)")
                if response.items.count < batchSize { break }
            }

            // Now that we have ALL incomplete API IDs, mark any local tasks
            // not in this set as staged. This is safe because we have the full dataset.
            if !allIncompleteApiIds.isEmpty {
                try await ActionItemStorage.shared.markAbsentTasksAsStaged(apiIds: allIncompleteApiIds)
            }

            // Sync all completed tasks
            offset = 0
            while true {
                let response = try await APIClient.shared.getActionItems(
                    limit: batchSize,
                    offset: offset,
                    completed: true
                )
                if response.items.isEmpty { break }
                try await ActionItemStorage.shared.syncTaskActionItems(response.items)
                totalSynced += response.items.count
                offset += response.items.count
                log("TasksStore: Full sync progress - \(totalSynced) tasks synced (completed)")
                if response.items.count < batchSize { break }
            }

            // Purge any soft-deleted rows from local SQLite (one-time cleanup)
            let purged = try await ActionItemStorage.shared.purgeAllSoftDeletedItems()
            if purged > 0 {
                log("TasksStore: Purged \(purged) soft-deleted items from local SQLite")
            }

            UserDefaults.standard.set(true, forKey: syncKey)
            log("TasksStore: Full sync completed - \(totalSynced) tasks synced total")

            // Reload incomplete tasks from cache so UI reflects the full dataset
            do {
                let refreshed = try await ActionItemStorage.shared.getLocalActionItems(
                    limit: pageSize,
                    offset: 0,
                    completed: false
                )
                incompleteTasks = refreshed
                incompleteOffset = refreshed.count
                hasMoreIncompleteTasks = refreshed.count >= pageSize
                log("TasksStore: Refreshed UI after full sync - \(refreshed.count) incomplete tasks")
                await loadDashboardTasks()
            } catch {
                logError("TasksStore: Failed to refresh UI after full sync", error: error)
            }

        } catch {
            logError("TasksStore: Full sync failed (will retry next launch)", error: error)
        }
    }

    /// In-memory guard to prevent duplicate migration calls within the same app session
    private static var isMigrating = false

    /// One-time migration: tell backend to move excess AI tasks to staged_tasks subcollection.
    /// The SQLite migration handles local data; this handles Firestore.
    /// Sets the flag optimistically before the request to avoid retry loops on timeout.
    private func migrateAITasksToStagedIfNeeded() async {
        let userId = UserDefaults.standard.string(forKey: "auth_userId") ?? "unknown"
        let migrationKey = "stagedTasksMigrationCompleted_v4_\(userId)"

        guard !UserDefaults.standard.bool(forKey: migrationKey) else {
            log("TasksStore: Staged tasks migration already completed for user \(userId)")
            return
        }

        // In-memory guard: loadTasks() can be called from multiple pages
        guard !Self.isMigrating else {
            log("TasksStore: Staged tasks migration already in progress, skipping")
            return
        }
        Self.isMigrating = true

        // Set flag optimistically — the migration is idempotent and safe to skip on re-run.
        // This prevents infinite retry loops when the backend succeeds but the client times out.
        UserDefaults.standard.set(true, forKey: migrationKey)

        log("TasksStore: Starting staged tasks backend migration for user \(userId)")

        do {
            try await APIClient.shared.migrateStagedTasks()
            log("TasksStore: Staged tasks backend migration completed")
        } catch {
            log("TasksStore: Staged tasks backend migration fired (may complete in background): \(error.localizedDescription)")
        }
        Self.isMigrating = false
    }

    /// One-time migration of conversation-extracted action items (no source field) to staged_tasks.
    /// These were created by the old save_action_items path that bypassed the staging pipeline.
    private func migrateConversationItemsToStagedIfNeeded() async {
        let userId = UserDefaults.standard.string(forKey: "auth_userId") ?? "unknown"
        let migrationKey = "conversationItemsMigrationCompleted_v4_\(userId)"

        guard !UserDefaults.standard.bool(forKey: migrationKey) else { return }

        UserDefaults.standard.set(true, forKey: migrationKey)
        log("TasksStore: Starting conversation items migration for user \(userId)")

        do {
            try await APIClient.shared.migrateConversationItemsToStaged()
            log("TasksStore: Conversation items migration completed, resetting full sync to clean up local SQLite")

            // Reset full sync flag so it re-runs and marks migrated items as staged locally
            let syncKey = "tasksFullSyncCompleted_v9_\(userId)"
            UserDefaults.standard.set(false, forKey: syncKey)

            // Run full sync now to clean up local SQLite
            await performFullSyncIfNeeded()
        } catch {
            log("TasksStore: Conversation items migration fired (may complete in background): \(error.localizedDescription)")
        }
    }

    /// Retry syncing locally-created tasks that failed to push to the backend.
    /// These are records with backendSynced=false and no backendId — the API call
    /// failed during extraction and there was no retry mechanism.
    private func retryUnsyncedItems() async {
        guard !isRetryingUnsynced else {
            log("TasksStore: Skipping retryUnsyncedItems (already in progress)")
            return
        }
        isRetryingUnsynced = true
        defer { isRetryingUnsynced = false }

        let items: [ActionItemRecord]
        do {
            items = try await ActionItemStorage.shared.getUnsyncedActionItems()
        } catch {
            logError("TasksStore: Failed to fetch unsynced items", error: error)
            return
        }

        guard !items.isEmpty else { return }
        log("TasksStore: Retrying sync for \(items.count) unsynced items")

        var synced = 0
        for item in items {
            guard let localId = item.id else { continue }

            // Re-check: the normal sync path may have synced this item while we were iterating
            if let current = try? await ActionItemStorage.shared.getActionItem(id: localId),
               current.backendSynced || (current.backendId != nil && !current.backendId!.isEmpty) {
                continue
            }

            // Parse metadata back from JSON
            var metadata: [String: Any]?
            if let json = item.metadataJson, let data = json.data(using: .utf8) {
                metadata = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            }

            do {
                let response = try await APIClient.shared.createActionItem(
                    description: item.description,
                    dueAt: item.dueAt,
                    source: item.source,
                    priority: item.priority,
                    category: item.category,
                    metadata: metadata,
                    relevanceScore: item.relevanceScore
                )
                try await ActionItemStorage.shared.markSynced(id: localId, backendId: response.id)
                synced += 1
            } catch {
                // Skip this item, will retry next launch
                continue
            }
        }

        log("TasksStore: Retry sync completed — \(synced)/\(items.count) items synced")
    }


    /// One-time backfill: assign relevance scores to all unscored active tasks.
    /// Each unscored task gets max+1 sequentially so they appear at the bottom
    /// until the next Gemini rescore properly ranks them.
    private func backfillRelevanceScoresIfNeeded(userId: String) async {
        let backfillKey = "tasksRelevanceScoreBackfill_v1_\(userId)"
        guard !UserDefaults.standard.bool(forKey: backfillKey) else { return }

        do {
            let count = try await ActionItemStorage.shared.backfillUnscoredTasks()
            UserDefaults.standard.set(true, forKey: backfillKey)
            log("TasksStore: Relevance score backfill complete - scored \(count) tasks")
        } catch {
            logError("TasksStore: Relevance score backfill failed", error: error)
        }
    }

    /// Load more incomplete tasks (pagination) - local-first
    func loadMoreIncompleteIfNeeded(currentTask: TaskActionItem) async {
        guard hasMoreIncompleteTasks, !isLoadingMore else { return }

        let thresholdIndex = incompleteTasks.index(incompleteTasks.endIndex, offsetBy: -10, limitedBy: incompleteTasks.startIndex) ?? incompleteTasks.startIndex
        guard let taskIndex = incompleteTasks.firstIndex(where: { $0.id == currentTask.id }),
              taskIndex >= thresholdIndex else {
            return
        }

        isLoadingMore = true

        do {
            let response = try await APIClient.shared.getActionItems(
                limit: pageSize,
                offset: incompleteOffset,
                completed: false
            )

            // Sync to cache
            try await ActionItemStorage.shared.syncTaskActionItems(response.items)

            incompleteTasks.append(contentsOf: response.items)
            hasMoreIncompleteTasks = response.hasMore
            incompleteOffset += response.items.count
            log("TasksStore: Loaded \(response.items.count) more incomplete tasks from API")
        } catch {
            logError("TasksStore: Failed to load more incomplete tasks", error: error)
        }

        isLoadingMore = false
    }

    /// Load more completed tasks (pagination) - local-first
    func loadMoreCompletedIfNeeded(currentTask: TaskActionItem) async {
        guard hasMoreCompletedTasks, !isLoadingMore else { return }

        let thresholdIndex = completedTasks.index(completedTasks.endIndex, offsetBy: -10, limitedBy: completedTasks.startIndex) ?? completedTasks.startIndex
        guard let taskIndex = completedTasks.firstIndex(where: { $0.id == currentTask.id }),
              taskIndex >= thresholdIndex else {
            return
        }

        isLoadingMore = true

        // Step 1: Try to load more from local cache first
        do {
            let moreFromCache = try await ActionItemStorage.shared.getLocalActionItems(
                limit: pageSize,
                offset: completedOffset,
                completed: true
            )

            if !moreFromCache.isEmpty {
                completedTasks.append(contentsOf: moreFromCache)
                completedOffset += moreFromCache.count
                hasMoreCompletedTasks = moreFromCache.count >= pageSize
                log("TasksStore: Loaded \(moreFromCache.count) more completed tasks from local cache")
                isLoadingMore = false
                return
            }
        } catch {
            log("TasksStore: Local cache pagination failed for completed tasks")
        }

        // Step 2: If local cache exhausted, fetch from API
        do {
            let response = try await APIClient.shared.getActionItems(
                limit: pageSize,
                offset: completedOffset,
                completed: true
            )

            // Sync to cache first
            try await ActionItemStorage.shared.syncTaskActionItems(response.items)

            completedTasks.append(contentsOf: response.items)
            hasMoreCompletedTasks = response.hasMore
            completedOffset += response.items.count
            log("TasksStore: Loaded \(response.items.count) more completed tasks from API")
        } catch {
            logError("TasksStore: Failed to load more completed tasks", error: error)
        }

        isLoadingMore = false
    }

    /// Legacy pagination - routes to appropriate method based on task completion status
    func loadMoreIfNeeded(currentTask: TaskActionItem) async {
        if currentTask.completed {
            await loadMoreCompletedIfNeeded(currentTask: currentTask)
        } else {
            await loadMoreIncompleteIfNeeded(currentTask: currentTask)
        }
    }

    // MARK: - Recurrence Helpers

    /// Compute the next due date for a recurring task, skipping past dates.
    private func nextFutureDueDate(from dueDate: Date, rule: String) -> Date? {
        let calendar = Calendar.current
        func nextDate(from date: Date) -> Date? {
            switch rule {
            case "daily":
                return calendar.date(byAdding: .day, value: 1, to: date)
            case "weekdays":
                var next = calendar.date(byAdding: .day, value: 1, to: date)!
                while calendar.isDateInWeekend(next) {
                    next = calendar.date(byAdding: .day, value: 1, to: next)!
                }
                return next
            case "weekly":
                return calendar.date(byAdding: .weekOfYear, value: 1, to: date)
            case "biweekly":
                return calendar.date(byAdding: .weekOfYear, value: 2, to: date)
            case "monthly":
                return calendar.date(byAdding: .month, value: 1, to: date)
            default:
                return nil
            }
        }
        guard var next = nextDate(from: dueDate) else { return nil }
        // Skip past dates to avoid pile-up when completing late
        while next < Date() {
            guard let n = nextDate(from: next) else { return nil }
            next = n
        }
        return next
    }

    // MARK: - Task Actions

    func toggleTask(_ task: TaskActionItem) async {
        let newCompleted = !task.completed

        // 1. Local-first: update SQLite immediately so auto-refresh reads correct state
        do {
            try await ActionItemStorage.shared.updateCompletionStatus(
                backendId: task.id, completed: newCompleted
            )
        } catch {
            logError("TasksStore: Failed to update task locally", error: error)
            self.error = error.localizedDescription
            return
        }

        // 2. Read back from SQLite to get a TaskActionItem with the new completed value
        guard let updatedTask = try? await ActionItemStorage.shared.getLocalActionItem(byBackendId: task.id) else {
            logError("TasksStore: Failed to read back toggled task", error: nil)
            return
        }

        // 3. Update in-memory arrays immediately (optimistic UI)
        if newCompleted {
            incompleteTasks.removeAll { $0.id == task.id }
            completedTasks.insert(updatedTask, at: 0)

            // Compact relevance scores to fill the gap
            if let score = task.relevanceScore {
                try? await ActionItemStorage.shared.compactScoresAfterRemoval(removedScore: score)
                Task { await self.syncScoresToBackend() }
            }

            // Promote a staged task to fill the vacated slot
            if task.source?.contains("screenshot") == true {
                Task {
                    let promoted = await TaskPromotionService.shared.promoteIfNeeded()
                    if !promoted.isEmpty {
                        self.incompleteTasks.append(contentsOf: promoted)
                        log("TasksStore: Inserted \(promoted.count) promoted tasks after completion")
                    }
                }
            }
        } else {
            completedTasks.removeAll { $0.id == task.id }
            incompleteTasks.insert(updatedTask, at: 0)
        }

        // 4. Call API in background, revert on failure
        do {
            let apiResult = try await APIClient.shared.updateActionItem(
                id: task.id,
                completed: newCompleted
            )
            // Sync API result to store server-side timestamps
            try await ActionItemStorage.shared.syncTaskActionItems([apiResult])

            // Spawn next recurring instance when completing a recurring task
            if newCompleted, let rule = task.recurrenceRule, !rule.isEmpty {
                let baseDueDate = task.dueAt ?? Date()
                if let nextDue = nextFutureDueDate(from: baseDueDate, rule: rule) {
                    let parentId = task.recurrenceParentId ?? task.id
                    if let spawned = try? await APIClient.shared.createActionItem(
                        description: task.description,
                        dueAt: nextDue,
                        source: "recurring",
                        priority: task.priority,
                        category: task.category,
                        recurrenceRule: rule,
                        recurrenceParentId: parentId
                    ) {
                        try? await ActionItemStorage.shared.syncTaskActionItems([spawned])
                        incompleteTasks.insert(spawned, at: 0)
                        log("TasksStore: Spawned recurring task \(spawned.id) due \(nextDue)")
                    }
                }
            }

            await loadDashboardTasks()
        } catch {
            logError("TasksStore: Failed to toggle task on backend, reverting", error: error)
            // Revert SQLite
            try? await ActionItemStorage.shared.updateCompletionStatus(
                backendId: task.id, completed: task.completed
            )
            // Revert in-memory arrays
            if newCompleted {
                completedTasks.removeAll { $0.id == task.id }
                incompleteTasks.insert(task, at: 0)
            } else {
                incompleteTasks.removeAll { $0.id == task.id }
                completedTasks.insert(task, at: 0)
            }
            self.error = error.localizedDescription
        }
    }

    @discardableResult
    func createTask(description: String, dueAt: Date?, priority: String?, tags: [String]? = nil, recurrenceRule: String? = nil) async -> TaskActionItem? {
        do {
            var metadata: [String: Any]? = nil
            if let tags = tags, !tags.isEmpty {
                metadata = ["tags": tags]
            }

            let created = try await APIClient.shared.createActionItem(
                description: description,
                dueAt: dueAt,
                source: "manual",
                priority: priority,
                category: tags?.first,
                metadata: metadata,
                recurrenceRule: recurrenceRule
            )

            // Sync to local SQLite cache
            try await ActionItemStorage.shared.syncTaskActionItems([created])

            // New tasks are incomplete, add to incomplete list
            incompleteTasks.insert(created, at: 0)
            return created
        } catch {
            self.error = error.localizedDescription
            logError("TasksStore: Failed to create task", error: error)
            return nil
        }
    }

    func deleteTask(_ task: TaskActionItem) async {
        // Local-first: soft-delete in SQLite immediately for instant UI update
        do {
            try await ActionItemStorage.shared.deleteActionItemByBackendId(task.id, deletedBy: "user")
        } catch {
            logError("TasksStore: Failed to soft-delete task locally", error: error)
        }

        // Remove from in-memory arrays immediately
        if task.completed {
            completedTasks.removeAll { $0.id == task.id }
        } else {
            incompleteTasks.removeAll { $0.id == task.id }
        }

        // Compact relevance scores to fill the gap
        if let score = task.relevanceScore {
            try? await ActionItemStorage.shared.compactScoresAfterRemoval(removedScore: score)
            Task { await self.syncScoresToBackend() }
        }

        // Promote a staged task to fill the vacated slot
        if task.source?.contains("screenshot") == true {
            Task {
                let promoted = await TaskPromotionService.shared.promoteIfNeeded()
                if !promoted.isEmpty {
                    self.incompleteTasks.append(contentsOf: promoted)
                    log("TasksStore: Inserted \(promoted.count) promoted tasks after deletion")
                }
            }
        }

        // Hard-delete on backend in background
        do {
            try await APIClient.shared.deleteActionItem(id: task.id)
        } catch {
            logError("TasksStore: Failed to hard-delete task on backend (local delete preserved)", error: error)
        }
    }

    /// Restore a previously deleted task (for undo)
    /// Re-inserts the task into SQLite and re-creates on backend (since both were hard-deleted).
    func restoreTask(_ task: TaskActionItem) async {
        // 1. Re-insert into SQLite from the in-memory task object
        do {
            try await ActionItemStorage.shared.syncTaskActionItems([task])
        } catch {
            logError("TasksStore: Failed to re-insert task locally for undo", error: error)
            return
        }

        // 2. Re-insert into the appropriate in-memory array
        if task.completed {
            completedTasks.insert(task, at: 0)
        } else {
            incompleteTasks.insert(task, at: 0)
        }

        // 3. Re-create on backend (hard-delete already removed it)
        do {
            let created = try await APIClient.shared.createActionItem(
                description: task.description,
                dueAt: task.dueAt,
                priority: task.priority
            )
            // Update local record with new backend ID
            try await ActionItemStorage.shared.syncTaskActionItems([created])
            log("TasksStore: Restored task via undo (new backend ID: \(created.id))")
        } catch {
            logError("TasksStore: Failed to re-create task on backend (local restore preserved)", error: error)
        }
    }

    func updateTask(_ task: TaskActionItem, description: String? = nil, dueAt: Date? = nil, priority: String? = nil, recurrenceRule: String? = nil) async {
        // Track manual edits: if description is changed, mark as manually edited
        var metadata: [String: Any]? = nil
        if description != nil {
            metadata = ["manually_edited": true]
            // Preserve existing tags in metadata
            if !task.tags.isEmpty {
                metadata?["tags"] = task.tags
            }
        }

        // 1. Local-first: update SQLite immediately so auto-refresh reads correct state
        do {
            try await ActionItemStorage.shared.updateActionItemFields(
                backendId: task.id,
                description: description,
                dueAt: dueAt,
                priority: priority,
                metadata: metadata,
                recurrenceRule: recurrenceRule
            )
        } catch {
            logError("TasksStore: Failed to update task locally", error: error)
            self.error = error.localizedDescription
            return
        }

        // 2. Read back from SQLite and update in-memory arrays immediately
        if let updatedTask = try? await ActionItemStorage.shared.getLocalActionItem(byBackendId: task.id) {
            if task.completed {
                if let index = completedTasks.firstIndex(where: { $0.id == task.id }) {
                    completedTasks[index] = updatedTask
                }
            } else {
                if let index = incompleteTasks.firstIndex(where: { $0.id == task.id }) {
                    incompleteTasks[index] = updatedTask
                }
            }
        }

        // 3. Call API in background
        do {
            let apiResult = try await APIClient.shared.updateActionItem(
                id: task.id,
                description: description,
                dueAt: dueAt,
                priority: priority,
                metadata: metadata,
                recurrenceRule: recurrenceRule
            )
            // Sync API result to store server-side timestamps
            try await ActionItemStorage.shared.syncTaskActionItems([apiResult])
        } catch {
            // Local change persists; next successful sync will reconcile
            self.error = error.localizedDescription
            logError("TasksStore: Failed to update task on backend (local update preserved)", error: error)
        }
    }

    // MARK: - Chat Session

    /// Update the chatSessionId for a task in memory
    func updateChatSessionId(taskId: String, sessionId: String) {
        if let idx = incompleteTasks.firstIndex(where: { $0.id == taskId }) {
            incompleteTasks[idx].chatSessionId = sessionId
        } else if let idx = completedTasks.firstIndex(where: { $0.id == taskId }) {
            completedTasks[idx].chatSessionId = sessionId
        }
    }

    // MARK: - Bulk Actions

    func deleteMultipleTasks(ids: [String]) async {
        // Collect relevance scores before removing from memory
        let allTasks = incompleteTasks + completedTasks
        let scores = ids.compactMap { id in allTasks.first(where: { $0.id == id })?.relevanceScore }

        // Local-first: soft-delete all in SQLite and remove from memory immediately
        for id in ids {
            do {
                try await ActionItemStorage.shared.deleteActionItemByBackendId(id, deletedBy: "user")
            } catch {
                logError("TasksStore: Failed to soft-delete task \(id) locally", error: error)
            }
            incompleteTasks.removeAll { $0.id == id }
            completedTasks.removeAll { $0.id == id }
        }

        // Compact relevance scores (process highest first so shifts don't affect each other)
        for score in scores.sorted(by: >) {
            try? await ActionItemStorage.shared.compactScoresAfterRemoval(removedScore: score)
        }
        if !scores.isEmpty {
            Task { await self.syncScoresToBackend() }
        }

        // Hard-delete on backend in background
        for id in ids {
            do {
                try await APIClient.shared.deleteActionItem(id: id)
            } catch {
                logError("TasksStore: Failed to hard-delete task \(id) on backend (local delete preserved)", error: error)
            }
        }
    }

    /// Sync all scored tasks' relevance scores to backend
    private func syncScoresToBackend() async {
        do {
            let tasks = try await ActionItemStorage.shared.getAllScoredTasks()
            let scores = tasks.compactMap { t -> (id: String, score: Int)? in
                guard let s = t.relevanceScore, !t.id.hasPrefix("local_") else { return nil }
                return (id: t.id, score: s)
            }
            guard !scores.isEmpty else { return }
            try await APIClient.shared.batchUpdateScores(scores)
        } catch {
            logError("TasksStore: Failed to sync scores to backend", error: error)
        }
    }
}
