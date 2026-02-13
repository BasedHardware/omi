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

    /// Whether the tasks page (or dashboard) is currently visible.
    /// Auto-refresh only runs when active to avoid unnecessary API calls.
    var isActive = false {
        didSet {
            if isActive && !oldValue && hasLoadedIncomplete {
                // Refresh immediately when becoming active
                Task { await refreshTasksIfNeeded() }
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

    /// Standard sort: due date ascending, then manual > AI-generated, then newest first
    private static func sortByDueDateThenSource(_ a: TaskActionItem, _ b: TaskActionItem) -> Bool {
        let aDue = a.dueAt ?? .distantFuture
        let bDue = b.dueAt ?? .distantFuture
        if aDue != bDue {
            return aDue < bDue
        }
        let aWeight = sourceWeight(for: a.source)
        let bWeight = sourceWeight(for: b.source)
        if aWeight != bWeight {
            return aWeight < bWeight
        }
        return a.createdAt > b.createdAt
    }

    /// Overdue tasks (due date in the past but within 7 days)
    var overdueTasks: [TaskActionItem] {
        let startOfToday = Calendar.current.startOfDay(for: Date())
        return incompleteTasks
            .filter { task in
                guard let dueAt = task.dueAt else { return false }
                // Must be overdue (before today) but within 7 days (not too old)
                return dueAt < startOfToday && dueAt >= sevenDaysAgo
            }
            .sorted(by: Self.sortByDueDateThenSource)
    }

    /// Today's tasks (due today)
    var todaysTasks: [TaskActionItem] {
        let calendar = Calendar.current
        let startOfToday = calendar.startOfDay(for: Date())
        let endOfToday = calendar.date(byAdding: .day, value: 1, to: startOfToday)!
        return incompleteTasks
            .filter { task in
                guard let dueAt = task.dueAt else { return false }
                return dueAt >= startOfToday && dueAt < endOfToday
            }
            .sorted(by: Self.sortByDueDateThenSource)
    }

    /// Tasks without due date (created within last 7 days)
    var tasksWithoutDueDate: [TaskActionItem] {
        incompleteTasks
            .filter { task in
                // No due date, but created within 7 days
                task.dueAt == nil && task.createdAt >= sevenDaysAgo
            }
            .sorted(by: Self.sortByDueDateThenSource)
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
    private func refreshTasksIfNeeded() async {
        // Skip if page is not visible
        guard isActive else { return }

        // Skip if currently loading
        guard !isLoadingIncomplete, !isLoadingCompleted, !isLoadingDeleted, !isLoadingMore else { return }

        // Only refresh if we've already loaded tasks
        guard hasLoadedIncomplete else { return }

        // Silently sync and reload incomplete tasks
        do {
            let response = try await APIClient.shared.getActionItems(
                limit: pageSize,
                offset: 0,
                completed: false
            )

            // Sync API results to local cache
            try await ActionItemStorage.shared.syncTaskActionItems(response.items)

            // Use API response directly to match iOS/Flutter behavior
            let updated = response.items
            if updated != incompleteTasks {
                incompleteTasks = updated
                hasMoreIncompleteTasks = updated.count >= pageSize
                incompleteOffset = updated.count
                log("TasksStore: Auto-refresh updated \(updated.count) incomplete tasks (API had \(response.items.count))")
            }
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
                if mergedTasks != completedTasks {
                    completedTasks = mergedTasks
                    hasMoreCompletedTasks = mergedTasks.count >= pageSize
                    completedOffset = mergedTasks.count
                }
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
                if newDeleted != deletedTasks {
                    deletedTasks = newDeleted
                    hasMoreDeletedTasks = response.hasMore
                    deletedOffset = newDeleted.count
                }
            } catch {
                logError("TasksStore: Auto-refresh deleted tasks failed", error: error)
            }
        }
    }

    // MARK: - Load Tasks

    /// Load incomplete tasks if not already loaded (call this on app launch)
    func loadTasksIfNeeded() async {
        guard !hasLoadedIncomplete else { return }
        await loadIncompleteTasks()
        // Also load deleted tasks in background so the filter count is ready
        if !hasLoadedDeleted {
            await loadDeletedTasks()
        }
    }

    /// Legacy method - loads incomplete tasks
    func loadTasks() async {
        await loadIncompleteTasks()
        // Also load deleted tasks so the "Removed by AI" filter count is ready
        if !hasLoadedDeleted {
            await loadDeletedTasks()
        }
        // Kick off one-time full sync in background (populates SQLite with all tasks)
        // Then retry pushing any locally-created tasks that failed to sync
        Task {
            await performFullSyncIfNeeded()
            await migrateAITasksToStagedIfNeeded()
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

    /// Load incomplete tasks (To Do) using local-first pattern
    /// Load incomplete tasks (To Do) from API
    func loadIncompleteTasks() async {
        guard !isLoadingIncomplete else { return }

        isLoadingIncomplete = true
        error = nil
        incompleteOffset = 0

        // Fetch from API and sync to local cache
        do {
            let response = try await APIClient.shared.getActionItems(
                limit: pageSize,
                offset: 0,
                completed: false
            )
            hasLoadedIncomplete = true
            log("TasksStore: Fetched \(response.items.count) incomplete tasks from API")

            // Sync API data to cache, use API response as source of truth
            do {
                try await ActionItemStorage.shared.syncTaskActionItems(response.items)
            } catch {
                logError("TasksStore: Failed to sync incomplete tasks to local cache", error: error)
            }

            incompleteTasks = response.items
            incompleteOffset = response.items.count
            hasMoreIncompleteTasks = response.hasMore
            log("TasksStore: Showing \(response.items.count) incomplete tasks")
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
        let syncKey = "tasksFullSyncCompleted_v3_\(userId)"

        guard !UserDefaults.standard.bool(forKey: syncKey) else {
            log("TasksStore: Full sync already completed for user \(userId)")
            return
        }

        log("TasksStore: Starting full sync for user \(userId)")

        var totalSynced = 0
        let batchSize = 500

        do {
            // Sync all incomplete tasks (start at 0 — initial load uses a date filter so it's a different dataset)
            var offset = 0
            while true {
                let response = try await APIClient.shared.getActionItems(
                    limit: batchSize,
                    offset: offset,
                    completed: false
                )
                if response.items.isEmpty { break }
                try await ActionItemStorage.shared.syncTaskActionItems(response.items)
                totalSynced += response.items.count
                offset += response.items.count
                log("TasksStore: Full sync progress - \(totalSynced) tasks synced (incomplete)")
                if response.items.count < batchSize { break }
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

            // Sync all deleted tasks
            offset = 0
            while true {
                let response = try await APIClient.shared.getActionItems(
                    limit: batchSize,
                    offset: offset,
                    deleted: true
                )
                if response.items.isEmpty { break }
                try await ActionItemStorage.shared.syncTaskActionItems(response.items)
                totalSynced += response.items.count
                offset += response.items.count
                log("TasksStore: Full sync progress - \(totalSynced) tasks synced (deleted)")
                if response.items.count < batchSize { break }
            }

            UserDefaults.standard.set(true, forKey: syncKey)
            log("TasksStore: Full sync completed - \(totalSynced) tasks synced total")

            // Backfill due dates on backend for tasks that have none
            await backfillDueDatesOnBackendIfNeeded(userId: userId)
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

    /// One-time backfill: patch backend tasks that have no dueAt.
    /// Sets dueAt to end of the day the task was created.
    private func backfillDueDatesOnBackendIfNeeded(userId: String) async {
        let backfillKey = "tasksDueDateBackfill_v1_\(userId)"
        guard !UserDefaults.standard.bool(forKey: backfillKey) else { return }

        log("TasksStore: Starting due date backfill for backend tasks")
        var patchedCount = 0

        do {
            // Fetch all incomplete tasks from local cache that have no dueAt
            let tasksWithoutDueDate = try await ActionItemStorage.shared.getLocalActionItems(
                limit: 500,
                completed: false
            ).filter { $0.dueAt == nil }

            for task in tasksWithoutDueDate {
                // Set dueAt to end of the day the task was created (11:59 PM local)
                let calendar = Calendar.current
                let endOfCreatedDay = calendar.date(bySettingHour: 23, minute: 59, second: 0, of: task.createdAt)
                    ?? task.createdAt

                do {
                    _ = try await APIClient.shared.updateActionItem(
                        id: task.id,
                        dueAt: endOfCreatedDay
                    )
                    patchedCount += 1
                } catch {
                    logError("TasksStore: Failed to backfill dueAt for task \(task.id)", error: error)
                }
            }

            UserDefaults.standard.set(true, forKey: backfillKey)
            log("TasksStore: Due date backfill complete - patched \(patchedCount) tasks")
        } catch {
            logError("TasksStore: Due date backfill failed", error: error)
        }
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

    // MARK: - Task Actions

    func toggleTask(_ task: TaskActionItem) async {
        do {
            let updated = try await APIClient.shared.updateActionItem(
                id: task.id,
                completed: !task.completed
            )

            // Sync to local SQLite cache so auto-refresh doesn't revert the change
            try await ActionItemStorage.shared.syncTaskActionItems([updated])

            // Move task between lists based on new completion status
            if updated.completed {
                // Was incomplete, now completed - move to completed list
                incompleteTasks.removeAll { $0.id == task.id }
                completedTasks.insert(updated, at: 0)

                // Compact relevance scores to fill the gap
                if let score = task.relevanceScore {
                    try await ActionItemStorage.shared.compactScoresAfterRemoval(removedScore: score)
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
                // Was completed, now incomplete - move to incomplete list
                completedTasks.removeAll { $0.id == task.id }
                incompleteTasks.insert(updated, at: 0)
            }
        } catch {
            self.error = error.localizedDescription
            logError("TasksStore: Failed to toggle task", error: error)
        }
    }

    func createTask(description: String, dueAt: Date?, priority: String?, tags: [String]? = nil) async {
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
                metadata: metadata
            )

            // Sync to local SQLite cache
            try await ActionItemStorage.shared.syncTaskActionItems([created])

            // New tasks are incomplete, add to incomplete list
            incompleteTasks.insert(created, at: 0)
        } catch {
            self.error = error.localizedDescription
            logError("TasksStore: Failed to create task", error: error)
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

        // Soft-delete on backend in background
        do {
            _ = try await APIClient.shared.softDeleteActionItem(id: task.id, deletedBy: "user")
        } catch {
            logError("TasksStore: Failed to soft-delete task on backend (local delete preserved)", error: error)
        }
    }

    func updateTask(_ task: TaskActionItem, description: String? = nil, dueAt: Date? = nil, priority: String? = nil) async {
        do {
            // Track manual edits: if description is changed, mark as manually edited
            var metadata: [String: Any]? = nil
            if description != nil {
                metadata = ["manually_edited": true]
                // Preserve existing tags in metadata
                if !task.tags.isEmpty {
                    metadata?["tags"] = task.tags
                }
            }

            let updated = try await APIClient.shared.updateActionItem(
                id: task.id,
                description: description,
                dueAt: dueAt,
                priority: priority,
                metadata: metadata
            )

            // Sync to local SQLite cache so auto-refresh doesn't revert the change
            try await ActionItemStorage.shared.syncTaskActionItems([updated])

            // Update in appropriate list
            if task.completed {
                if let index = completedTasks.firstIndex(where: { $0.id == task.id }) {
                    completedTasks[index] = updated
                }
            } else {
                if let index = incompleteTasks.firstIndex(where: { $0.id == task.id }) {
                    incompleteTasks[index] = updated
                }
            }
        } catch {
            self.error = error.localizedDescription
            logError("TasksStore: Failed to update task", error: error)
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

        // Soft-delete on backend in background
        for id in ids {
            do {
                _ = try await APIClient.shared.softDeleteActionItem(id: id, deletedBy: "user")
            } catch {
                logError("TasksStore: Failed to soft-delete task \(id) on backend (local delete preserved)", error: error)
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
