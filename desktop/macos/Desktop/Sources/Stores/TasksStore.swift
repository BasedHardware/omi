import Combine
import OmiSupport
import SwiftUI

/// Sendable carrier for `[String: Any]` task metadata that must cross an actor
/// boundary into `APIClient` / `ActionItemStorage`. The wrapped dictionary is
/// built on the main actor and only read (never mutated) by the receiving
/// actor, so the unchecked Sendable conformance is sound.
struct ActionItemMetadataBox: @unchecked Sendable {
  let value: [String: Any]?
  init(_ value: [String: Any]?) { self.value = value }
}

/// Shared store for all tasks - single source of truth
/// Both Dashboard and Tasks tab observe this store
///
/// Tasks are loaded separately for incomplete vs completed to minimize memory usage.
/// By default, only recent (7 days) incomplete tasks are loaded.
@MainActor
class TasksStore: ObservableObject {
  static let shared = TasksStore()

  struct DashboardTaskSnapshot {
    let overdue: [TaskActionItem]
    let today: [TaskActionItem]
    let noDueDate: [TaskActionItem]
  }

  typealias DashboardTaskLoader = () async throws -> DashboardTaskSnapshot

  struct ToggleOperationOverrides {
    let updateLocal: (_ completed: Bool, _ ownerID: String) async throws -> TaskActionItem
    let refreshDashboard: (_ ownerID: String) async -> Void
    let updateRemote: (_ completed: Bool, _ ownerID: String) async throws -> TaskActionItem
    let syncRemote: (_ task: TaskActionItem, _ ownerID: String) async throws -> Void
    let rollbackLocal: () async throws -> Void
  }

  /// Legacy surfaces deliberately preserve a local edit while offline; the
  /// cohort-only inline task controls roll a rejected mutation back instead.
  enum TaskUpdateRemoteFailureBehavior: Equatable, Sendable {
    case preserveLocalEdit
    case rollbackForChatFirst
  }

  enum TaskUpdateOutcome: Equatable, Sendable {
    case updated
    case preservedLocalAfterRemoteFailure
    case rolledBackAfterRemoteFailure
    case rollbackFailed
    case localWriteFailed
    case ownerChanged
  }

  struct TaskUpdateOperationOverrides {
    let updateLocal: (_ ownerID: String) async throws -> TaskActionItem
    let updateRemote: (_ ownerID: String) async throws -> TaskActionItem
    let syncRemote: (_ task: TaskActionItem, _ ownerID: String) async throws -> Void
    let rollbackLocal: () async throws -> Void
  }

  /// Controllable seams for owner-bound reads and writes. Production callers
  /// use the defaults; tests suspend individual operations to prove that an
  /// owner change fences every later cache/UI/defaults publication.
  struct OwnerBoundOperations {
    struct ActionItemsPage {
      let items: [TaskActionItem]
      let hasMore: Bool
    }

    var fetchPage:
      ((_ completed: Bool, _ offset: Int, _ limit: Int, _ ownerID: String) async throws -> ActionItemsPage)?
    var fetchAllTaskIds: ((_ ownerID: String) async throws -> [String])?
    var fetchTaskDetail: ((_ id: String, _ ownerID: String) async throws -> TaskActionItem?)?
    var reconcileVisibility: ((_ items: [TaskActionItem], _ ownerID: String) async throws -> Int)?
    var fetchDeletedPage: ((_ offset: Int, _ limit: Int, _ ownerID: String) async throws -> ActionItemsPage)?
    var syncPage:
      ((_ items: [TaskActionItem], _ overrideStagedDeletions: Bool, _ ownerID: String) async throws -> Void)?
    var hardDeleteAbsent: ((_ ids: Set<String>, _ ownerID: String) async throws -> Int)?
    var markAbsent: ((_ ids: Set<String>, _ ownerID: String) async throws -> Void)?
    var purgeDeleted: ((_ ownerID: String) async throws -> Int)?
    var loadIncomplete: ((_ ownerID: String) async throws -> [TaskActionItem])?
    var loadCompleted: ((_ ownerID: String) async throws -> [TaskActionItem])?
    var loadDeleted: ((_ ownerID: String) async throws -> [TaskActionItem])?
    var refreshDashboard: ((_ ownerID: String) async -> Void)?
    var migrateAI: ((_ ownerID: String) async throws -> Void)?
    var migrateConversation: ((_ ownerID: String) async throws -> Void)?
    var backfillRelevance: ((_ ownerID: String) async throws -> Int)?

    init(
      fetchPage: (
        (_ completed: Bool, _ offset: Int, _ limit: Int, _ ownerID: String) async throws -> ActionItemsPage
      )? = nil,
      fetchAllTaskIds: ((_ ownerID: String) async throws -> [String])? = nil,
      fetchTaskDetail: ((_ id: String, _ ownerID: String) async throws -> TaskActionItem?)? = nil,
      reconcileVisibility: ((_ items: [TaskActionItem], _ ownerID: String) async throws -> Int)? = nil,
      fetchDeletedPage: ((_ offset: Int, _ limit: Int, _ ownerID: String) async throws -> ActionItemsPage)? = nil,
      syncPage: (
        (_ items: [TaskActionItem], _ overrideStagedDeletions: Bool, _ ownerID: String) async throws -> Void
      )? = nil,
      hardDeleteAbsent: ((_ ids: Set<String>, _ ownerID: String) async throws -> Int)? = nil,
      markAbsent: ((_ ids: Set<String>, _ ownerID: String) async throws -> Void)? = nil,
      purgeDeleted: ((_ ownerID: String) async throws -> Int)? = nil,
      loadIncomplete: ((_ ownerID: String) async throws -> [TaskActionItem])? = nil,
      loadCompleted: ((_ ownerID: String) async throws -> [TaskActionItem])? = nil,
      loadDeleted: ((_ ownerID: String) async throws -> [TaskActionItem])? = nil,
      refreshDashboard: ((_ ownerID: String) async -> Void)? = nil,
      migrateAI: ((_ ownerID: String) async throws -> Void)? = nil,
      migrateConversation: ((_ ownerID: String) async throws -> Void)? = nil,
      backfillRelevance: ((_ ownerID: String) async throws -> Int)? = nil
    ) {
      self.fetchPage = fetchPage
      self.fetchAllTaskIds = fetchAllTaskIds
      self.fetchTaskDetail = fetchTaskDetail
      self.reconcileVisibility = reconcileVisibility
      self.fetchDeletedPage = fetchDeletedPage
      self.syncPage = syncPage
      self.hardDeleteAbsent = hardDeleteAbsent
      self.markAbsent = markAbsent
      self.purgeDeleted = purgeDeleted
      self.loadIncomplete = loadIncomplete
      self.loadCompleted = loadCompleted
      self.loadDeleted = loadDeleted
      self.refreshDashboard = refreshDashboard
      self.migrateAI = migrateAI
      self.migrateConversation = migrateConversation
      self.backfillRelevance = backfillRelevance
    }
  }

  private struct OwnerOperationLease: Equatable, Sendable {
    let authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
    let generation: UInt64

    var ownerID: String { authorizationSnapshot.ownerID }
  }

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
  @Published private(set) var incompleteError: String?
  @Published private(set) var completedError: String?

  /// Counter bumped at the top of `refreshTasksIfNeeded()`, before any of the
  /// early-exit guards. Lets `TasksStoreObserverTests` prove that posting
  /// `didBecomeActive` / `.refreshAllData` actually reaches the refresh method
  /// — if the observer rewire regresses (wrong notification name, dropped
  /// subscription), the counter stays flat and the test fails.
  /// Deliberately **not** `@Published` — publishing on every activation/Cmd+R
  /// refresh would emit `objectWillChange` and invalidate SwiftUI views
  /// observing `TasksStore`, which is a pure production cost for a value
  /// nothing drives UI from.
  private(set) var refreshInvocations: Int = 0

  // Legacy compatibility - combines both lists
  var tasks: [TaskActionItem] {
    incompleteTasks + completedTasks
  }

  var isLoading: Bool {
    isLoadingIncomplete || isLoadingCompleted || isLoadingDeleted
  }

  var hasLoadedIncompleteTasks: Bool { hasLoadedIncomplete }
  var hasLoadedCompletedTasks: Bool { hasLoadedCompleted }

  func resetSessionState() {
    ownerOperationGeneration &+= 1
    for task in startupMaintenanceTasks {
      task.cancel()
    }
    startupMaintenanceTasks.removeAll()
    activeMigrationLease = nil
    activeRetryLease = nil
    incompleteTasks = []
    completedTasks = []
    deletedTasks = []
    overdueTasks = []
    todaysTasks = []
    tasksWithoutDueDate = []
    isLoadingIncomplete = false
    isLoadingCompleted = false
    isLoadingDeleted = false
    isLoadingMore = false
    hasMoreIncompleteTasks = true
    hasMoreCompletedTasks = true
    hasMoreDeletedTasks = true
    error = nil
    incompleteError = nil
    completedError = nil
    incompleteOffset = 0
    completedOffset = 0
    deletedOffset = 0
    hasLoadedIncomplete = false
    hasLoadedCompleted = false
    hasLoadedDeleted = false
    hasScheduledStartupMaintenance = false
    lastReconciliationDate = nil
  }

  // MARK: - Private State

  private var incompleteOffset = 0
  private var completedOffset = 0
  private var deletedOffset = 0
  private let pageSize = 100  // Reduced from 1000 for better performance

  /// Backend cap on `limit` for `GET /v1/action-items` (`le=500`). A request
  /// above this returns HTTP 422 and the whole refresh fails, so any computed
  /// reload limit must be clamped to it.
  static let apiPageLimitCap = 500

  /// Clamp a computed page limit to the range the backend accepts (1...500).
  static func clampedApiPageLimit(_ requested: Int) -> Int {
    min(max(requested, 1), apiPageLimitCap)
  }

  /// The two limits an auto-refresh needs. `api` is clamped to the backend cap
  /// (an unclamped >500 request 422s). `local` is the full loaded count and
  /// drives the local-cache reload + hasMore: it must NOT be clamped, or a user
  /// who has paginated past 500 tasks would have every row beyond 500 dropped by
  /// `mergeWithoutAdding` on every refresh, collapsing the list back to 500.
  static func refreshLimits(pageSize: Int, loadedCount: Int) -> (api: Int, local: Int) {
    let local = max(pageSize, loadedCount)
    return (api: clampedApiPageLimit(local), local: local)
  }
  private var hasLoadedIncomplete = false
  private var hasLoadedCompleted = false
  private var hasLoadedDeleted = false
  private(set) var hasScheduledStartupMaintenance = false
  /// Whether we're currently showing all tasks (no date filter) or just recent
  private var cancellables = Set<AnyCancellable>()
  private var ownerOperationGeneration: UInt64 = 0
  private var startupMaintenanceTasks: [Task<Void, Never>] = []
  private var activeMigrationLease: OwnerOperationLease?
  private var activeRetryLease: OwnerOperationLease?

  /// Timestamp of last full reconciliation (paginated API check for absent tasks)
  private var lastReconciliationDate: Date?

  /// Whether the tasks page (or dashboard) is currently visible.
  /// Auto-refresh only runs when active to avoid unnecessary API calls.
  var isActive = false {
    didSet {
      if isActive && !oldValue && hasLoadedIncomplete {
        refreshInvocations += 1
        guard let lease = captureOwnerLease() else { return }
        // Refresh immediately when becoming active
        Task { @MainActor [weak self] in
          guard let self, self.isCurrent(lease) else { return }
          await self.refreshTasksIfNeeded(lease: lease)
          guard self.isCurrent(lease) else { return }
          await self.reconcileWithAPIIfNeeded(lease: lease)
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
  func loadDashboardTasks(
    expectedOwnerID: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil,
    loader: DashboardTaskLoader? = nil
  ) async {
    guard
      let lease = captureOwnerLease(
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot
      )
    else { return }
    let calendar = Calendar.current
    let startOfToday = calendar.startOfDay(for: Date())
    let endOfToday = calendar.date(byAdding: .day, value: 1, to: startOfToday)!
    let sevenDaysAgo = calendar.date(byAdding: .day, value: -7, to: Date()) ?? Date()

    do {
      let snapshot: DashboardTaskSnapshot
      if let loader {
        snapshot = try await loader()
      } else {
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
        let (overdue, today, noDueDate) = try await (
          overdueResult,
          todayResult,
          noDueDateResult
        )
        snapshot = DashboardTaskSnapshot(
          overdue: overdue,
          today: today,
          noDueDate: noDueDate
        )
      }
      guard isCurrent(lease) else { return }
      let sortedOverdue = snapshot.overdue.sorted(by: Self.sortByDueDateThenSource)
      let sortedToday = snapshot.today.sorted(by: Self.sortByDueDateThenSource)
      let sortedNoDueDate = snapshot.noDueDate.sorted(by: Self.sortByDueDateThenSource)
      // Only update @Published properties if values actually changed to avoid unnecessary objectWillChange
      if overdueTasks != sortedOverdue { overdueTasks = sortedOverdue }
      if todaysTasks != sortedToday { todaysTasks = sortedToday }
      if tasksWithoutDueDate != sortedNoDueDate { tasksWithoutDueDate = sortedNoDueDate }
      log(
        "TasksStore: Dashboard loaded from SQLite - overdue: \(snapshot.overdue.count), today: \(snapshot.today.count), noDeadline: \(snapshot.noDueDate.count)"
      )
    } catch {
      if isCurrent(lease) {
        logError("TasksStore: Failed to load dashboard tasks from SQLite", error: error)
      }
    }
  }

  func refreshDashboardTasksFromServer(
    expectedOwnerID: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async {
    guard
      let lease = captureOwnerLease(
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot
      )
    else { return }
    await DashboardTaskRefreshService.refresh(
      store: self,
      expectedOwnerID: lease.ownerID,
      authorizationSnapshot: lease.authorizationSnapshot
    )
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
    // Refresh tasks when app becomes active
    NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)
      .sink { [weak self] _ in
        MainActor.assumeIsolated {
          guard let self else { return }
          self.refreshInvocations += 1
          guard let lease = self.captureOwnerLease() else { return }
          Task { @MainActor [weak self] in
            await self?.refreshTasksIfNeeded(lease: lease)
          }
        }
      }
      .store(in: &cancellables)

    // Cmd+R: refresh tasks on demand
    NotificationCenter.default.publisher(for: .refreshAllData)
      .sink { [weak self] _ in
        MainActor.assumeIsolated {
          guard let self else { return }
          self.refreshInvocations += 1
          guard let lease = self.captureOwnerLease() else { return }
          Task { @MainActor [weak self] in
            await self?.refreshTasksIfNeeded(lease: lease)
          }
        }
      }
      .store(in: &cancellables)

    NotificationCenter.default.publisher(for: .runtimeOwnerDidChange)
      .sink { [weak self] _ in
        MainActor.assumeIsolated {
          self?.resetSessionState()
        }
      }
      .store(in: &cancellables)

  }

  /// Refresh tasks if already loaded (for auto-refresh)
  /// Uses local-first pattern: sync API to cache, then reload from cache
  /// Merges changes in-place to avoid wholesale array replacement (which kills SwiftUI gestures)
  func refreshTasksIfNeeded(
    operations: OwnerBoundOperations = OwnerBoundOperations()
  ) async {
    refreshInvocations += 1
    guard let lease = captureOwnerLease() else { return }
    await refreshTasksIfNeeded(lease: lease, operations: operations)
  }

  private func refreshTasksIfNeeded(
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations = OwnerBoundOperations()
  ) async {
    guard isCurrent(lease) else { return }
    // Skip if not signed in
    guard AuthService.shared.isSignedIn else { return }
    // Skip if page is not visible
    guard isActive else { return }

    // Skip if currently loading
    guard !isLoadingIncomplete, !isLoadingCompleted, !isLoadingDeleted, !isLoadingMore else { return }

    // Dashboard-only users may never open the full Tasks page, so the
    // incomplete task list may not be hydrated. Still keep dashboard task
    // slices fresh on app activation / Cmd+R using the scoped dashboard
    // refresh path instead of requiring full Tasks-page hydration first.
    guard hasLoadedIncomplete else {
      await refreshDashboard(lease: lease, operations: operations)
      return
    }

    // Silently sync and reload incomplete tasks (local-first, like Memories)
    do {
      // The backend caps `limit` at 500, so the API page must be clamped (an
      // unclamped >500 request 422s). But the LOCAL cache load below and the
      // hasMore signal must use the full loaded count: reusing the clamped API
      // limit for the local reload would drop every task past row 500 from a
      // user who has paginated beyond it (mergeWithoutAdding removes current
      // rows absent from its source), collapsing a 600+ list back to 500.
      let limits = Self.refreshLimits(pageSize: pageSize, loadedCount: incompleteTasks.count)
      let apiLimit = limits.api
      let localReloadLimit = limits.local
      let response = try await fetchPage(
        completed: false,
        offset: 0,
        limit: apiLimit,
        lease: lease,
        operations: operations
      )
      guard isCurrent(lease) else { return }

      // Sync API results to local cache
      try await syncPage(
        response.items,
        lease: lease,
        operations: operations
      )
      guard isCurrent(lease) else { return }

      // Reconcile: if we got the full set, hard-delete local tasks absent from API
      // (completed/deleted on mobile). Safe: only deletes synced records.
      // An empty page is reconciled only after the IDs endpoint confirms the
      // account truly has zero incomplete tasks (degraded-backend guard).
      if response.items.count < apiLimit {
        if response.items.isEmpty {
          if !incompleteTasks.isEmpty {
            _ = await reconcileConfirmedEmptyCloud(lease: lease, operations: operations)
            guard isCurrent(lease) else { return }
          }
        } else {
          let apiIds = Set(response.items.map { $0.id })
          let reconciled = try await hardDeleteAbsent(
            apiIds,
            lease: lease,
            operations: operations
          )
          guard isCurrent(lease) else { return }
          if reconciled > 0 {
            log("TasksStore: Reconciled: hard-deleted \(reconciled) absent tasks during auto-refresh")
          }
        }
      }

      // Reload from local cache (respects local changes like completions/deletions).
      // Uses the unclamped local limit so a user paginated past 500 keeps every
      // loaded row instead of being truncated by the backend's API cap.
      let mergedTasks = try await loadCachedTasks(
        scope: .incomplete,
        limit: localReloadLimit,
        offset: 0,
        lease: lease,
        operations: operations
      )
      guard isCurrent(lease) else { return }

      // Merge without triggering @Published unless something actually changed
      let merged = Self.mergeWithoutAdding(source: mergedTasks, current: incompleteTasks)
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
        log(
          "RENDER: Auto-refresh diff: \(incompleteTasks.count)->\(merged.count) items, removed=\(removed.count), added=\(added.count), updated=\(updated.count) properties changed"
        )
        if !removed.isEmpty { log("RENDER: Removed IDs: \(removed.prefix(5).joined(separator: ", "))") }
        if !updated.isEmpty {
          log("RENDER: Updated IDs: \(updated.prefix(3).map { $0.id.prefix(8) }.joined(separator: ", "))")
        }

        incompleteTasks = merged
        incompleteOffset = merged.count
        log("TasksStore: Auto-refresh updated incomplete tasks (\(merged.count) items)")
      } else {
        log("RENDER: Auto-refresh: no changes detected, skipping update")
      }
      let newHasMore = mergedTasks.count >= localReloadLimit
      if hasMoreIncompleteTasks != newHasMore { hasMoreIncompleteTasks = newHasMore }
      await refreshDashboardCache(lease: lease, operations: operations)
    } catch {
      // Benign sign-out race: the isSignedIn guard above passed, but the
      // token was cleared by the time the request ran. Expected, not a bug
      // — log quietly (breadcrumb only) instead of flooding Sentry.
      guard isCurrent(lease) else { return }
      if case AuthError.notSignedIn = error {
        log("TasksStore: Auto-refresh skipped: signed out mid-cycle")
        return
      }
      // Silently ignore errors during auto-refresh
      logError("TasksStore: Auto-refresh failed", error: error)
    }

    // Also refresh completed if loaded
    if hasLoadedCompleted, isCurrent(lease) {
      do {
        let response = try await fetchPage(
          completed: true,
          offset: 0,
          limit: pageSize,
          lease: lease,
          operations: operations
        )
        guard isCurrent(lease) else { return }

        // Sync to cache
        try await syncPage(response.items, lease: lease, operations: operations)
        guard isCurrent(lease) else { return }

        // Reload from cache
        let mergedTasks = try await loadCachedTasks(
          scope: .completed,
          limit: pageSize,
          offset: 0,
          lease: lease,
          operations: operations
        )
        guard isCurrent(lease) else { return }
        let merged = Self.mergeWithoutAdding(source: mergedTasks, current: completedTasks)
        if merged != completedTasks {
          completedTasks = merged
          completedOffset = merged.count
        }
        let newHasMore = mergedTasks.count >= pageSize
        if hasMoreCompletedTasks != newHasMore { hasMoreCompletedTasks = newHasMore }
      } catch {
        guard isCurrent(lease) else { return }
        // Benign sign-out race (see incomplete-tasks catch above).
        if case AuthError.notSignedIn = error {
          log("TasksStore: Auto-refresh skipped: signed out mid-cycle")
          return
        }
        logError("TasksStore: Auto-refresh completed tasks failed", error: error)
      }
    }

    // Also refresh deleted if loaded
    if hasLoadedDeleted, isCurrent(lease) {
      do {
        let response = try await fetchDeletedPage(
          offset: 0,
          limit: pageSize,
          lease: lease,
          operations: operations
        )
        guard isCurrent(lease) else { return }

        // Sync to cache
        try await syncPage(response.items, lease: lease, operations: operations)
        guard isCurrent(lease) else { return }

        // Reload from cache
        let newDeleted = try await loadCachedTasks(
          scope: .deleted,
          limit: pageSize,
          offset: 0,
          lease: lease,
          operations: operations
        )
        guard isCurrent(lease) else { return }
        let merged = Self.mergeWithoutAdding(source: newDeleted, current: deletedTasks)
        if merged != deletedTasks {
          deletedTasks = merged
          deletedOffset = merged.count
        }
        if hasMoreDeletedTasks != response.hasMore { hasMoreDeletedTasks = response.hasMore }
      } catch {
        guard isCurrent(lease) else { return }
        // Benign sign-out race (see incomplete-tasks catch above).
        if case AuthError.notSignedIn = error {
          log("TasksStore: Auto-refresh skipped: signed out mid-cycle")
          return
        }
        logError("TasksStore: Auto-refresh deleted tasks failed", error: error)
      }
    }
  }

  /// Full reconciliation: paginate ALL incomplete task IDs from API, then hard-delete
  /// local tasks not present. Throttled to run at most every 5 minutes.
  /// Catches cases where the user has more tasks than one page of auto-refresh can cover.
  func reconcileWithAPIIfNeeded(
    operations: OwnerBoundOperations = OwnerBoundOperations()
  ) async {
    guard let lease = captureOwnerLease() else { return }
    await reconcileWithAPIIfNeeded(lease: lease, operations: operations)
  }

  private func reconcileWithAPIIfNeeded(
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations = OwnerBoundOperations()
  ) async {
    guard isCurrent(lease) else { return }
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
        guard isCurrent(lease) else { return }
        let response = try await fetchPage(
          completed: false,
          offset: offset,
          limit: batchSize,
          lease: lease,
          operations: operations
        )
        guard isCurrent(lease) else { return }
        allApiIds.formUnion(response.items.map { $0.id })
        offset += response.items.count
        if response.items.count < batchSize { break }
      }

      let deleted: Int
      if allApiIds.isEmpty {
        // Zero incomplete tasks in the cloud — confirm through the IDs
        // endpoint before wiping so stale local tasks converge to empty
        // without trusting a single unverified empty response.
        if incompleteTasks.isEmpty {
          // Local cache already matches the empty cloud state.
          lastReconciliationDate = Date()
          return
        }
        guard
          let confirmed = await reconcileConfirmedEmptyCloud(
            lease: lease,
            operations: operations
          )
        else { return }
        deleted = confirmed
      } else {
        deleted = try await hardDeleteAbsent(
          allApiIds,
          lease: lease,
          operations: operations
        )
        guard isCurrent(lease) else { return }
        lastReconciliationDate = Date()
      }

      if deleted > 0 {
        log("TasksStore: Full reconciliation: hard-deleted \(deleted) absent tasks")
        // Reload from cache to reflect deletions in UI
        let reloadLimit = max(pageSize, incompleteTasks.count)
        let refreshed = try await loadCachedTasks(
          scope: .incomplete,
          limit: reloadLimit,
          offset: 0,
          lease: lease,
          operations: operations
        )
        guard isCurrent(lease) else { return }
        if refreshed != incompleteTasks {
          incompleteTasks = refreshed
          incompleteOffset = refreshed.count
        }
        await refreshDashboardCache(lease: lease, operations: operations)
      }
    } catch {
      if isCurrent(lease) {
        logError("TasksStore: Full reconciliation failed", error: error)
      }
    }
  }

  /// Build a merged result from source and current: update changed items, remove gone ones.
  /// Does NOT add new items — new tasks only appear on explicit load (initial load, tab switch).
  /// Returns a new array only if different from current (caller compares with == before assigning
  /// to @Published property, preventing unnecessary objectWillChange notifications).
  static func mergeWithoutAdding(source: [TaskActionItem], current: [TaskActionItem]) -> [TaskActionItem] {
    // The source list can contain duplicate ids (local sync/reconciliation races),
    // so build the lookup with last-write-wins.
    let sourceById = Dictionary(lastWriteWins: source.map { ($0.id, $0) })
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
  func reloadFromLocalCache(
    expectedOwnerID: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async {
    guard
      let lease = captureOwnerLease(
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot
      )
    else { return }
    guard hasLoadedIncomplete else { return }

    do {
      let reloadLimit = max(pageSize, incompleteTasks.count + 10)
      let cachedTasks = try await ActionItemStorage.shared.getLocalActionItems(
        limit: reloadLimit,
        offset: 0,
        completed: false
      )
      guard isCurrent(lease) else { return }
      if cachedTasks != incompleteTasks {
        incompleteTasks = cachedTasks
        incompleteOffset = cachedTasks.count
        log("TasksStore: Reloaded \(cachedTasks.count) incomplete tasks from local cache (external change)")
      }
    } catch {
      if isCurrent(lease) {
        logError("TasksStore: Failed to reload incomplete tasks from cache", error: error)
      }
    }

    // Also reload completed if already loaded
    if hasLoadedCompleted {
      do {
        let cachedCompleted = try await ActionItemStorage.shared.getLocalActionItems(
          limit: pageSize,
          offset: 0,
          completed: true
        )
        guard isCurrent(lease) else { return }
        if cachedCompleted != completedTasks {
          completedTasks = cachedCompleted
          completedOffset = cachedCompleted.count
          log("TasksStore: Reloaded \(cachedCompleted.count) completed tasks from local cache (external change)")
        }
      } catch {
        if isCurrent(lease) {
          logError("TasksStore: Failed to reload completed tasks from cache", error: error)
        }
      }
    }
  }

  // MARK: - Load Tasks

  /// Load incomplete tasks if not already loaded (call this on app launch)
  func loadTasksIfNeeded(expectedOwnerID: String? = nil) async {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else { return }
    if !hasLoadedIncomplete {
      await loadIncompleteTasks(expectedOwnerID: lease.ownerID)
      guard isCurrent(lease) else { return }
      await loadDashboardTasks(
        expectedOwnerID: lease.ownerID,
        authorizationSnapshot: lease.authorizationSnapshot
      )
      guard isCurrent(lease) else { return }
      // Also load deleted tasks in background so the filter count is ready
      if !hasLoadedDeleted {
        await loadDeletedTasks(expectedOwnerID: lease.ownerID)
        guard isCurrent(lease) else { return }
      }
    }
    scheduleStartupMaintenanceIfNeeded(expectedOwnerID: lease.ownerID)
  }

  /// Legacy method - loads incomplete tasks
  func loadTasks(expectedOwnerID: String? = nil) async {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else { return }
    await loadIncompleteTasks(expectedOwnerID: lease.ownerID)
    guard isCurrent(lease) else { return }
    await loadDashboardTasks(
      expectedOwnerID: lease.ownerID,
      authorizationSnapshot: lease.authorizationSnapshot
    )
    guard isCurrent(lease) else { return }
    // Also load deleted tasks so the "Removed by AI" filter count is ready
    if !hasLoadedDeleted {
      await loadDeletedTasks(expectedOwnerID: lease.ownerID)
      guard isCurrent(lease) else { return }
    }
    scheduleStartupMaintenanceIfNeeded(expectedOwnerID: lease.ownerID)
    // Note: no startup task promotion. Promotion happens on the natural
    // cadence — when the user completes/deletes a task, or via the
    // 5-minute safety-net timer. Bursting up to 5 promotions on every
    // launch felt like spam.
  }

  @discardableResult
  func scheduleStartupMaintenanceIfNeeded(
    expectedOwnerID: String? = nil,
    fullSyncAndRetry: (@Sendable (_ ownerID: String) async -> Void)? = nil,
    relevanceBackfill: (@Sendable (_ ownerID: String) async -> Void)? = nil,
    operations: OwnerBoundOperations = OwnerBoundOperations()
  ) -> [Task<Void, Never>] {
    guard !hasScheduledStartupMaintenance else { return [] }
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else { return [] }
    hasScheduledStartupMaintenance = true

    // Kick off one-time full sync in background (populates SQLite with all tasks)
    // Then retry pushing any locally-created tasks that failed to sync.
    let fullSyncTask = Task { @MainActor [weak self] in
      guard let self, self.isCurrent(lease) else { return }
      if let fullSyncAndRetry {
        await fullSyncAndRetry(lease.ownerID)
      } else {
        await self.performFullSyncIfNeeded(lease: lease, operations: operations)
        guard self.isCurrent(lease) else { return }
        await self.migrateAITasksToStagedIfNeeded(lease: lease, operations: operations)
        guard self.isCurrent(lease) else { return }
        await self.migrateConversationItemsToStagedIfNeeded(lease: lease, operations: operations)
        guard self.isCurrent(lease) else { return }
        await self.retryUnsyncedItems(
          expectedOwnerID: lease.ownerID,
          authorizationSnapshot: lease.authorizationSnapshot
        )
      }
    }
    startupMaintenanceTasks.append(fullSyncTask)

    // Backfill relevance scores for unscored tasks (independent of full sync).
    let relevanceTask = Task { @MainActor [weak self] in
      guard let self, self.isCurrent(lease) else { return }
      if let relevanceBackfill {
        await relevanceBackfill(lease.ownerID)
      } else {
        await self.backfillRelevanceScoresIfNeeded(
          lease: lease,
          operations: operations
        )
      }
    }
    startupMaintenanceTasks.append(relevanceTask)
    return [fullSyncTask, relevanceTask]
  }

  private func captureOwnerLease(
    expectedOwnerID: String? = nil,
    authorizationSnapshot suppliedAuthorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) -> OwnerOperationLease? {
    if let suppliedAuthorizationSnapshot {
      if let expectedOwnerID {
        let normalizedExpectedOwnerID =
          expectedOwnerID
          .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalizedExpectedOwnerID.isEmpty,
          normalizedExpectedOwnerID == suppliedAuthorizationSnapshot.ownerID
        else {
          return nil
        }
      }
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(suppliedAuthorizationSnapshot) else {
        return nil
      }
      return OwnerOperationLease(
        authorizationSnapshot: suppliedAuthorizationSnapshot,
        generation: ownerOperationGeneration
      )
    }
    guard let ownerID = Self.captureOperationOwner(expectedOwnerID),
      let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(
        expectedOwnerID: ownerID
      )
    else { return nil }
    return OwnerOperationLease(
      authorizationSnapshot: authorizationSnapshot,
      generation: ownerOperationGeneration
    )
  }

  private func isCurrent(_ lease: OwnerOperationLease) -> Bool {
    lease.generation == ownerOperationGeneration
      && RuntimeOwnerIdentity.isAuthorizationCurrent(lease.authorizationSnapshot)
      && !Task.isCancelled
  }

  private enum CachedTaskScope {
    case incomplete
    case completed
    case deleted
  }

  private func fetchPage(
    completed: Bool,
    offset: Int,
    limit: Int,
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async throws -> OwnerBoundOperations.ActionItemsPage {
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    if let fetchPage = operations.fetchPage {
      return try await fetchPage(completed, offset, limit, lease.ownerID)
    }
    let response = try await APIClient.shared.getActionItems(
      limit: limit,
      offset: offset,
      completed: completed,
      expectedOwnerId: lease.ownerID,
      authorizationSnapshot: lease.authorizationSnapshot
    )
    return .init(items: response.items, hasMore: response.hasMore)
  }

  private func fetchDeletedPage(
    offset: Int,
    limit: Int,
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async throws -> OwnerBoundOperations.ActionItemsPage {
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    if let fetchDeletedPage = operations.fetchDeletedPage {
      return try await fetchDeletedPage(offset, limit, lease.ownerID)
    }
    let response = try await APIClient.shared.getActionItems(
      limit: limit,
      offset: offset,
      deleted: true,
      expectedOwnerId: lease.ownerID,
      authorizationSnapshot: lease.authorizationSnapshot
    )
    return .init(items: response.items, hasMore: response.hasMore)
  }

  private func syncPage(
    _ items: [TaskActionItem],
    overrideStagedDeletions: Bool = false,
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async throws {
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    if let syncPage = operations.syncPage {
      try await syncPage(items, overrideStagedDeletions, lease.ownerID)
    } else {
      try await ActionItemStorage.shared.syncTaskActionItems(
        items,
        overrideStagedDeletions: overrideStagedDeletions,
        authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
      )
    }
  }

  private func hardDeleteAbsent(
    _ ids: Set<String>,
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations,
    confirmedEmpty: Bool = false
  ) async throws -> Int {
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    if let hardDeleteAbsent = operations.hardDeleteAbsent {
      return try await hardDeleteAbsent(ids, lease.ownerID)
    }
    return try await ActionItemStorage.shared.hardDeleteAbsentTasks(
      apiIds: ids,
      authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot),
      confirmedEmpty: confirmedEmpty
    )
  }

  /// The cloud returned zero incomplete tasks. A legitimately-empty account must
  /// still converge (tasks completed/deleted on other devices have to disappear
  /// here too), but a bogus empty page from a degraded backend must never wipe
  /// the local cache on its own say-so. Instead of trusting the empty page,
  /// reconcile against the independent ID census (GET /v1/action-items/ids):
  ///   - rows whose documents are absent from the census are proven gone and
  ///     hard-deleted;
  ///   - rows whose documents still exist are resolved with authoritative
  ///     per-document reads (completed/deleted flips), never blind deletion;
  ///   - an empty census itself proves the account has no task documents at
  ///     all, which authorizes the storage layer's confirmed-empty wipe.
  /// Returns the number of local rows changed (deleted + visibility flips), or
  /// nil when the census fetch failed (reconciliation skipped, fail closed).
  private func reconcileConfirmedEmptyCloud(
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async -> Int? {
    guard isCurrent(lease) else { return nil }
    do {
      let censusIds: [String]
      if let fetchAllTaskIds = operations.fetchAllTaskIds {
        censusIds = try await fetchAllTaskIds(lease.ownerID)
      } else {
        censusIds = try await APIClient.shared.getActionItemIds(
          expectedOwnerId: lease.ownerID,
          authorizationSnapshot: lease.authorizationSnapshot
        )
      }
      guard isCurrent(lease) else { return nil }

      let census = Set(censusIds)
      var changed: Int
      if census.isEmpty {
        changed = try await hardDeleteAbsent(
          [],
          lease: lease,
          operations: operations,
          confirmedEmpty: true
        )
      } else {
        changed = try await hardDeleteAbsent(census, lease: lease, operations: operations)
        guard isCurrent(lease) else { return nil }
        changed += await resolveCensusPresentStaleRows(
          census: census,
          lease: lease,
          operations: operations
        )
      }
      guard isCurrent(lease) else { return nil }
      lastReconciliationDate = Date()
      if changed > 0 {
        log("TasksStore: Reconciled empty cloud to-do state: \(changed) stale local tasks resolved")
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "task_reconcile",
          from: "incomplete_page",
          to: "id_census",
          reason: "local_heal",
          outcome: .recovered,
          extra: ["resolved_rows": changed]
        )
      }
      return changed
    } catch {
      if isCurrent(lease) {
        log("TasksStore: Empty-cloud reconciliation skipped — census fetch failed: \(error.localizedDescription)")
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "task_reconcile",
          from: "incomplete_page",
          to: "none",
          reason: "other",
          outcome: .degraded
        )
      }
      return nil
    }
  }

  /// Local incomplete rows whose documents still exist in the census cannot be
  /// deleted on the empty page's word — read each document and apply its
  /// authoritative completed/deleted state instead. Loops until a full cache
  /// read shows no unattempted census-present rows, so the whole stale set is
  /// resolved in one reconcile pass. Terminates because every iteration either
  /// attempts new rows or widens the read window: rows that resolve leave the
  /// incomplete cache, and rows that do not (still incomplete in the cloud, or
  /// unreadable) are remembered in `attempted` and stay visible by design.
  private func resolveCensusPresentStaleRows(
    census: Set<String>,
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async -> Int {
    var flippedTotal = 0
    var unresolvedRows = 0
    var attempted = Set<String>()
    var readLimit = pageSize
    defer {
      if unresolvedRows > 0 {
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "task_reconcile",
          from: "id_census",
          to: "none",
          reason: "other",
          outcome: .degraded,
          extra: ["unresolved_rows": unresolvedRows]
        )
      }
    }
    do {
      while true {
        guard isCurrent(lease) else { return flippedTotal }
        let rows = try await loadCachedTasks(
          scope: .incomplete,
          limit: readLimit,
          offset: 0,
          lease: lease,
          operations: operations
        )
        let candidates = rows.filter { census.contains($0.id) && !attempted.contains($0.id) }
        if candidates.isEmpty {
          // A short read means the whole remaining cache was visible and
          // holds nothing left to resolve. A full read may hide deeper
          // rows behind stable ones — widen and look again.
          if rows.count < readLimit { break }
          readLimit += pageSize
          continue
        }

        var fetched: [TaskActionItem] = []
        for row in candidates {
          guard isCurrent(lease) else { return flippedTotal }
          attempted.insert(row.id)
          do {
            let item: TaskActionItem?
            if let fetchTaskDetail = operations.fetchTaskDetail {
              item = try await fetchTaskDetail(row.id, lease.ownerID)
            } else {
              item = try await APIClient.shared.getActionItem(
                id: row.id,
                expectedOwnerId: lease.ownerID,
                authorizationSnapshot: lease.authorizationSnapshot
              )
            }
            if let item { fetched.append(item) }
          } catch {
            // One unreadable document must not abort the rest; it stays
            // visible and is retried on the next reconcile pass.
            unresolvedRows += 1
            log("TasksStore: Skipping stale-row resolution for one task: \(error.localizedDescription)")
          }
        }
        guard isCurrent(lease) else { return flippedTotal }
        guard !fetched.isEmpty else { continue }

        if let reconcileVisibility = operations.reconcileVisibility {
          flippedTotal += try await reconcileVisibility(fetched, lease.ownerID)
        } else {
          flippedTotal += try await ActionItemStorage.shared.reconcileDashboardVisibilityFields(
            fetched,
            authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
          )
        }
      }
      return flippedTotal
    } catch {
      if isCurrent(lease) {
        unresolvedRows += 1
        log("TasksStore: Stale-row resolution skipped: \(error.localizedDescription)")
      }
      return flippedTotal
    }
  }

  private func loadCachedTasks(
    scope: CachedTaskScope,
    limit: Int,
    offset: Int,
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async throws -> [TaskActionItem] {
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    if offset == 0 {
      switch scope {
      case .incomplete:
        if let loadIncomplete = operations.loadIncomplete {
          return try await loadIncomplete(lease.ownerID)
        }
      case .completed:
        if let loadCompleted = operations.loadCompleted {
          return try await loadCompleted(lease.ownerID)
        }
      case .deleted:
        if let loadDeleted = operations.loadDeleted {
          return try await loadDeleted(lease.ownerID)
        }
      }
    }

    switch scope {
    case .incomplete:
      return try await ActionItemStorage.shared.getLocalActionItems(
        limit: limit,
        offset: offset,
        completed: false
      )
    case .completed:
      return try await ActionItemStorage.shared.getLocalActionItems(
        limit: limit,
        offset: offset,
        completed: true
      )
    case .deleted:
      let items = try await ActionItemStorage.shared.getLocalActionItems(
        limit: limit,
        offset: offset,
        completed: nil,
        includeDeleted: true
      )
      return items.filter { $0.deleted == true }
    }
  }

  private func refreshDashboard(
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async {
    guard isCurrent(lease) else { return }
    if let refreshDashboard = operations.refreshDashboard {
      await refreshDashboard(lease.ownerID)
    } else {
      await DashboardTaskRefreshService.refresh(
        store: self,
        expectedOwnerID: lease.ownerID,
        authorizationSnapshot: lease.authorizationSnapshot
      )
    }
  }

  private func refreshDashboardCache(
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async {
    guard isCurrent(lease) else { return }
    if let refreshDashboard = operations.refreshDashboard {
      await refreshDashboard(lease.ownerID)
    } else {
      await loadDashboardTasks(
        expectedOwnerID: lease.ownerID,
        authorizationSnapshot: lease.authorizationSnapshot
      )
    }
  }

  /// Load incomplete tasks (To Do) using local-first pattern (like Memories)
  /// Step 1: Show cached data instantly. Step 2: Sync API to cache, reload from cache.
  func loadIncompleteTasks(
    expectedOwnerID: String? = nil,
    operations: OwnerBoundOperations = OwnerBoundOperations()
  ) async {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else { return }
    guard !isLoadingIncomplete else { return }

    isLoadingIncomplete = true
    error = nil
    incompleteError = nil
    incompleteOffset = 0

    // Step 1: Load from local cache first for instant display
    do {
      let cachedTasks = try await loadCachedTasks(
        scope: .incomplete,
        limit: pageSize,
        offset: 0,
        lease: lease,
        operations: operations
      )
      guard isCurrent(lease) else { return }
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
      let response: OwnerBoundOperations.ActionItemsPage
      if let fetchPage = operations.fetchPage {
        response = try await fetchPage(false, 0, pageSize, lease.ownerID)
      } else {
        let page = try await APIClient.shared.getActionItems(
          limit: pageSize,
          offset: 0,
          completed: false,
          expectedOwnerId: lease.ownerID,
          authorizationSnapshot: lease.authorizationSnapshot
        )
        response = .init(items: page.items, hasMore: page.hasMore)
      }
      guard isCurrent(lease) else { return }
      hasLoadedIncomplete = true
      log("TasksStore: Fetched \(response.items.count) incomplete tasks from API")

      // Sync API data to local cache
      do {
        if let syncPage = operations.syncPage {
          try await syncPage(response.items, false, lease.ownerID)
        } else {
          try await ActionItemStorage.shared.syncTaskActionItems(
            response.items,
            authorization: Self.localMutationAuthorization(
              snapshot: lease.authorizationSnapshot
            )
          )
        }
        guard isCurrent(lease) else { return }
      } catch {
        if isCurrent(lease) {
          logError("TasksStore: Failed to sync incomplete tasks to local cache", error: error)
        }
      }

      // Reload from cache to get merged data (local changes + API data)
      let mergedTasks = try await loadCachedTasks(
        scope: .incomplete,
        limit: pageSize,
        offset: 0,
        lease: lease,
        operations: operations
      )
      guard isCurrent(lease) else { return }
      incompleteTasks = mergedTasks
      incompleteOffset = mergedTasks.count
      hasMoreIncompleteTasks = mergedTasks.count >= pageSize
      log("TasksStore: Showing \(mergedTasks.count) incomplete tasks from merged local cache")
    } catch {
      if isCurrent(lease) {
        if incompleteTasks.isEmpty {
          self.error = error.localizedDescription
          incompleteError = error.localizedDescription
        }
        logError("TasksStore: Failed to load incomplete tasks from API", error: error)
      }
    }

    guard isCurrent(lease) else { return }
    isLoadingIncomplete = false
    NotificationCenter.default.post(name: .tasksPageDidLoad, object: nil)

    // Force reconciliation on initial load to clean up tasks deleted on other devices.
    // This bypasses the 5-minute throttle since the first load should always reconcile.
    // Awaited inline (not in a detached Task) so loadDashboardTasks() sees clean data.
    if lastReconciliationDate == nil {
      await forceReconcileOnLoad(lease: lease, operations: operations)
    }
  }

  /// Reconcile on initial load: paginate ALL incomplete task IDs from API,
  /// then hard-delete any local tasks that are absent. This catches tasks
  /// deleted on other devices (e.g. mobile) that still exist in local SQLite.
  private func forceReconcileOnLoad(
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async {
    guard isCurrent(lease) else { return }
    let batchSize = 500
    var allApiIds = Set<String>()
    var offset = 0

    do {
      while true {
        guard isCurrent(lease) else { return }
        let response: OwnerBoundOperations.ActionItemsPage
        if let fetchPage = operations.fetchPage {
          response = try await fetchPage(false, offset, batchSize, lease.ownerID)
        } else {
          let page = try await APIClient.shared.getActionItems(
            limit: batchSize,
            offset: offset,
            completed: false,
            expectedOwnerId: lease.ownerID,
            authorizationSnapshot: lease.authorizationSnapshot
          )
          response = .init(items: page.items, hasMore: page.hasMore)
        }
        guard isCurrent(lease) else { return }
        allApiIds.formUnion(response.items.map { $0.id })
        offset += response.items.count
        if response.items.count < batchSize { break }
      }

      let deleted: Int
      if allApiIds.isEmpty {
        // Zero incomplete tasks in the cloud: either the account is truly
        // empty (everything completed/deleted on another device) or the
        // backend served a bogus empty page. Confirm before wiping so the
        // local list converges to empty instead of showing stale tasks
        // forever, without trusting a single unverified empty response.
        if incompleteTasks.isEmpty {
          // Local cache already matches the empty cloud state.
          lastReconciliationDate = Date()
          return
        }
        guard
          let confirmed = await reconcileConfirmedEmptyCloud(
            lease: lease,
            operations: operations
          )
        else { return }
        deleted = confirmed
      } else {
        deleted = try await hardDeleteAbsent(
          allApiIds,
          lease: lease,
          operations: operations
        )
        guard isCurrent(lease) else { return }
        lastReconciliationDate = Date()
      }

      if deleted > 0 {
        log("TasksStore: Reconciled on load: hard-deleted \(deleted) absent tasks")
        let reloadLimit = max(pageSize, incompleteTasks.count)
        let refreshed = try await loadCachedTasks(
          scope: .incomplete,
          limit: reloadLimit,
          offset: 0,
          lease: lease,
          operations: operations
        )
        guard isCurrent(lease) else { return }
        if refreshed != incompleteTasks {
          incompleteTasks = refreshed
          incompleteOffset = refreshed.count
        }
        await refreshDashboardCache(lease: lease, operations: operations)
      } else {
        log("TasksStore: Reconciled on load: all local tasks match API")
      }
    } catch {
      if isCurrent(lease) {
        logError("TasksStore: Force reconciliation on load failed", error: error)
      }
    }
  }

  /// Load completed tasks (Done) - called when user views Done tab
  /// Uses local-first pattern
  func loadCompletedTasks(
    expectedOwnerID: String? = nil,
    operations: OwnerBoundOperations = OwnerBoundOperations()
  ) async {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else { return }
    guard !isLoadingCompleted else { return }

    isLoadingCompleted = true
    error = nil
    completedError = nil
    completedOffset = 0

    // Step 1: Load from local cache first
    do {
      let cachedTasks = try await loadCachedTasks(
        scope: .completed,
        limit: pageSize,
        offset: 0,
        lease: lease,
        operations: operations
      )
      guard isCurrent(lease) else { return }
      if !cachedTasks.isEmpty {
        completedTasks = cachedTasks
        completedOffset = cachedTasks.count
        hasMoreCompletedTasks = cachedTasks.count >= pageSize
        isLoadingCompleted = false
        log("TasksStore: Loaded \(cachedTasks.count) completed tasks from local cache")
      }
    } catch {
      if isCurrent(lease) {
        log("TasksStore: Local cache unavailable for completed tasks")
      }
    }

    // Step 2: Fetch from API and sync
    do {
      let response = try await fetchPage(
        completed: true,
        offset: 0,
        limit: pageSize,
        lease: lease,
        operations: operations
      )
      guard isCurrent(lease) else { return }
      hasLoadedCompleted = true
      log("TasksStore: Fetched \(response.items.count) completed tasks from API")

      // Step 3: Sync and reload from cache
      do {
        try await syncPage(response.items, lease: lease, operations: operations)
        guard isCurrent(lease) else { return }

        let mergedTasks = try await loadCachedTasks(
          scope: .completed,
          limit: pageSize,
          offset: 0,
          lease: lease,
          operations: operations
        )
        guard isCurrent(lease) else { return }
        completedTasks = mergedTasks
        completedOffset = mergedTasks.count
        hasMoreCompletedTasks = mergedTasks.count >= pageSize
        log("TasksStore: Showing \(mergedTasks.count) completed tasks from merged local cache")
      } catch {
        guard isCurrent(lease) else { return }
        logError("TasksStore: Failed to sync/reload completed tasks", error: error)
        completedTasks = response.items
        completedOffset = response.items.count
        hasMoreCompletedTasks = response.hasMore
      }
    } catch {
      guard isCurrent(lease) else { return }
      if completedTasks.isEmpty {
        self.error = error.localizedDescription
        completedError = error.localizedDescription
      }
      logError("TasksStore: Failed to load completed tasks from API", error: error)
    }

    guard isCurrent(lease) else { return }
    isLoadingCompleted = false
    NotificationCenter.default.post(name: .tasksPageDidLoad, object: nil)
  }

  /// Load deleted tasks (Removed by AI) - called when user views the filter
  /// Uses local-first pattern
  func loadDeletedTasks(
    expectedOwnerID: String? = nil,
    operations: OwnerBoundOperations = OwnerBoundOperations()
  ) async {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else { return }
    guard !isLoadingDeleted else { return }

    isLoadingDeleted = true
    error = nil
    deletedOffset = 0

    // Step 1: Load from local cache first
    do {
      let deleted = try await loadCachedTasks(
        scope: .deleted,
        limit: pageSize,
        offset: 0,
        lease: lease,
        operations: operations
      )
      guard isCurrent(lease) else { return }
      if !deleted.isEmpty {
        deletedTasks = deleted
        deletedOffset = deleted.count
        hasMoreDeletedTasks = deleted.count >= pageSize
        isLoadingDeleted = false
        log("TasksStore: Loaded \(deleted.count) deleted tasks from local cache")
      }
    } catch {
      if isCurrent(lease) {
        log("TasksStore: Local cache unavailable for deleted tasks")
      }
    }

    // Step 2: Fetch from API and sync
    do {
      let response = try await fetchDeletedPage(
        offset: 0,
        limit: pageSize,
        lease: lease,
        operations: operations
      )
      guard isCurrent(lease) else { return }
      hasLoadedDeleted = true
      log("TasksStore: Fetched \(response.items.count) deleted tasks from API")

      // Step 3: Sync and reload from cache
      do {
        try await syncPage(response.items, lease: lease, operations: operations)
        guard isCurrent(lease) else { return }

        let mergedDeleted = try await loadCachedTasks(
          scope: .deleted,
          limit: pageSize,
          offset: 0,
          lease: lease,
          operations: operations
        )
        guard isCurrent(lease) else { return }
        deletedTasks = mergedDeleted
        deletedOffset = mergedDeleted.count
        hasMoreDeletedTasks = response.hasMore
        log("TasksStore: Showing \(mergedDeleted.count) deleted tasks from merged local cache")
      } catch {
        guard isCurrent(lease) else { return }
        logError("TasksStore: Failed to sync/reload deleted tasks", error: error)
        deletedTasks = response.items
        deletedOffset = response.items.count
        hasMoreDeletedTasks = response.hasMore
      }
    } catch {
      guard isCurrent(lease) else { return }
      if deletedTasks.isEmpty {
        self.error = error.localizedDescription
      }
      logError("TasksStore: Failed to load deleted tasks from API", error: error)
    }

    guard isCurrent(lease) else { return }
    isLoadingDeleted = false
    NotificationCenter.default.post(name: .tasksPageDidLoad, object: nil)
  }

  /// One-time background sync that fetches ALL tasks from the API and stores in SQLite.
  /// Ensures filter/search queries have the full dataset. Keyed per user so it runs once per account.
  private func performFullSyncIfNeeded(
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async {
    guard isCurrent(lease) else { return }
    let userId = lease.ownerID
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
        guard isCurrent(lease) else { return }
        let page: OwnerBoundOperations.ActionItemsPage
        if let fetchPage = operations.fetchPage {
          page = try await fetchPage(false, offset, batchSize, lease.ownerID)
        } else {
          let response = try await APIClient.shared.getActionItems(
            limit: batchSize,
            offset: offset,
            completed: false,
            expectedOwnerId: lease.ownerID,
            authorizationSnapshot: lease.authorizationSnapshot
          )
          page = .init(items: response.items, hasMore: response.hasMore)
        }
        guard isCurrent(lease) else { return }
        if page.items.isEmpty { break }
        if let syncPage = operations.syncPage {
          try await syncPage(page.items, true, lease.ownerID)
        } else {
          try await ActionItemStorage.shared.syncTaskActionItems(
            page.items,
            overrideStagedDeletions: true,
            authorization: Self.localMutationAuthorization(
              snapshot: lease.authorizationSnapshot
            )
          )
        }
        guard isCurrent(lease) else { return }
        allIncompleteApiIds.formUnion(page.items.map { $0.id })
        totalSynced += page.items.count
        offset += page.items.count
        log("TasksStore: Full sync progress - \(totalSynced) tasks synced (incomplete)")
        if page.items.count < batchSize { break }
      }

      // Now that we have ALL incomplete API IDs, mark any local tasks
      // not in this set as staged. This is safe because we have the full dataset.
      if !allIncompleteApiIds.isEmpty {
        if let markAbsent = operations.markAbsent {
          try await markAbsent(allIncompleteApiIds, lease.ownerID)
        } else {
          try await ActionItemStorage.shared.markAbsentTasksAsStaged(
            apiIds: allIncompleteApiIds,
            authorization: Self.localMutationAuthorization(
              snapshot: lease.authorizationSnapshot
            )
          )
        }
        guard isCurrent(lease) else { return }
      }

      // Sync all completed tasks
      offset = 0
      while true {
        guard isCurrent(lease) else { return }
        let page: OwnerBoundOperations.ActionItemsPage
        if let fetchPage = operations.fetchPage {
          page = try await fetchPage(true, offset, batchSize, lease.ownerID)
        } else {
          let response = try await APIClient.shared.getActionItems(
            limit: batchSize,
            offset: offset,
            completed: true,
            expectedOwnerId: lease.ownerID,
            authorizationSnapshot: lease.authorizationSnapshot
          )
          page = .init(items: response.items, hasMore: response.hasMore)
        }
        guard isCurrent(lease) else { return }
        if page.items.isEmpty { break }
        if let syncPage = operations.syncPage {
          try await syncPage(page.items, false, lease.ownerID)
        } else {
          try await ActionItemStorage.shared.syncTaskActionItems(
            page.items,
            authorization: Self.localMutationAuthorization(
              snapshot: lease.authorizationSnapshot
            )
          )
        }
        guard isCurrent(lease) else { return }
        totalSynced += page.items.count
        offset += page.items.count
        log("TasksStore: Full sync progress - \(totalSynced) tasks synced (completed)")
        if page.items.count < batchSize { break }
      }

      // Purge any soft-deleted rows from local SQLite (one-time cleanup)
      let purged: Int
      if let purgeDeleted = operations.purgeDeleted {
        purged = try await purgeDeleted(lease.ownerID)
      } else {
        purged = try await ActionItemStorage.shared.purgeAllSoftDeletedItems(
          authorization: Self.localMutationAuthorization(
            snapshot: lease.authorizationSnapshot
          )
        )
      }
      guard isCurrent(lease) else { return }
      if purged > 0 {
        log("TasksStore: Purged \(purged) soft-deleted items from local SQLite")
      }

      guard isCurrent(lease) else { return }
      UserDefaults.standard.set(true, forKey: syncKey)
      log("TasksStore: Full sync completed - \(totalSynced) tasks synced total")

      // Reload incomplete tasks from cache so UI reflects the full dataset
      do {
        let refreshed: [TaskActionItem]
        if let loadIncomplete = operations.loadIncomplete {
          refreshed = try await loadIncomplete(lease.ownerID)
        } else {
          refreshed = try await ActionItemStorage.shared.getLocalActionItems(
            limit: pageSize,
            offset: 0,
            completed: false
          )
        }
        guard isCurrent(lease) else { return }
        incompleteTasks = refreshed
        incompleteOffset = refreshed.count
        hasMoreIncompleteTasks = refreshed.count >= pageSize
        log("TasksStore: Refreshed UI after full sync - \(refreshed.count) incomplete tasks")
        await loadDashboardTasks(
          expectedOwnerID: lease.ownerID,
          authorizationSnapshot: lease.authorizationSnapshot
        )
      } catch {
        if isCurrent(lease) {
          logError("TasksStore: Failed to refresh UI after full sync", error: error)
        }
      }

    } catch {
      if isCurrent(lease) {
        logError("TasksStore: Full sync failed (will retry next launch)", error: error)
      }
    }
  }

  /// One-time migration: tell backend to move excess AI tasks to staged_tasks subcollection.
  /// The SQLite migration handles local data; this handles Firestore.
  /// Sets the flag optimistically before the request to avoid retry loops on timeout.
  private func migrateAITasksToStagedIfNeeded(
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async {
    guard isCurrent(lease) else { return }
    let userId = lease.ownerID
    let migrationKey = "stagedTasksMigrationCompleted_v4_\(userId)"

    guard !UserDefaults.standard.bool(forKey: migrationKey) else {
      log("TasksStore: Staged tasks migration already completed for user \(userId)")
      return
    }

    // Owner+generation scoped: another account never inherits this guard,
    // and owner invalidation clears it synchronously.
    guard activeMigrationLease == nil else {
      log("TasksStore: Staged tasks migration already in progress, skipping")
      return
    }
    activeMigrationLease = lease
    defer {
      if activeMigrationLease == lease { activeMigrationLease = nil }
    }

    // Set flag optimistically — the migration is idempotent and safe to skip on re-run.
    // This prevents infinite retry loops when the backend succeeds but the client times out.
    guard isCurrent(lease) else { return }
    UserDefaults.standard.set(true, forKey: migrationKey)

    log("TasksStore: Starting staged tasks backend migration for user \(userId)")

    do {
      if let migrateAI = operations.migrateAI {
        try await migrateAI(lease.ownerID)
      } else {
        try await APIClient.shared.migrateStagedTasks(
          expectedOwnerId: lease.ownerID,
          authorizationSnapshot: lease.authorizationSnapshot
        )
      }
      if isCurrent(lease) {
        log("TasksStore: Staged tasks backend migration completed")
      }
    } catch {
      if isCurrent(lease) {
        log(
          "TasksStore: Staged tasks backend migration fired (may complete in background): \(error.localizedDescription)"
        )
      }
    }
  }

  /// One-time migration of conversation-extracted action items (no source field) to staged_tasks.
  /// These were created by the old save_action_items path that bypassed the staging pipeline.
  private func migrateConversationItemsToStagedIfNeeded(
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async {
    guard isCurrent(lease) else { return }
    let userId = lease.ownerID
    let migrationKey = "conversationItemsMigrationCompleted_v4_\(userId)"

    guard !UserDefaults.standard.bool(forKey: migrationKey) else { return }

    guard isCurrent(lease) else { return }
    UserDefaults.standard.set(true, forKey: migrationKey)
    log("TasksStore: Starting conversation items migration for user \(userId)")

    do {
      if let migrateConversation = operations.migrateConversation {
        try await migrateConversation(lease.ownerID)
      } else {
        try await APIClient.shared.migrateConversationItemsToStaged(
          expectedOwnerId: lease.ownerID,
          authorizationSnapshot: lease.authorizationSnapshot
        )
      }
      guard isCurrent(lease) else { return }
      log("TasksStore: Conversation items migration completed, resetting full sync to clean up local SQLite")

      // Reset full sync flag so it re-runs and marks migrated items as staged locally
      let syncKey = "tasksFullSyncCompleted_v9_\(userId)"
      UserDefaults.standard.set(false, forKey: syncKey)

      // Run full sync now to clean up local SQLite
      await performFullSyncIfNeeded(lease: lease, operations: operations)
    } catch {
      if isCurrent(lease) {
        log(
          "TasksStore: Conversation items migration fired (may complete in background): \(error.localizedDescription)")
      }
    }
  }

  /// Retry syncing locally-created tasks that failed to push to the backend.
  /// These are records with backendSynced=false and no backendId — the API call
  /// failed during extraction and there was no retry mechanism.
  func retryUnsyncedItems(
    includeRecent: Bool = false,
    expectedOwnerID: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async {
    guard
      let lease = captureOwnerLease(
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot
      )
    else { return }
    let ownerID = lease.ownerID
    guard activeRetryLease == nil else {
      log("TasksStore: Skipping retryUnsyncedItems (already in progress)")
      return
    }
    activeRetryLease = lease
    defer {
      if activeRetryLease == lease { activeRetryLease = nil }
    }

    let items: [ActionItemRecord]
    do {
      items = try await ActionItemStorage.shared.getUnsyncedActionItems(includeRecent: includeRecent)
    } catch {
      if isCurrent(lease) {
        logError("TasksStore: Failed to fetch unsynced items", error: error)
      }
      return
    }
    guard isCurrent(lease) else { return }

    guard !items.isEmpty else { return }
    log("TasksStore: Retrying sync for \(items.count) unsynced items")

    var synced = 0
    for item in items {
      guard isCurrent(lease) else { return }
      guard let localId = item.id else { continue }

      // Re-check: the normal sync path may have synced this item while we were iterating
      if let current = try? await ActionItemStorage.shared.getActionItem(id: localId),
        current.backendSynced || (current.backendId != nil && !current.backendId!.isEmpty)
      {
        continue
      }
      guard isCurrent(lease) else { return }

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
          metadataBox: ActionItemMetadataBox(metadata),
          relevanceScore: item.relevanceScore,
          expectedOwnerId: ownerID,
          authorizationSnapshot: lease.authorizationSnapshot
        )
        guard isCurrent(lease) else { return }
        // createActionItem always posts completed:nil, so a task the user
        // completed while it was still unsynced (offline / failed create) would
        // be recreated on the backend as incomplete and resurrected on the next
        // refresh. Push the completed state with a follow-up update.
        if item.completed {
          _ = try? await APIClient.shared.updateActionItem(
            id: response.id,
            completed: true,
            expectedOwnerId: ownerID,
            authorizationSnapshot: lease.authorizationSnapshot
          )
          guard isCurrent(lease) else { return }
        }
        try await ActionItemStorage.shared.markSynced(
          id: localId,
          backendId: response.id,
          authorization: Self.localMutationAuthorization(
            snapshot: lease.authorizationSnapshot
          )
        )
        guard isCurrent(lease) else { return }
        synced += 1
      } catch {
        // Skip this item, will retry next launch
        continue
      }
    }

    if isCurrent(lease) {
      log("TasksStore: Retry sync completed — \(synced)/\(items.count) items synced")
    }
  }

  /// One-time backfill: assign relevance scores to all unscored active tasks.
  /// Each unscored task gets max+1 sequentially so they appear at the bottom
  /// until the next Gemini rescore properly ranks them.
  private func backfillRelevanceScoresIfNeeded(
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async {
    guard isCurrent(lease) else { return }
    let backfillKey = "tasksRelevanceScoreBackfill_v1_\(lease.ownerID)"
    guard !UserDefaults.standard.bool(forKey: backfillKey) else { return }

    do {
      let count: Int
      if let backfillRelevance = operations.backfillRelevance {
        count = try await backfillRelevance(lease.ownerID)
      } else {
        count = try await ActionItemStorage.shared.backfillUnscoredTasks(
          authorization: Self.localMutationAuthorization(
            snapshot: lease.authorizationSnapshot
          )
        )
      }
      guard isCurrent(lease) else { return }
      UserDefaults.standard.set(true, forKey: backfillKey)
      log("TasksStore: Relevance score backfill complete - scored \(count) tasks")
    } catch {
      if isCurrent(lease) {
        logError("TasksStore: Relevance score backfill failed", error: error)
      }
    }
  }

  /// Load more incomplete tasks (pagination) - local-first
  func loadMoreIncompleteIfNeeded(
    currentTask: TaskActionItem,
    expectedOwnerID: String? = nil,
    operations: OwnerBoundOperations = OwnerBoundOperations()
  ) async {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else { return }
    guard hasMoreIncompleteTasks, !isLoadingMore else { return }

    let thresholdIndex =
      incompleteTasks.index(incompleteTasks.endIndex, offsetBy: -10, limitedBy: incompleteTasks.startIndex)
      ?? incompleteTasks.startIndex
    guard let taskIndex = incompleteTasks.firstIndex(where: { $0.id == currentTask.id }),
      taskIndex >= thresholdIndex
    else {
      return
    }

    isLoadingMore = true

    do {
      let response = try await fetchPage(
        completed: false,
        offset: incompleteOffset,
        limit: pageSize,
        lease: lease,
        operations: operations
      )
      guard isCurrent(lease) else { return }

      // Sync to cache
      try await syncPage(response.items, lease: lease, operations: operations)
      guard isCurrent(lease) else { return }

      incompleteTasks.append(contentsOf: response.items)
      hasMoreIncompleteTasks = response.hasMore
      incompleteOffset += response.items.count
      log("TasksStore: Loaded \(response.items.count) more incomplete tasks from API")
    } catch {
      if isCurrent(lease) {
        logError("TasksStore: Failed to load more incomplete tasks", error: error)
      }
    }

    guard isCurrent(lease) else { return }
    isLoadingMore = false
  }

  /// Load more completed tasks (pagination) - local-first
  func loadMoreCompletedIfNeeded(
    currentTask: TaskActionItem,
    expectedOwnerID: String? = nil,
    operations: OwnerBoundOperations = OwnerBoundOperations()
  ) async {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else { return }
    guard hasMoreCompletedTasks, !isLoadingMore else { return }

    let thresholdIndex =
      completedTasks.index(completedTasks.endIndex, offsetBy: -10, limitedBy: completedTasks.startIndex)
      ?? completedTasks.startIndex
    guard let taskIndex = completedTasks.firstIndex(where: { $0.id == currentTask.id }),
      taskIndex >= thresholdIndex
    else {
      return
    }

    isLoadingMore = true

    // Step 1: Try to load more from local cache first
    do {
      let moreFromCache = try await loadCachedTasks(
        scope: .completed,
        limit: pageSize,
        offset: completedOffset,
        lease: lease,
        operations: operations
      )
      guard isCurrent(lease) else { return }

      if !moreFromCache.isEmpty {
        completedTasks.append(contentsOf: moreFromCache)
        completedOffset += moreFromCache.count
        hasMoreCompletedTasks = moreFromCache.count >= pageSize
        log("TasksStore: Loaded \(moreFromCache.count) more completed tasks from local cache")
        isLoadingMore = false
        return
      }
    } catch {
      if isCurrent(lease) {
        log("TasksStore: Local cache pagination failed for completed tasks")
      }
    }

    // Step 2: If local cache exhausted, fetch from API
    do {
      let response = try await fetchPage(
        completed: true,
        offset: completedOffset,
        limit: pageSize,
        lease: lease,
        operations: operations
      )
      guard isCurrent(lease) else { return }

      // Sync to cache first
      try await syncPage(response.items, lease: lease, operations: operations)
      guard isCurrent(lease) else { return }

      completedTasks.append(contentsOf: response.items)
      hasMoreCompletedTasks = response.hasMore
      completedOffset += response.items.count
      log("TasksStore: Loaded \(response.items.count) more completed tasks from API")
    } catch {
      if isCurrent(lease) {
        logError("TasksStore: Failed to load more completed tasks", error: error)
      }
    }

    guard isCurrent(lease) else { return }
    isLoadingMore = false
  }

  /// Legacy pagination - routes to appropriate method based on task completion status
  func loadMoreIfNeeded(
    currentTask: TaskActionItem,
    expectedOwnerID: String? = nil,
    operations: OwnerBoundOperations = OwnerBoundOperations()
  ) async {
    if currentTask.completed {
      await loadMoreCompletedIfNeeded(
        currentTask: currentTask,
        expectedOwnerID: expectedOwnerID,
        operations: operations
      )
    } else {
      await loadMoreIncompleteIfNeeded(
        currentTask: currentTask,
        expectedOwnerID: expectedOwnerID,
        operations: operations
      )
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

  private nonisolated static func captureOperationOwner(_ expectedOwnerID: String?) -> String? {
    if let expectedOwnerID {
      let explicitOwner =
        expectedOwnerID
        .trimmingCharacters(in: .whitespacesAndNewlines)
      return explicitOwner.isEmpty ? nil : explicitOwner
    }
    return RuntimeOwnerIdentity.currentOwnerId()
  }

  private nonisolated static func localMutationAuthorization(
    snapshot: RuntimeOwnerAuthorizationSnapshot
  ) -> LocalMutationAuthorization {
    LocalMutationAuthorization {
      RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot)
    }
  }

  func toggleTask(
    _ task: TaskActionItem,
    expectedOwnerID: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil,
    beforeLocalMutation: (() async -> Void)? = nil,
    operationOverrides: ToggleOperationOverrides? = nil
  ) async {
    let isDirectUIOperation = expectedOwnerID == nil
    guard
      let lease = captureOwnerLease(
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot
      )
    else { return }
    let ownerID = lease.ownerID
    if let beforeLocalMutation { await beforeLocalMutation() }
    guard isCurrent(lease) else { return }
    let newCompleted = !task.completed

    // 1. Local-first: update SQLite immediately so auto-refresh reads correct state
    let updatedTask: TaskActionItem
    do {
      if let operationOverrides {
        updatedTask = try await operationOverrides.updateLocal(newCompleted, ownerID)
      } else {
        try await ActionItemStorage.shared.updateCompletionStatus(
          backendId: task.id,
          completed: newCompleted,
          authorization: Self.localMutationAuthorization(
            snapshot: lease.authorizationSnapshot
          )
        )
        guard
          let storedTask = try await ActionItemStorage.shared.getLocalActionItem(
            byBackendId: task.id
          )
        else {
          logError("TasksStore: Failed to read back toggled task", error: nil)
          return
        }
        updatedTask = storedTask
      }
    } catch {
      guard isCurrent(lease) else { return }
      logError("TasksStore: Failed to update task locally", error: error)
      self.error = error.localizedDescription
      return
    }
    guard isCurrent(lease) else { return }

    // 2. The local commit (and readback on the production path) completed
    // under the captured owner lease.

    // 3. Track completion analytics
    if newCompleted {
      AnalyticsManager.shared.taskCompleted(source: task.source)
    }

    // 4. Update in-memory arrays immediately (optimistic UI)
    if newCompleted {
      incompleteTasks.removeAll { $0.id == task.id }
      completedTasks.insert(updatedTask, at: 0)

      // Compact relevance scores to fill the gap
      if let score = task.relevanceScore {
        try? await ActionItemStorage.shared.compactScoresAfterRemoval(
          removedScore: score,
          authorization: Self.localMutationAuthorization(
            snapshot: lease.authorizationSnapshot
          )
        )
        guard isCurrent(lease) else { return }
        if isDirectUIOperation {
          Task { @MainActor [weak self] in
            await self?.syncScoresToBackend(lease: lease)
          }
        }
      }

      // Promote a staged task to fill the vacated slot
      if isDirectUIOperation, task.source?.contains("screenshot") == true {
        Task { @MainActor [weak self] in
          guard let self, self.isCurrent(lease) else { return }
          let promoted = await TaskPromotionService.shared.promoteIfNeeded(
            expectedOwnerID: ownerID,
            authorizationSnapshot: lease.authorizationSnapshot
          )
          guard self.isCurrent(lease) else { return }
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

    // 5. Refresh dashboard arrays immediately (SQLite was already updated in step 1)
    guard isCurrent(lease) else { return }
    if let operationOverrides {
      await operationOverrides.refreshDashboard(ownerID)
    } else {
      await loadDashboardTasks(
        expectedOwnerID: ownerID,
        authorizationSnapshot: lease.authorizationSnapshot
      )
    }
    guard isCurrent(lease) else { return }

    // 6. Call API in background, revert on failure. An unsynced local-only
    // task has no backend row — the call would 404 and wrongly revert the
    // local toggle; the pending create-sync will push current row state.
    if operationOverrides == nil, ActionItemTaskIdentity(surfacedId: task.id).isLocalOnly {
      log("TasksStore: Skipped backend toggle for unsynced local task \(task.id)")
      return
    }
    do {
      let apiResult: TaskActionItem
      if let operationOverrides {
        apiResult = try await operationOverrides.updateRemote(newCompleted, ownerID)
      } else {
        apiResult = try await APIClient.shared.updateActionItem(
          id: task.id,
          completed: newCompleted,
          expectedOwnerId: ownerID,
          authorizationSnapshot: lease.authorizationSnapshot
        )
      }
      guard isCurrent(lease) else { return }
      // Sync API result to store server-side timestamps
      if let operationOverrides {
        try await operationOverrides.syncRemote(apiResult, ownerID)
      } else {
        try await ActionItemStorage.shared.syncTaskActionItems(
          [apiResult],
          authorization: Self.localMutationAuthorization(
            snapshot: lease.authorizationSnapshot
          )
        )
      }
      guard isCurrent(lease) else { return }

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
            recurrenceParentId: parentId,
            expectedOwnerId: ownerID,
            authorizationSnapshot: lease.authorizationSnapshot
          ) {
            guard isCurrent(lease) else { return }
            try? await ActionItemStorage.shared.syncTaskActionItems(
              [spawned],
              authorization: Self.localMutationAuthorization(
                snapshot: lease.authorizationSnapshot
              )
            )
            guard isCurrent(lease) else { return }
            incompleteTasks.insert(spawned, at: 0)
            log("TasksStore: Spawned recurring task \(spawned.id) due \(nextDue)")
          }
        }
      }

      if let operationOverrides {
        await operationOverrides.refreshDashboard(ownerID)
      } else {
        await loadDashboardTasks(
          expectedOwnerID: ownerID,
          authorizationSnapshot: lease.authorizationSnapshot
        )
      }
      guard isCurrent(lease) else { return }
    } catch {
      guard isCurrent(lease) else { return }
      logError("TasksStore: Failed to toggle task on backend, reverting", error: error)
      await rollbackToggleAfterBackendFailure(
        task: task,
        attemptedCompleted: newCompleted,
        backendError: error,
        expectedOwnerID: ownerID,
        authorizationSnapshot: lease.authorizationSnapshot,
        rollbackStorage: operationOverrides?.rollbackLocal
      )
    }
  }

  /// Roll back one optimistic toggle only while the initiating owner remains
  /// current. The post-await guard is the authority boundary: storage may
  /// reject after an account transition, and that stale operation must not
  /// rewrite the replacement owner's published arrays or error state.
  func rollbackToggleAfterBackendFailure(
    task: TaskActionItem,
    attemptedCompleted: Bool,
    backendError: Error,
    expectedOwnerID: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil,
    rollbackStorage: (() async throws -> Void)? = nil
  ) async {
    guard
      let lease = captureOwnerLease(
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot
      )
    else { return }
    do {
      if let rollbackStorage {
        try await rollbackStorage()
      } else {
        try await ActionItemStorage.shared.updateCompletionStatus(
          backendId: task.id,
          completed: task.completed,
          authorization: Self.localMutationAuthorization(
            snapshot: lease.authorizationSnapshot
          )
        )
      }
    } catch {
      guard isCurrent(lease) else { return }
      logError("TasksStore: Failed to revert optimistic task toggle", error: error)
    }
    guard isCurrent(lease) else { return }
    if attemptedCompleted {
      completedTasks.removeAll { $0.id == task.id }
      incompleteTasks.insert(task, at: 0)
    } else {
      incompleteTasks.removeAll { $0.id == task.id }
      completedTasks.insert(task, at: 0)
    }
    self.error = backendError.localizedDescription
  }

  @discardableResult
  func createDailyRecurringTask(
    description: String,
    priority: String? = "medium",
    tags: [String]? = nil,
    expectedOwnerID: String? = nil
  ) async -> TaskActionItem? {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else { return nil }
    // Set due date to start of next day if it's past 6 PM, otherwise today
    let calendar = Calendar.current
    let now = Date()
    let hour = calendar.component(.hour, from: now)
    let dueDate: Date

    if hour >= 18 {  // After 6 PM, schedule for next day
      dueDate = calendar.startOfDay(for: calendar.date(byAdding: .day, value: 1, to: now) ?? now)
    } else {
      dueDate = calendar.startOfDay(for: now)
    }

    return await createTask(
      description: description,
      dueAt: dueDate,
      priority: priority,
      tags: (tags ?? []) + ["daily"],
      recurrenceRule: "daily",
      expectedOwnerID: lease.ownerID
    )
  }

  @discardableResult
  func createTask(
    description: String,
    dueAt: Date?,
    priority: String?,
    tags: [String]? = nil,
    recurrenceRule: String? = nil,
    expectedOwnerID: String? = nil
  ) async -> TaskActionItem? {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else { return nil }
    // Local-first: insert into SQLite immediately, then sync to backend in background
    do {
      var metadataJson: String? = nil
      if let tags = tags, !tags.isEmpty {
        let metaDict: [String: Any] = ["tags": tags]
        if let data = try? JSONSerialization.data(withJSONObject: metaDict),
          let str = String(data: data, encoding: .utf8)
        {
          metadataJson = str
        }
      }

      let record = ActionItemRecord(
        description: description,
        source: "manual",
        priority: priority,
        category: tags?.first,
        dueAt: dueAt,
        recurrenceRule: recurrenceRule,
        metadataJson: metadataJson
      )

      let inserted = try await ActionItemStorage.shared.insertLocalActionItem(
        record,
        authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
      )
      guard isCurrent(lease) else { return nil }
      let localTask = inserted.toTaskActionItem()
      let localId = inserted.id!

      // Track task added analytics
      AnalyticsManager.shared.taskAdded()

      // Instant UI update
      incompleteTasks.insert(localTask, at: 0)

      // Sync to backend in background
      Task { @MainActor [weak self] in
        guard let self, self.isCurrent(lease) else { return }
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
            recurrenceRule: recurrenceRule,
            expectedOwnerId: lease.ownerID,
            authorizationSnapshot: lease.authorizationSnapshot
          )
          guard self.isCurrent(lease) else { return }

          try await ActionItemStorage.shared.markSynced(
            id: localId,
            backendId: created.id,
            authorization: Self.localMutationAuthorization(
              snapshot: lease.authorizationSnapshot
            )
          )
          guard self.isCurrent(lease) else { return }

          // Replace local_ entry with real backend-synced task
          if let idx = self.incompleteTasks.firstIndex(where: { $0.id == localTask.id }) {
            self.incompleteTasks[idx] = created
          }
          log("TasksStore: Task synced to backend (local \(localId) → \(created.id))")
        } catch {
          if self.isCurrent(lease) {
            logError("TasksStore: Failed to sync new task to backend (will retry on next launch)", error: error)
          }
        }
      }

      return localTask
    } catch {
      guard isCurrent(lease) else { return nil }
      self.error = error.localizedDescription
      logError("TasksStore: Failed to create task locally", error: error)
      return nil
    }
  }

  func deleteTask(
    _ task: TaskActionItem,
    expectedOwnerID: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil,
    beforeLocalMutation: (() async -> Void)? = nil
  ) async {
    let isDirectUIOperation = expectedOwnerID == nil
    guard
      let lease = captureOwnerLease(
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot
      )
    else { return }
    let ownerID = lease.ownerID
    if let beforeLocalMutation { await beforeLocalMutation() }
    guard isCurrent(lease) else { return }
    // Local-first: soft-delete in SQLite immediately for instant UI update
    do {
      try await ActionItemStorage.shared.deleteActionItemByBackendId(
        task.id,
        deletedBy: "user",
        authorization: Self.localMutationAuthorization(
          snapshot: lease.authorizationSnapshot
        )
      )
    } catch {
      guard isCurrent(lease) else { return }
      logError("TasksStore: Failed to soft-delete task locally", error: error)
      return
    }
    guard isCurrent(lease) else { return }

    // Track deletion analytics
    AnalyticsManager.shared.taskDeleted(source: task.source)

    // Remove from in-memory arrays immediately
    if task.completed {
      completedTasks.removeAll { $0.id == task.id }
    } else {
      incompleteTasks.removeAll { $0.id == task.id }
    }

    // Compact relevance scores to fill the gap
    if let score = task.relevanceScore {
      try? await ActionItemStorage.shared.compactScoresAfterRemoval(
        removedScore: score,
        authorization: Self.localMutationAuthorization(
          snapshot: lease.authorizationSnapshot
        )
      )
      guard isCurrent(lease) else { return }
      if isDirectUIOperation {
        Task { @MainActor [weak self] in
          await self?.syncScoresToBackend(lease: lease)
        }
      }
    }

    // Promote a staged task to fill the vacated slot
    if isDirectUIOperation, task.source?.contains("screenshot") == true {
      Task { @MainActor [weak self] in
        guard let self, self.isCurrent(lease) else { return }
        let promoted = await TaskPromotionService.shared.promoteIfNeeded(
          expectedOwnerID: ownerID,
          authorizationSnapshot: lease.authorizationSnapshot
        )
        guard self.isCurrent(lease) else { return }
        if !promoted.isEmpty {
          self.incompleteTasks.append(contentsOf: promoted)
          log("TasksStore: Inserted \(promoted.count) promoted tasks after deletion")
        }
      }
    }

    // Hard-delete on backend in background. Unsynced local-only tasks have
    // no backend row to delete.
    if ActionItemTaskIdentity(surfacedId: task.id).isLocalOnly {
      log("TasksStore: Skipped backend delete for unsynced local task \(task.id)")
      return
    }
    do {
      try await APIClient.shared.deleteActionItem(
        id: task.id,
        expectedOwnerId: ownerID,
        authorizationSnapshot: lease.authorizationSnapshot
      )
    } catch {
      guard isCurrent(lease) else { return }
      logError("TasksStore: Failed to hard-delete task on backend (local delete preserved)", error: error)
    }
  }

  /// Restore a previously deleted task (for undo)
  /// Re-inserts the task into SQLite and re-creates on backend (since both were hard-deleted).
  func restoreTask(
    _ task: TaskActionItem,
    expectedOwnerID: String? = nil
  ) async {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else { return }

    // A local-only task never had a backend row (deleteTask skipped the backend
    // delete). Restoring it through the backend-recreate path below is wrong on
    // two counts: syncTaskActionItems([task]) would persist the "local_<rowid>"
    // placeholder as a *synced* backendId, and createActionItem would mint a
    // SECOND real backend task — leaving a duplicate/phantom row. Instead
    // re-insert it as an UNSYNCED local row so the pending create-sync pushes it
    // exactly once (carrying completion via retryUnsyncedItems).
    if ActionItemTaskIdentity(surfacedId: task.id).isLocalOnly {
      await restoreLocalOnlyTask(task, lease: lease)
      return
    }

    // 1. Re-insert into SQLite from the in-memory task object
    do {
      try await ActionItemStorage.shared.syncTaskActionItems(
        [task],
        authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
      )
    } catch {
      if isCurrent(lease) {
        logError("TasksStore: Failed to re-insert task locally for undo", error: error)
      }
      return
    }
    guard isCurrent(lease) else { return }

    // 2. Re-insert into the appropriate in-memory array
    if task.completed {
      completedTasks.insert(task, at: 0)
    } else {
      incompleteTasks.insert(task, at: 0)
    }

    // 3. Re-create on backend (hard-delete already removed it). Pass the full
    // field set — restore used to send only description/dueAt/priority, so undo
    // silently dropped source, category, tags, recurrence, goal/workstream, and
    // completion state.
    do {
      var restoreMetadata: [String: Any] = [:]
      if let existing = task.metadata,
        let data = existing.data(using: .utf8),
        let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
      {
        restoreMetadata = json
      }
      if !task.tags.isEmpty {
        restoreMetadata["tags"] = task.tags
      }
      let created = try await APIClient.shared.createActionItem(
        description: task.description,
        dueAt: task.dueAt,
        source: task.source,
        priority: task.priority,
        category: task.category,
        metadataBox: restoreMetadata.isEmpty ? nil : ActionItemMetadataBox(restoreMetadata),
        relevanceScore: task.relevanceScore,
        recurrenceRule: task.recurrenceRule,
        recurrenceParentId: task.recurrenceParentId,
        goalId: task.goalId,
        workstreamId: task.workstreamId,
        expectedOwnerId: lease.ownerID,
        authorizationSnapshot: lease.authorizationSnapshot
      )
      guard isCurrent(lease) else { return }
      // createActionItem cannot set completion; restore the completed state of
      // a task that was done when it was deleted via a follow-up update.
      var resolved = created
      if task.completed, !created.completed {
        resolved =
          (try? await APIClient.shared.updateActionItem(
            id: created.id,
            completed: true,
            expectedOwnerId: lease.ownerID,
            authorizationSnapshot: lease.authorizationSnapshot
          )) ?? created
        guard isCurrent(lease) else { return }
      }
      // Update local record with new backend ID
      try await ActionItemStorage.shared.syncTaskActionItems(
        [resolved],
        authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
      )
      guard isCurrent(lease) else { return }
      log("TasksStore: Restored task via undo (new backend ID: \(resolved.id))")
    } catch {
      if isCurrent(lease) {
        logError("TasksStore: Failed to re-create task on backend (local restore preserved)", error: error)
      }
    }
  }

  /// Build the SQLite record for restoring a local-only task: an UNSYNCED row
  /// (never carry the "local_<rowid>" placeholder as a backendId, or it becomes
  /// a fabricated synced id) with the original rowid preserved so the surfaced
  /// id is stable, and the delete flags cleared.
  static func localOnlyRestoreRecord(from task: TaskActionItem) -> ActionItemRecord {
    var record = ActionItemRecord.from(task)
    record.backendId = nil
    record.backendSynced = false
    record.deleted = false
    record.deletedBy = nil
    if case .localRow(let rowId) = ActionItemTaskIdentity(surfacedId: task.id) {
      record.id = rowId
    } else {
      record.id = nil
    }
    return record
  }

  /// Restore a hard-deleted local-only task as an unsynced local row, preserving
  /// its original rowid so the surfaced "local_<rowid>" id is stable. No backend
  /// recreate: the task never had a backend row, and the pending create-sync
  /// (retryUnsyncedItems) is the single writer that pushes it to the backend.
  private func restoreLocalOnlyTask(_ task: TaskActionItem, lease: OwnerOperationLease) async {
    let record = Self.localOnlyRestoreRecord(from: task)
    do {
      try await ActionItemStorage.shared.insertLocalActionItem(
        record,
        authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
      )
    } catch {
      if isCurrent(lease) {
        logError("TasksStore: Failed to re-insert local-only task for undo", error: error)
      }
      return
    }
    guard isCurrent(lease) else { return }

    if task.completed {
      completedTasks.insert(task, at: 0)
    } else {
      incompleteTasks.insert(task, at: 0)
    }
    log("TasksStore: Restored local-only task via undo (unsynced, id: \(task.id))")
  }

  @discardableResult
  func updateTask(
    _ task: TaskActionItem,
    description: String? = nil,
    dueAt: Date? = nil,
    clearDueAt: Bool = false,
    priority: String? = nil,
    recurrenceRule: String? = nil,
    expectedOwnerID: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil,
    remoteFailureBehavior: TaskUpdateRemoteFailureBehavior = .preserveLocalEdit,
    beforeLocalMutation: (() async -> Void)? = nil,
    operationOverrides: TaskUpdateOperationOverrides? = nil
  ) async -> TaskUpdateOutcome {
    guard let lease = captureOwnerLease(
      expectedOwnerID: expectedOwnerID,
      authorizationSnapshot: authorizationSnapshot
    ) else { return .ownerChanged }
    if let beforeLocalMutation { await beforeLocalMutation() }
    guard isCurrent(lease) else { return .ownerChanged }

    var metadata: [String: Any]? = nil
    if description != nil {
      metadata = ["manually_edited": true]
      if !task.tags.isEmpty { metadata?["tags"] = task.tags }
    }

    do {
      let updatedTask: TaskActionItem?
      if let operationOverrides {
        updatedTask = try await operationOverrides.updateLocal(lease.ownerID)
      } else {
        try await ActionItemStorage.shared.updateActionItemFields(
          backendId: task.id,
          description: description,
          dueAt: dueAt,
          clearDueAt: clearDueAt,
          priority: priority,
          metadataBox: ActionItemMetadataBox(metadata),
          recurrenceRule: recurrenceRule,
          authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
        )
        updatedTask = try await ActionItemStorage.shared.getLocalActionItem(byBackendId: task.id)
      }
      guard isCurrent(lease) else { return .ownerChanged }
      if let updatedTask {
        replaceTaskInMemory(updatedTask, originalTask: task)
      } else if remoteFailureBehavior == .rollbackForChatFirst {
        error = "Could not verify the task update locally."
        return .localWriteFailed
      }
    } catch {
      guard isCurrent(lease) else { return .ownerChanged }
      logError("TasksStore: Failed to update task locally", error: error)
      self.error = error.localizedDescription
      if remoteFailureBehavior == .rollbackForChatFirst { return .localWriteFailed }
    }

    // Unsynced local-only tasks have no backend row; the pending create-sync
    // pushes their current state instead of sending an invalid remote update.
    if operationOverrides == nil, ActionItemTaskIdentity(surfacedId: task.id).isLocalOnly {
      log("TasksStore: Skipped backend update for unsynced local task \(task.id)")
      return .updated
    }
    do {
      let apiResult: TaskActionItem
      if let operationOverrides {
        apiResult = try await operationOverrides.updateRemote(lease.ownerID)
      } else {
        apiResult = try await APIClient.shared.updateActionItem(
          id: task.id,
          description: description,
          dueAt: dueAt,
          clearDueAt: clearDueAt,
          priority: priority,
          metadataBox: ActionItemMetadataBox(metadata),
          recurrenceRule: recurrenceRule,
          expectedOwnerId: lease.ownerID,
          authorizationSnapshot: lease.authorizationSnapshot
        )
      }
      guard isCurrent(lease) else { return .ownerChanged }
      if let operationOverrides {
        try await operationOverrides.syncRemote(apiResult, lease.ownerID)
      } else {
        try await ActionItemStorage.shared.syncTaskActionItems(
          [apiResult],
          authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
        )
      }
      guard isCurrent(lease) else { return .ownerChanged }
      replaceTaskInMemory(apiResult, originalTask: task)
      return .updated
    } catch {
      guard isCurrent(lease) else { return .ownerChanged }
      if remoteFailureBehavior == .preserveLocalEdit {
        self.error = error.localizedDescription
        logError("TasksStore: Failed to update task on backend (local update preserved)", error: error)
        return .preservedLocalAfterRemoteFailure
      }
      let rolledBack = await rollbackTaskUpdateAfterBackendFailure(
        task: task,
        backendError: error,
        expectedOwnerID: lease.ownerID,
        authorizationSnapshot: lease.authorizationSnapshot,
        rollbackStorage: operationOverrides?.rollbackLocal
      )
      if rolledBack { return .rolledBackAfterRemoteFailure }
      return isCurrent(lease) ? .rollbackFailed : .ownerChanged
    }
  }

  @discardableResult
  func rollbackTaskUpdateAfterBackendFailure(
    task: TaskActionItem,
    backendError: Error,
    expectedOwnerID: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil,
    rollbackStorage: (() async throws -> Void)? = nil
  ) async -> Bool {
    guard let lease = captureOwnerLease(
      expectedOwnerID: expectedOwnerID,
      authorizationSnapshot: authorizationSnapshot
    ) else { return false }
    do {
      if let rollbackStorage {
        try await rollbackStorage()
      } else {
        try await ActionItemStorage.shared.syncTaskActionItems(
          [task],
          authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
        )
      }
      guard isCurrent(lease) else { return false }
      replaceTaskInMemory(task, originalTask: task)
      await loadDashboardTasks(
        expectedOwnerID: lease.ownerID,
        authorizationSnapshot: lease.authorizationSnapshot
      )
      guard isCurrent(lease) else { return false }
      error = backendError.localizedDescription
      logError("TasksStore: Failed to update task on backend, reverted Chat-first edit", error: backendError)
      return true
    } catch {
      guard isCurrent(lease) else { return false }
      self.error = error.localizedDescription
      logError("TasksStore: Failed to roll back Chat-first task update", error: error)
      return false
    }
  }

  private func replaceTaskInMemory(_ updatedTask: TaskActionItem, originalTask: TaskActionItem) {
    if originalTask.completed {
      if let index = completedTasks.firstIndex(where: { $0.id == originalTask.id }) {
        completedTasks[index] = updatedTask
      }
    } else if let index = incompleteTasks.firstIndex(where: { $0.id == originalTask.id }) {
      incompleteTasks[index] = updatedTask
    }
  }

  /// Update tags for a task, preserving other metadata keys
  func updateTaskTags(
    _ task: TaskActionItem,
    tags: [String],
    expectedOwnerID: String? = nil
  ) async {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else { return }
    // Build metadata that preserves existing keys and updates tags
    var metaDict: [String: Any] = [:]
    if let existingMeta = task.metadata,
      let data = existingMeta.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    {
      metaDict = json
    }
    metaDict["tags"] = tags

    // 1. Local-first: update SQLite
    do {
      try await ActionItemStorage.shared.updateActionItemFields(
        backendId: task.id,
        metadataBox: ActionItemMetadataBox(metaDict),
        authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
      )
    } catch {
      guard isCurrent(lease) else { return }
      logError("TasksStore: Failed to update task tags locally", error: error)
      self.error = error.localizedDescription
      return
    }

    // 2. Read back and update in-memory
    if let updatedTask = try? await ActionItemStorage.shared.getLocalActionItem(byBackendId: task.id) {
      guard isCurrent(lease) else { return }
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

    // 3. Call API in background. Unsynced local-only tasks have no backend
    // row; the pending create-sync pushes current row state instead.
    if ActionItemTaskIdentity(surfacedId: task.id).isLocalOnly {
      log("TasksStore: Skipped backend tag update for unsynced local task \(task.id)")
      return
    }
    do {
      let apiResult = try await APIClient.shared.updateActionItem(
        id: task.id,
        metadataBox: ActionItemMetadataBox(metaDict),
        expectedOwnerId: lease.ownerID,
        authorizationSnapshot: lease.authorizationSnapshot
      )
      guard isCurrent(lease) else { return }
      try await ActionItemStorage.shared.syncTaskActionItems(
        [apiResult],
        authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
      )
    } catch {
      guard isCurrent(lease) else { return }
      self.error = error.localizedDescription
      logError("TasksStore: Failed to update task tags on backend (local update preserved)", error: error)
    }
  }

  // MARK: - Bulk Actions

  func deleteMultipleTasks(
    ids: [String],
    expectedOwnerID: String? = nil
  ) async {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else { return }
    // Collect relevance scores before removing from memory
    let allTasks = incompleteTasks + completedTasks
    let scores = ids.compactMap { id in allTasks.first(where: { $0.id == id })?.relevanceScore }

    // Local-first: soft-delete all in SQLite and remove from memory immediately
    for id in ids {
      do {
        try await ActionItemStorage.shared.deleteActionItemByBackendId(
          id,
          deletedBy: "user",
          authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
        )
      } catch {
        if isCurrent(lease) {
          logError("TasksStore: Failed to soft-delete task \(id) locally", error: error)
        }
      }
      guard isCurrent(lease) else { return }
      incompleteTasks.removeAll { $0.id == id }
      completedTasks.removeAll { $0.id == id }
    }

    // Compact relevance scores (process highest first so shifts don't affect each other)
    for score in scores.sorted(by: >) {
      try? await ActionItemStorage.shared.compactScoresAfterRemoval(
        removedScore: score,
        authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
      )
      guard isCurrent(lease) else { return }
    }
    if !scores.isEmpty {
      Task { @MainActor [weak self] in
        await self?.syncScoresToBackend(lease: lease)
      }
    }

    // Hard-delete on backend in background (skip unsynced local-only ids)
    for id in ids where !ActionItemTaskIdentity(surfacedId: id).isLocalOnly {
      do {
        try await APIClient.shared.deleteActionItem(
          id: id,
          expectedOwnerId: lease.ownerID,
          authorizationSnapshot: lease.authorizationSnapshot
        )
      } catch {
        if isCurrent(lease) {
          logError("TasksStore: Failed to hard-delete task \(id) on backend (local delete preserved)", error: error)
        }
      }
      guard isCurrent(lease) else { return }
    }
  }

  /// Sync all scored tasks' relevance scores to backend
  private func syncScoresToBackend(expectedOwnerID: String? = nil) async {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else { return }
    await syncScoresToBackend(lease: lease)
  }

  private func syncScoresToBackend(lease: OwnerOperationLease) async {
    guard isCurrent(lease) else { return }
    do {
      let tasks = try await ActionItemStorage.shared.getAllScoredTasks()
      guard isCurrent(lease) else { return }
      let scores = tasks.compactMap { t -> (id: String, score: Int)? in
        guard let s = t.relevanceScore, !t.id.hasPrefix("local_") else { return nil }
        return (id: t.id, score: s)
      }
      guard !scores.isEmpty else { return }
      try await APIClient.shared.batchUpdateScores(
        scores,
        expectedOwnerId: lease.ownerID,
        authorizationSnapshot: lease.authorizationSnapshot
      )
      guard isCurrent(lease) else { return }
    } catch {
      guard isCurrent(lease) else { return }
      logError("TasksStore: Failed to sync scores to backend", error: error)
    }
  }
}
