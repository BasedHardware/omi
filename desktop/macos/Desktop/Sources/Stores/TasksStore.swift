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
  /// universal inline task controls roll a rejected mutation back instead.
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

  enum BulkDeleteOutcome: Equatable, Sendable {
    case deletedEverywhere
    case localFailure(remoteDeletedIDs: Set<String>)
    case remoteFailure(confirmedIDs: Set<String>)
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

    struct IncompleteTaskSurface {
      let datedTasks: [TaskActionItem]
      let noDeadlineTasks: [TaskActionItem]
      let hasMoreNoDeadline: Bool
      /// Number of raw rows consumed from the API's No Deadline partition.
      /// This is intentionally separate from the deduplicated rows presented
      /// by the store.
      let apiConsumedNoDeadlineCount: Int

      init(
        datedTasks: [TaskActionItem],
        noDeadlineTasks: [TaskActionItem],
        hasMoreNoDeadline: Bool,
        apiConsumedNoDeadlineCount: Int? = nil
      ) {
        self.datedTasks = datedTasks
        self.noDeadlineTasks = noDeadlineTasks
        self.hasMoreNoDeadline = hasMoreNoDeadline
        self.apiConsumedNoDeadlineCount = apiConsumedNoDeadlineCount ?? noDeadlineTasks.count
      }

      var activeDatedTasks: [TaskActionItem] {
        TasksStore.activeDatedOnly(datedTasks)
      }

      /// Raw dated-bucket row count for the API's null-due boundary. Includes
      /// retired dated rows the backend still orders before the No Deadline
      /// partition; presentation uses `activeDatedTasks` instead.
      var apiDatedBucketCount: Int {
        TasksStore.apiDatedBucketCount(in: datedTasks)
      }

      var activeNoDeadlineTasks: [TaskActionItem] {
        TasksStore.noDeadlineOnly(noDeadlineTasks)
      }

      var stablePresentationItems: [TaskActionItem] {
        TasksStore.stableIncompleteTaskSurfaceItems(
          datedTasks: activeDatedTasks,
          noDeadlineTasks: activeNoDeadlineTasks
        )
      }
    }

    var fetchPage:
      ((_ completed: Bool, _ offset: Int, _ limit: Int, _ ownerID: String) async throws -> ActionItemsPage)?
    var fetchIncompleteSurface: ((_ ownerID: String) async throws -> IncompleteTaskSurface)?
    var fetchDatedTasks: ((_ ownerID: String) async throws -> [TaskActionItem])?
    var fetchNoDeadlinePage: ((_ offset: Int, _ limit: Int, _ ownerID: String) async throws -> ActionItemsPage)?
    var fetchAllTaskIds: ((_ ownerID: String) async throws -> [String])?
    var fetchSelectionTaskIds: ((_ completed: Bool, _ ownerID: String) async throws -> [String])?
    var fetchTaskDetail: ((_ id: String, _ ownerID: String) async throws -> TaskActionItem?)?
    var loadTaskDetail: ((_ id: String, _ ownerID: String) async throws -> TaskActionItem?)?
    var reconcileVisibility: ((_ items: [TaskActionItem], _ ownerID: String) async throws -> Int)?
    var fetchDeletedPage: ((_ offset: Int, _ limit: Int, _ ownerID: String) async throws -> ActionItemsPage)?
    var syncPage:
      ((_ items: [TaskActionItem], _ overrideStagedDeletions: Bool, _ ownerID: String) async throws -> Void)?
    var hardDeleteAbsent: ((_ ids: Set<String>, _ ownerID: String) async throws -> Int)?
    var markAbsent: ((_ ids: Set<String>, _ ownerID: String) async throws -> Void)?
    var purgeDeleted: ((_ ownerID: String) async throws -> Int)?
    var loadIncomplete: ((_ ownerID: String) async throws -> [TaskActionItem])?
    var loadIncompleteSurface: ((_ ownerID: String) async throws -> IncompleteTaskSurface)?
    var loadIncompleteSurfaceForLimit:
      ((_ ownerID: String, _ noDeadlineLimit: Int) async throws -> IncompleteTaskSurface)?
    var loadCompleted: ((_ ownerID: String) async throws -> [TaskActionItem])?
    var loadDeleted: ((_ ownerID: String) async throws -> [TaskActionItem])?
    var refreshDashboard: ((_ ownerID: String) async -> Void)?
    var restoreLegacyConversationItems:
      ((_ ownerID: String, _ cursor: String?) async throws -> LegacyConversationRecoveryPage)?
    var legacyRecoveryMarkersInvalidated: ((_ ownerID: String) -> Void)?
    var backfillRelevance: ((_ ownerID: String) async throws -> Int)?

    init(
      fetchPage: (
        (_ completed: Bool, _ offset: Int, _ limit: Int, _ ownerID: String) async throws -> ActionItemsPage
      )? = nil,
      fetchIncompleteSurface: ((_ ownerID: String) async throws -> IncompleteTaskSurface)? = nil,
      fetchDatedTasks: ((_ ownerID: String) async throws -> [TaskActionItem])? = nil,
      fetchNoDeadlinePage: (
        (_ offset: Int, _ limit: Int, _ ownerID: String) async throws -> ActionItemsPage
      )? = nil,
      fetchAllTaskIds: ((_ ownerID: String) async throws -> [String])? = nil,
      fetchSelectionTaskIds: ((_ completed: Bool, _ ownerID: String) async throws -> [String])? = nil,
      fetchTaskDetail: ((_ id: String, _ ownerID: String) async throws -> TaskActionItem?)? = nil,
      loadTaskDetail: ((_ id: String, _ ownerID: String) async throws -> TaskActionItem?)? = nil,
      reconcileVisibility: ((_ items: [TaskActionItem], _ ownerID: String) async throws -> Int)? = nil,
      fetchDeletedPage: ((_ offset: Int, _ limit: Int, _ ownerID: String) async throws -> ActionItemsPage)? = nil,
      syncPage: (
        (_ items: [TaskActionItem], _ overrideStagedDeletions: Bool, _ ownerID: String) async throws -> Void
      )? = nil,
      hardDeleteAbsent: ((_ ids: Set<String>, _ ownerID: String) async throws -> Int)? = nil,
      markAbsent: ((_ ids: Set<String>, _ ownerID: String) async throws -> Void)? = nil,
      purgeDeleted: ((_ ownerID: String) async throws -> Int)? = nil,
      loadIncomplete: ((_ ownerID: String) async throws -> [TaskActionItem])? = nil,
      loadIncompleteSurface: ((_ ownerID: String) async throws -> IncompleteTaskSurface)? = nil,
      loadIncompleteSurfaceForLimit:
        ((_ ownerID: String, _ noDeadlineLimit: Int) async throws -> IncompleteTaskSurface)? = nil,
      loadCompleted: ((_ ownerID: String) async throws -> [TaskActionItem])? = nil,
      loadDeleted: ((_ ownerID: String) async throws -> [TaskActionItem])? = nil,
      refreshDashboard: ((_ ownerID: String) async -> Void)? = nil,
      restoreLegacyConversationItems:
        ((_ ownerID: String, _ cursor: String?) async throws -> LegacyConversationRecoveryPage)? = nil,
      legacyRecoveryMarkersInvalidated: ((_ ownerID: String) -> Void)? = nil,
      backfillRelevance: ((_ ownerID: String) async throws -> Int)? = nil
    ) {
      self.fetchPage = fetchPage
      self.fetchIncompleteSurface = fetchIncompleteSurface
      self.fetchDatedTasks = fetchDatedTasks
      self.fetchNoDeadlinePage = fetchNoDeadlinePage
      self.fetchAllTaskIds = fetchAllTaskIds
      self.fetchSelectionTaskIds = fetchSelectionTaskIds
      self.fetchTaskDetail = fetchTaskDetail
      self.loadTaskDetail = loadTaskDetail
      self.reconcileVisibility = reconcileVisibility
      self.fetchDeletedPage = fetchDeletedPage
      self.syncPage = syncPage
      self.hardDeleteAbsent = hardDeleteAbsent
      self.markAbsent = markAbsent
      self.purgeDeleted = purgeDeleted
      self.loadIncomplete = loadIncomplete
      self.loadIncompleteSurface = loadIncompleteSurface
      self.loadIncompleteSurfaceForLimit = loadIncompleteSurfaceForLimit
      self.loadCompleted = loadCompleted
      self.loadDeleted = loadDeleted
      self.refreshDashboard = refreshDashboard
      self.restoreLegacyConversationItems = restoreLegacyConversationItems
      self.legacyRecoveryMarkersInvalidated = legacyRecoveryMarkersInvalidated
      self.backfillRelevance = backfillRelevance
    }
  }

  struct OwnerOperationLease: Equatable, Sendable {
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
    incompleteSurfaceState.reset()
    completedOffset = 0
    deletedOffset = 0
    hasLoadedIncomplete = false
    hasLoadedCompleted = false
    hasLoadedDeleted = false
    hasScheduledStartupMaintenance = false
    lastReconciliationDate = nil
  }

  // MARK: - Private State

  /// Tracks dated vs no-deadline bucket boundaries and API vs presentation
  /// offsets for incomplete-task pagination.
  private var incompleteSurfaceState = IncompleteTaskSurfaceState()

  private struct IncompleteTaskSurfaceState {
    /// Number of raw dated-bucket rows in the current owner-scoped API snapshot.
    /// Includes retired dated rows the backend still orders before No Deadline.
    var datedCount = 0
    /// Raw API row offset at the null-bucket boundary in general list order.
    var datedAPIBoundaryOffset = 0
    /// Offset within the bounded No Deadline bucket (local presentation count).
    var noDeadlinePresentationOffset = 0
    /// Number of raw rows consumed from the API's No Deadline partition.
    var noDeadlineAPIOffset = 0

    mutating func reset() {
      datedCount = 0
      datedAPIBoundaryOffset = 0
      noDeadlinePresentationOffset = 0
      noDeadlineAPIOffset = 0
    }

    mutating func syncFrom(surface: OwnerBoundOperations.IncompleteTaskSurface) {
      datedCount = surface.apiDatedBucketCount
      noDeadlinePresentationOffset = surface.activeNoDeadlineTasks.count
    }

    mutating func syncFrom(
      datedCount: Int,
      noDeadlinePresentationOffset: Int,
      noDeadlineAPIOffset: Int? = nil,
      datedAPIBoundaryOffset: Int? = nil
    ) {
      self.datedCount = datedCount
      self.noDeadlinePresentationOffset = noDeadlinePresentationOffset
      if let apiOffset = noDeadlineAPIOffset {
        self.noDeadlineAPIOffset = apiOffset
      }
      if let boundaryOffset = datedAPIBoundaryOffset {
        self.datedAPIBoundaryOffset = boundaryOffset
      }
    }

    mutating func syncNoDeadlinePresentation(from items: [TaskActionItem]) {
      noDeadlinePresentationOffset = items.filter { $0.dueAt == nil }.count
    }

    mutating func recordInitialFetch(
      surface: OwnerBoundOperations.IncompleteTaskSurface,
      noDeadlineTasks: [TaskActionItem],
      preservedNoDeadlineAPIOffset: Int = 0
    ) {
      datedCount = surface.apiDatedBucketCount
      noDeadlinePresentationOffset = noDeadlineTasks.count
      noDeadlineAPIOffset = max(
        preservedNoDeadlineAPIOffset,
        max(surface.apiConsumedNoDeadlineCount, noDeadlineTasks.count)
      )
    }

    mutating func advanceNoDeadlineAPI(by rawConsumed: Int) {
      noDeadlineAPIOffset += rawConsumed
    }
  }
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

  /// Overdue tasks — every incomplete task due before today, loaded from SQLite.
  /// Together with `todaysTasks` this is the Tasks page's "Today" category.
  @Published var overdueTasks: [TaskActionItem] = []

  /// Today's tasks (due today) — loaded from SQLite
  @Published var todaysTasks: [TaskActionItem] = []

  /// Tasks without a due date — the Tasks page's "No Deadline", loaded from SQLite
  @Published var tasksWithoutDueDate: [TaskActionItem] = []

  /// How many rows a bucket may hold. The spoken answer reads the first 15, but
  /// the bucket's *count* is spoken too ("Overdue (82)"), so the cap has to sit
  /// well clear of a real backlog or the assistant states a number the Tasks
  /// page contradicts — at the old 50 it did. These are small rows, and the
  /// Tasks page already materializes every incomplete dated task.
  static let dashboardBucketLimit = 500

  /// Load dashboard task lists directly from SQLite (avoids pagination issues).
  ///
  /// These three buckets are what the assistant knows about the user's tasks:
  /// the voice `get_tasks` tool, the About-user card, and `SuggestionAssistant`
  /// grounding all read them. They must partition the same rows the Tasks page
  /// shows, or the assistant contradicts the list the user is looking at.
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

    do {
      let snapshot: DashboardTaskSnapshot
      if let loader {
        snapshot = try await loader()
      } else {
        // No lower bound. The Tasks page buckets by `dueAt < startOfTomorrow`
        // alone (`TasksViewModel.categoryFor`), so a task overdue by more than a
        // week is still on the user's list — it was only missing from this one.
        async let overdueResult = ActionItemStorage.shared.getFilteredActionItems(
          limit: Self.dashboardBucketLimit,
          completedStates: [false],
          dueDateBefore: startOfToday
        )
        async let todayResult = ActionItemStorage.shared.getFilteredActionItems(
          limit: Self.dashboardBucketLimit,
          completedStates: [false],
          dueDateAfter: startOfToday,
          dueDateBefore: endOfToday
        )
        // Likewise no creation cutoff: "No Deadline" on the Tasks page is every
        // undated incomplete task, however long it has been sitting there.
        async let noDueDateResult = ActionItemStorage.shared.getFilteredActionItems(
          limit: Self.dashboardBucketLimit,
          completedStates: [false],
          dueDateIsNull: true
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
      // These lanes carry the same rows the Tasks page shows. They used to drop
      // AI-capture sources, on the reasoning that a capture is unreviewed until
      // the user accepts it — but INV-TASK-2 has since made capture
      // suggestion-only (`TaskCaptureModePolicy.usesLegacyStaging` is false for
      // every mode), so a capture never reaches `action_items` at all. It stays
      // a Candidate until an explicit gesture accepts it. Everything in this
      // table is therefore already the user's, and the filter had stopped
      // separating reviewed from unreviewed: it only hid the backlog they can
      // see on Tasks, plus anything they created by voice, since
      // `create_action_item` comes back stamped `conversation`.
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
    await refreshDashboard(lease: lease, operations: .init())
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
      let apiLimit = Self.refreshLimits(pageSize: pageSize, loadedCount: incompleteTasks.count).api
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
      if response.items.count < apiLimit, legacyConversationRecoveryCompleted(for: lease) {
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
      } else if response.items.count < apiLimit {
        log("TasksStore: Auto-refresh skipped destructive reconciliation until legacy task recovery succeeds")
      }

      // Reload the complete dated surface plus the currently displayed bounded
      // No Deadline surface. A mixed first-page read can drop expanded undated
      // rows even when its limit is large enough in aggregate.
      let mergedSurface = try await reloadIncompleteTaskSurface(
        lease: lease,
        operations: operations,
        displayedNoDeadlineCount: incompleteTasks.filter { $0.dueAt == nil }.count
      )
      guard isCurrent(lease) else { return }
      let mergedTasks = surfaceItems(mergedSurface)

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
        incompleteSurfaceState.syncNoDeadlinePresentation(from: merged)
        log("TasksStore: Auto-refresh updated incomplete tasks (\(merged.count) items)")
      } else {
        log("RENDER: Auto-refresh: no changes detected, skipping update")
      }
      let newHasMore = mergedSurface.hasMoreNoDeadline
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
    guard legacyConversationRecoveryCompleted(for: lease) else {
      log("TasksStore: Full reconciliation skipped until legacy task recovery succeeds")
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
        let refreshedSurface = try await reloadIncompleteTaskSurface(
          lease: lease,
          operations: operations,
          displayedNoDeadlineCount: incompleteTasks.filter { $0.dueAt == nil }.count
        )
        guard isCurrent(lease) else { return }
        let refreshed = surfaceItems(refreshedSurface)
        if refreshed != incompleteTasks {
          incompleteTasks = refreshed
          incompleteSurfaceState.syncFrom(surface: refreshedSurface)
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
      let cachedSurface = try await reloadIncompleteTaskSurface(
        lease: lease,
        operations: .init(),
        displayedNoDeadlineCount: incompleteTasks.filter { $0.dueAt == nil }.count
      )
      let cachedTasks = surfaceItems(cachedSurface)
      guard isCurrent(lease) else { return }
      if cachedTasks != incompleteTasks {
        incompleteTasks = cachedTasks
        incompleteSurfaceState.syncFrom(surface: cachedSurface)
        hasMoreIncompleteTasks = cachedSurface.hasMoreNoDeadline
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
      // This must finish before the initial ID census. An older backend returns
      // 404 for the recovery endpoint, in which case reconciling an empty
      // action-items response would otherwise hard-delete the only local copy
      // of migrated tasks.
      let recoveryCompleted = await restoreLegacyConversationItemsIfNeeded(lease: lease, operations: .init())
      guard isCurrent(lease) else { return }
      await loadIncompleteTasks(
        expectedOwnerID: lease.ownerID,
        allowInitialReconciliation: recoveryCompleted
      )
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
    let recoveryCompleted = await restoreLegacyConversationItemsIfNeeded(lease: lease, operations: .init())
    guard isCurrent(lease) else { return }
    await loadIncompleteTasks(
      expectedOwnerID: lease.ownerID,
      allowInitialReconciliation: recoveryCompleted
    )
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
        let recoveryCompleted = await self.restoreLegacyConversationItemsIfNeeded(lease: lease, operations: operations)
        guard self.isCurrent(lease) else { return }
        // `performFullSyncIfNeeded` marks every cache row absent from a
        // nonempty cloud response as staged. Do not let that destructive
        // reconciliation run while a pre-deploy backend still rejects legacy
        // recovery: those cache rows may be the last remaining copy.
        guard recoveryCompleted else { return }
        await self.performFullSyncIfNeeded(lease: lease, operations: operations)
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

  func captureOwnerLease(
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

  func isCurrent(_ lease: OwnerOperationLease) -> Bool {
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

  /// Keep the dated and null-due buckets disjoint even if a concurrent backend
  /// update or a duplicate response races a page boundary.
  nonisolated static func stableIncompleteTaskSurfaceItems(
    datedTasks: [TaskActionItem],
    noDeadlineTasks: [TaskActionItem]
  ) -> [TaskActionItem] {
    var seen = Set<String>()
    return (datedTasks + noDeadlineTasks).filter { seen.insert($0.id).inserted }
  }

  nonisolated static func noDeadlineOnly(_ items: [TaskActionItem]) -> [TaskActionItem] {
    var seen = Set<String>()
    return items.filter {
      $0.dueAt == nil && !$0.completed && !$0.isRetired && seen.insert($0.id).inserted
    }
  }

  nonisolated static func activeDatedOnly(_ items: [TaskActionItem]) -> [TaskActionItem] {
    items.filter { $0.dueAt != nil && !$0.completed && !$0.isRetired }
  }

  /// Count every incomplete dated row in the API's dated bucket, including
  /// retired rows that still occupy ordering slots before the null-due bucket.
  nonisolated static func apiDatedBucketCount(in items: [TaskActionItem]) -> Int {
    items.reduce(into: 0) { count, item in
      if item.dueAt != nil, !item.completed {
        count += 1
      }
    }
  }

  private func surfaceItems(_ surface: OwnerBoundOperations.IncompleteTaskSurface) -> [TaskActionItem] {
    surface.stablePresentationItems
  }

  private func loadIncompleteTaskSurface(
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations,
    noDeadlineLimit: Int = 100,
    noDeadlineOffset: Int = 0
  ) async throws -> OwnerBoundOperations.IncompleteTaskSurface {
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    if noDeadlineOffset == 0,
      noDeadlineLimit == pageSize,
      let loadIncompleteSurface = operations.loadIncompleteSurface
    {
      return try await loadIncompleteSurface(lease.ownerID)
    }
    if noDeadlineOffset == 0,
      let loadIncompleteSurfaceForLimit = operations.loadIncompleteSurfaceForLimit
    {
      return try await loadIncompleteSurfaceForLimit(lease.ownerID, noDeadlineLimit)
    }
    // Existing operation seams intentionally retain their old one-page
    // behavior for unrelated tests and callers. Production uses the split
    // storage primitive below.
    if operations.loadIncompleteSurface == nil, let loadIncomplete = operations.loadIncomplete {
      let items = try await loadIncomplete(lease.ownerID)
      return .init(
        datedTasks: Self.activeDatedOnly(items),
        noDeadlineTasks: Self.noDeadlineOnly(items),
        hasMoreNoDeadline: items.filter { $0.dueAt == nil }.count >= noDeadlineLimit
      )
    }
    let local = try await ActionItemStorage.shared.getIncompleteTaskSurface(
      noDeadlineLimit: noDeadlineLimit,
      noDeadlineOffset: noDeadlineOffset
    )
    return .init(
      datedTasks: local.dated,
      noDeadlineTasks: local.noDeadline,
      hasMoreNoDeadline: local.hasMoreNoDeadline
    )
  }

  /// Reload the complete dated surface and exactly the currently displayed
  /// bounded No Deadline surface. All cache reload callers use this helper so
  /// an expanded No Deadline list is never truncated back to the first page.
  private func reloadIncompleteTaskSurface(
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations,
    displayedNoDeadlineCount: Int
  ) async throws -> OwnerBoundOperations.IncompleteTaskSurface {
    let noDeadlineLimit = max(pageSize, displayedNoDeadlineCount)
    return try await loadIncompleteTaskSurface(
      lease: lease,
      operations: operations,
      noDeadlineLimit: noDeadlineLimit
    )
  }

  /// Rebuild the incomplete UI surface after background full sync. This is
  /// internal so behavioral tests can drive the same production helper with
  /// injected cache operations.
  func reloadIncompleteTaskSurfaceAfterFullSync(
    expectedOwnerID: String? = nil,
    operations: OwnerBoundOperations = OwnerBoundOperations()
  ) async {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else { return }
    await reloadIncompleteTaskSurfaceAfterFullSync(lease: lease, operations: operations)
  }

  private func reloadIncompleteTaskSurfaceAfterFullSync(
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async {
    do {
      let refreshedSurface = try await reloadIncompleteTaskSurface(
        lease: lease,
        operations: operations,
        displayedNoDeadlineCount: incompleteTasks.filter { $0.dueAt == nil }.count
      )
      guard isCurrent(lease) else { return }
      incompleteTasks = surfaceItems(refreshedSurface)
      incompleteSurfaceState.syncFrom(surface: refreshedSurface)
      hasMoreIncompleteTasks = refreshedSurface.hasMoreNoDeadline
      log("TasksStore: Refreshed UI after full sync - \(incompleteTasks.count) incomplete tasks")
    } catch {
      if isCurrent(lease) {
        logError("TasksStore: Failed to refresh UI after full sync", error: error)
      }
    }
  }

  private func fetchIncompleteTaskSurface(
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async throws -> OwnerBoundOperations.IncompleteTaskSurface {
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    if let fetchIncompleteSurface = operations.fetchIncompleteSurface {
      return try await fetchIncompleteSurface(lease.ownerID)
    }
    // Keep the legacy test seam compatible. Production's default path is the
    // split dated/null query below, because a general first page cannot prove
    // that every dated bucket is complete.
    if operations.fetchIncompleteSurface == nil, let fetchPage = operations.fetchPage {
      let page = try await fetchPage(false, 0, pageSize, lease.ownerID)
      return .init(
        datedTasks: Self.activeDatedOnly(page.items),
        noDeadlineTasks: Self.noDeadlineOnly(page.items),
        hasMoreNoDeadline: page.hasMore,
        apiConsumedNoDeadlineCount: page.items.count
      )
    }

    let datedBucket = try await fetchDatedBucketScan(lease: lease, operations: operations)
    incompleteSurfaceState.datedAPIBoundaryOffset = datedBucket.apiBoundaryOffset

    let noDeadlinePage = try await APIClient.shared.getNoDeadlineActionItems(
      limit: pageSize,
      offset: 0,
      datedBoundaryOffset: datedBucket.apiBoundaryOffset,
      completed: false,
      expectedOwnerId: lease.ownerID,
      authorizationSnapshot: lease.authorizationSnapshot
    )
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    return .init(
      datedTasks: datedBucket.items,
      noDeadlineTasks: Self.noDeadlineOnly(noDeadlinePage.items),
      hasMoreNoDeadline: noDeadlinePage.hasMore,
      apiConsumedNoDeadlineCount: noDeadlinePage.items.count
    )
  }

  private struct DatedBucketScan {
    let items: [TaskActionItem]
    let apiBoundaryOffset: Int
  }

  private func fetchDatedBucketScan(
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async throws -> DatedBucketScan {
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    if let fetchDatedTasks = operations.fetchDatedTasks {
      let items = try await fetchDatedTasks(lease.ownerID)
      let boundary = Self.apiDatedBucketCount(in: items)
      incompleteSurfaceState.datedAPIBoundaryOffset = boundary
      return .init(items: items, apiBoundaryOffset: boundary)
    }
    // Preserve older injected mixed-page seams. Production uses the complete
    // dated-bucket scan below, which refreshes the null-bucket boundary before
    // every No Deadline page.
    if operations.fetchPage != nil {
      let items = Self.activeDatedOnly(incompleteTasks)
      let boundary = Self.apiDatedBucketCount(in: items)
      incompleteSurfaceState.datedAPIBoundaryOffset = boundary
      return .init(items: items, apiBoundaryOffset: boundary)
    }

    return try await scanDatedIncompleteBuckets(lease: lease)
  }

  /// Scan every dated incomplete bucket page from the API, crossing the 2000-row
  /// offset cap with keyset windows when needed.
  private func scanDatedIncompleteBuckets(
    lease: OwnerOperationLease
  ) async throws -> DatedBucketScan {
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    let scan = try await APIClient.shared.scanDatedIncompleteActionItems(
      completed: false,
      pageLimit: Self.apiPageLimitCap,
      expectedOwnerId: lease.ownerID,
      authorizationSnapshot: lease.authorizationSnapshot
    )
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    incompleteSurfaceState.datedAPIBoundaryOffset = scan.boundaryOffset
    let items = scan.items.filter { $0.dueAt != nil && !$0.completed && !$0.isRetired }
    return .init(items: items, apiBoundaryOffset: scan.boundaryOffset)
  }

  private func fetchNoDeadlinePage(
    offset: Int,
    limit: Int,
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async throws -> OwnerBoundOperations.ActionItemsPage {
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    if let fetchNoDeadlinePage = operations.fetchNoDeadlinePage {
      return try await fetchNoDeadlinePage(offset, limit, lease.ownerID)
    }
    // Preserve the pre-split operation seam for existing owner-bound tests.
    if operations.fetchNoDeadlinePage == nil, let fetchPage = operations.fetchPage {
      return try await fetchPage(false, offset, limit, lease.ownerID)
    }
    let page = try await APIClient.shared.getNoDeadlineActionItems(
      limit: limit,
      offset: offset,
      datedBoundaryOffset: incompleteSurfaceState.datedAPIBoundaryOffset,
      completed: false,
      expectedOwnerId: lease.ownerID,
      authorizationSnapshot: lease.authorizationSnapshot
    )
    return .init(items: page.items, hasMore: page.hasMore)
  }

  private func fetchDeletedPage(
    offset: Int,
    limit: Int,
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async throws -> OwnerBoundOperations.ActionItemsPage {
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    let page: OwnerBoundOperations.ActionItemsPage
    if let fetchDeletedPage = operations.fetchDeletedPage {
      page = try await fetchDeletedPage(offset, limit, lease.ownerID)
    } else {
      let response = try await APIClient.shared.getActionItems(
        limit: limit,
        offset: offset,
        deleted: true,
        expectedOwnerId: lease.ownerID,
        authorizationSnapshot: lease.authorizationSnapshot
      )
      page = .init(items: response.items, hasMore: response.hasMore)
    }
    // Keep only the rows the response itself reports retired, and let the lane
    // stamp settle the ones that carry retirement through a field this decode
    // did not read (#11460: a retired row written to the cache as live
    // resurfaces as a live task).
    //
    // The lane used to be treated as the authority and stamped `.retired()`
    // over the whole page — but `GET /v1/action-items` has no `deleted`
    // parameter. FastAPI drops the unknown query item, and the handler's
    // stream skips soft-deleted documents outright, so what came back was the
    // user's *live* first page. Every caller of this page syncs it into
    // SQLite, so each visit to Removed tombstoned a hundred live tasks
    // locally: `deleted = 1` with no `deletedBy` and a canonical status still
    // `active`. Completing any of them from a chat task card then read the
    // tombstone back and rendered "Task is no longer available" over the task
    // the reader had just ticked.
    //
    // Until the backend can scope a page to retired rows, Removed shows the
    // deletions made on this Mac (those carry a local tombstone and a
    // `deletedBy`) and not another device's. Showing fewer rows is a gap;
    // manufacturing retirement is data loss.
    return .init(items: page.items.filter(\.isRetired).map { $0.retired() }, hasMore: page.hasMore)
  }

  func syncPage(
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
      return items.filter(\.isRetired)
    }
  }

  func refreshDashboard(
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async {
    guard isCurrent(lease) else { return }
    guard legacyConversationRecoveryCompleted(for: lease) else {
      // DashboardTaskRefreshService reconciles remote absence by hard-deleting
      // local rows. Before the marker-scoped recovery succeeds, a 404 from an
      // older backend leaves those local rows as the only safe copy.
      log("TasksStore: Dashboard server reconciliation skipped until legacy task recovery succeeds")
      await loadDashboardTasks(
        expectedOwnerID: lease.ownerID,
        authorizationSnapshot: lease.authorizationSnapshot
      )
      return
    }
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
    allowInitialReconciliation: Bool = true,
    operations: OwnerBoundOperations = OwnerBoundOperations()
  ) async {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else { return }
    guard !isLoadingIncomplete else { return }

    let displayedNoDeadlineCount = incompleteTasks.filter { $0.dueAt == nil }.count
    let preservedNoDeadlineAPIOffset = incompleteSurfaceState.noDeadlineAPIOffset

    isLoadingIncomplete = true
    error = nil
    incompleteError = nil
    incompleteSurfaceState.reset()

    // Step 1: Load the complete dated surface plus one bounded No Deadline
    // page from local cache for instant display.
    do {
      let cachedSurface = try await reloadIncompleteTaskSurface(
        lease: lease,
        operations: operations,
        displayedNoDeadlineCount: displayedNoDeadlineCount
      )
      guard isCurrent(lease) else { return }
      let cachedTasks = surfaceItems(cachedSurface)
      if !cachedTasks.isEmpty {
        incompleteTasks = cachedTasks
        incompleteSurfaceState.syncFrom(surface: cachedSurface)
        hasMoreIncompleteTasks = cachedSurface.hasMoreNoDeadline
        log("TasksStore: Loaded \(cachedTasks.count) incomplete tasks from local cache")
      }
    } catch {
      log("TasksStore: Local cache unavailable for incomplete tasks, falling back to API")
    }

    // Step 2: Fetch every dated page, then only the first No Deadline page.
    do {
      let surface = try await fetchIncompleteTaskSurface(lease: lease, operations: operations)
      guard isCurrent(lease) else { return }
      hasLoadedIncomplete = true
      let datedTasks = surface.activeDatedTasks
      let noDeadlineTasks = surface.activeNoDeadlineTasks
      incompleteSurfaceState.recordInitialFetch(
        surface: surface,
        noDeadlineTasks: noDeadlineTasks,
        preservedNoDeadlineAPIOffset: preservedNoDeadlineAPIOffset
      )
      hasMoreIncompleteTasks = surface.hasMoreNoDeadline
      let fetchedTasks = surface.stablePresentationItems
      log(
        "TasksStore: Fetched \(datedTasks.count) dated and \(noDeadlineTasks.count) No Deadline incomplete tasks "
          + "(hasMoreNoDeadline=\(surface.hasMoreNoDeadline))"
      )

      // Sync API data to local cache
      do {
        if let syncPage = operations.syncPage {
          try await syncPage(fetchedTasks, false, lease.ownerID)
        } else {
          try await ActionItemStorage.shared.syncTaskActionItems(
            fetchedTasks,
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

      // Reload from the split cache surface to retain local optimistic edits
      // without widening the No Deadline read.
      let mergedSurface = try await reloadIncompleteTaskSurface(
        lease: lease,
        operations: operations,
        displayedNoDeadlineCount: displayedNoDeadlineCount
      )
      guard isCurrent(lease) else { return }
      let mergedNoDeadlineTasks = Self.noDeadlineOnly(
        mergedSurface.noDeadlineTasks + noDeadlineTasks
      )
      let mergedTasks = Self.stableIncompleteTaskSurfaceItems(
        datedTasks: mergedSurface.activeDatedTasks,
        noDeadlineTasks: mergedNoDeadlineTasks
      )
      incompleteTasks = mergedTasks
      incompleteSurfaceState.syncFrom(
        datedCount: surface.apiDatedBucketCount,
        noDeadlinePresentationOffset: mergedNoDeadlineTasks.count
      )
      hasMoreIncompleteTasks = surface.hasMoreNoDeadline || mergedSurface.hasMoreNoDeadline
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
    if allowInitialReconciliation,
      legacyConversationRecoveryCompleted(for: lease),
      lastReconciliationDate == nil
    {
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
        let refreshedSurface = try await reloadIncompleteTaskSurface(
          lease: lease,
          operations: operations,
          displayedNoDeadlineCount: incompleteTasks.filter { $0.dueAt == nil }.count
        )
        guard isCurrent(lease) else { return }
        let refreshed = surfaceItems(refreshedSurface)
        if refreshed != incompleteTasks {
          incompleteTasks = refreshed
          incompleteSurfaceState.syncFrom(surface: refreshedSurface)
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
    let syncKey = ScopedDefaultsKey.tasksFullSyncCompleted(ownerID: userId)

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

      await reloadIncompleteTaskSurfaceAfterFullSync(lease: lease, operations: operations)
      guard isCurrent(lease) else { return }
      await loadDashboardTasks(
        expectedOwnerID: lease.ownerID,
        authorizationSnapshot: lease.authorizationSnapshot
      )

    } catch {
      if isCurrent(lease) {
        logError("TasksStore: Full sync failed (will retry next launch)", error: error)
      }
    }
  }

  /// Restore the exact rows a retired desktop migration moved out of the
  /// action-items collection. The recovery endpoint is idempotent and restores
  /// only rows explicitly marked `conversation_migration`; it never touches
  /// ordinary staged work.
  private func restoreLegacyConversationItemsIfNeeded(
    lease: OwnerOperationLease,
    operations: OwnerBoundOperations
  ) async -> Bool {
    guard isCurrent(lease) else { return false }
    let userId = lease.ownerID
    let recoveryKey = Self.legacyConversationRecoveryKey(for: userId)

    guard !UserDefaults.standard.bool(forKey: recoveryKey) else { return true }

    log("TasksStore: Checking for conversation tasks moved by the retired migration")

    do {
      var cursor: String?
      var seenCursors = Set<String>()
      var restored = 0
      var skippedExisting = 0

      while true {
        let page: LegacyConversationRecoveryPage
        if let restoreLegacyConversationItems = operations.restoreLegacyConversationItems {
          page = try await restoreLegacyConversationItems(lease.ownerID, cursor)
        } else {
          page = try await APIClient.shared.restoreLegacyConversationItems(
            cursor: cursor,
            expectedOwnerId: lease.ownerID,
            authorizationSnapshot: lease.authorizationSnapshot
          )
        }
        guard isCurrent(lease) else { return false }
        restored += page.restored
        skippedExisting += page.skippedExisting

        guard page.hasMore else {
          guard page.nextCursor == nil else { throw URLError(.badServerResponse) }
          break
        }
        guard
          let nextCursor = page.nextCursor,
          nextCursor != cursor,
          seenCursors.insert(nextCursor).inserted
        else {
          // A bounded page without a new cursor cannot safely prove the sweep
          // complete. Leave the marker unset and retry on a later launch.
          throw URLError(.badServerResponse)
        }
        cursor = nextCursor
      }

      // Every completed recovery sweep invalidates the startup sync, including
      // identity collisions. A skipped row has a current server action item
      // that the cache still needs to fetch, just like a newly restored row.
      UserDefaults.standard.set(false, forKey: .tasksFullSyncCompleted(ownerID: userId))
      operations.legacyRecoveryMarkersInvalidated?(userId)
      UserDefaults.standard.set(true, forKey: recoveryKey)
      if restored > 0 || skippedExisting > 0 {
        log(
          "TasksStore: Legacy conversation-task recovery completed: restored=\(restored), "
            + "alreadyCurrent=\(skippedExisting)"
        )
      }
      return true
    } catch {
      if isCurrent(lease) {
        // Do not mark the recovery complete on failure: a later launch may be
        // the first one after the backend recovery route is deployed.
        logError("TasksStore: Legacy conversation-task recovery failed", error: error)
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "task_reconcile",
          from: "legacy_recovery",
          to: "cache_only",
          reason: "other",
          outcome: .degraded
        )
      }
      return false
    }
  }

  private static func legacyConversationRecoveryKey(for ownerID: String) -> ScopedDefaultsKey {
    .restoreLegacyConversationItemsCompleted(ownerID: ownerID)
  }

  /// Until the marker-scoped server recovery succeeds, no path may treat an
  /// empty action-items response as authority to remove cached tasks.
  private func legacyConversationRecoveryCompleted(for lease: OwnerOperationLease) -> Bool {
    UserDefaults.standard.bool(forKey: Self.legacyConversationRecoveryKey(for: lease.ownerID))
  }

  /// The dashboard's exact-ID reconciliation can hard-delete a local row for
  /// a server 404. Keep that destructive authority behind the same recovery
  /// boundary as the full Tasks list so no independent dashboard caller can
  /// erase a migrated cache row while a pre-deploy backend rejects recovery.
  func canReconcileDashboardServerState(
    expectedOwnerID: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) -> Bool {
    guard
      let lease = captureOwnerLease(
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot
      )
    else { return false }
    return legacyConversationRecoveryCompleted(for: lease)
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
    guard await AccountCutoverOfflineUploadAdmission.allowsUploadOffMainActor() else {
      log("TasksStore: Skipping retryUnsyncedItems — account cutover offline upload gate closed")
      return
    }
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

    if items.isEmpty {
      await flushPendingBackendDeletions(lease: lease)
      return
    }
    log("TasksStore: Retrying sync for \(items.count) unsynced items")

    var synced = 0
    for item in items {
      guard isCurrent(lease) else { return }
      guard await AccountCutoverOfflineUploadAdmission.allowsUploadOffMainActor() else {
        log("TasksStore: Interrupted retryUnsyncedItems — account cutover offline upload gate closed")
        return
      }
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
    await flushPendingBackendDeletions(lease: lease)
  }

  /// Push unacknowledged deletions to the backend and purge the tombstones it confirms.
  ///
  /// Second half of the tombstone contract in `deleteTask`: the tombstone records that the
  /// user deleted the task, this flush makes the server agree, and only the server's
  /// confirmation removes the local row. Partial confirmations purge exactly the confirmed
  /// IDs — the rest stay tombstoned for the next pass.
  private func flushPendingBackendDeletions(lease: OwnerOperationLease) async {
    guard isCurrent(lease) else { return }
    let pending: [String]
    do {
      pending = try await ActionItemStorage.shared.getPendingBackendDeletionIds()
    } catch {
      if isCurrent(lease) { logError("TasksStore: Failed to read pending deletions", error: error) }
      return
    }
    guard isCurrent(lease), !pending.isEmpty else { return }
    log("TasksStore: Flushing \(pending.count) unacknowledged task deletions")

    var confirmed: [String] = []
    do {
      try await APIClient.shared.batchDeleteActionItems(
        ids: pending,
        expectedOwnerId: lease.ownerID,
        authorizationSnapshot: lease.authorizationSnapshot
      )
      confirmed = pending
    } catch let partial as APIClient.BatchDeletePartialFailure {
      confirmed = partial.confirmedIDs
    } catch {
      guard isCurrent(lease) else { return }
      logError("TasksStore: Deletion flush failed — tombstones retained", error: error)
      return
    }

    guard isCurrent(lease) else { return }
    for id in confirmed {
      try? await ActionItemStorage.shared.markActionItemDeletionAcknowledged(
        backendId: id,
        authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
      )
      guard isCurrent(lease) else { return }
    }
    log("TasksStore: Deletion flush confirmed \(confirmed.count)/\(pending.count)")
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
    guard hasMoreIncompleteTasks, !isLoadingMore, !isLoadingIncomplete else { return }
    // Dated buckets are complete after the initial split load. Pagination is
    // exclusively for No Deadline rows, so a dated row can never trigger a
    // late side-effect page.
    guard currentTask.dueAt == nil else { return }

    let thresholdIndex =
      incompleteTasks.index(incompleteTasks.endIndex, offsetBy: -10, limitedBy: incompleteTasks.startIndex)
      ?? incompleteTasks.startIndex
    guard let taskIndex = incompleteTasks.firstIndex(where: { $0.id == currentTask.id }),
      taskIndex >= thresholdIndex
    else {
      return
    }

    isLoadingMore = true
    defer { isLoadingMore = false }

    do {
      // Recompute the dated boundary immediately before consuming the next
      // No Deadline page. The API exposes the null bucket through a general
      // offset, so a dated row created/completed during pagination otherwise
      // shifts that boundary and can cause skips or duplicates.
      let datedBucket = try await fetchDatedBucketScan(lease: lease, operations: operations)
      guard isCurrent(lease) else { return }
      incompleteSurfaceState.datedCount = Self.apiDatedBucketCount(in: datedBucket.items)
      incompleteSurfaceState.datedAPIBoundaryOffset = datedBucket.apiBoundaryOffset
      let datedTasks = Self.activeDatedOnly(datedBucket.items)
      let response = try await fetchNoDeadlinePage(
        offset: incompleteSurfaceState.noDeadlineAPIOffset,
        limit: pageSize,
        lease: lease,
        operations: operations
      )
      guard isCurrent(lease) else { return }
      let noDeadlineItems = Self.noDeadlineOnly(response.items)

      // Sync to cache
      try await syncPage(noDeadlineItems, lease: lease, operations: operations)
      guard isCurrent(lease) else { return }

      let refreshedDatedIDs = Set(datedTasks.map(\.id))
      let visibleDatedTasks =
        datedTasks
        + incompleteTasks.filter {
          $0.dueAt != nil && !$0.completed && !$0.isRetired && !refreshedDatedIDs.contains($0.id)
        }
      incompleteTasks = Self.stableIncompleteTaskSurfaceItems(
        datedTasks: visibleDatedTasks,
        noDeadlineTasks: incompleteTasks.filter { $0.dueAt == nil } + noDeadlineItems
      )
      hasMoreIncompleteTasks = response.hasMore
      // Advance the API cursor by raw API consumption, not by the number of
      // accepted/deduplicated rows in the local presentation.
      incompleteSurfaceState.advanceNoDeadlineAPI(by: response.items.count)
      incompleteSurfaceState.syncNoDeadlinePresentation(from: incompleteTasks)
      log("TasksStore: Loaded \(noDeadlineItems.count) more No Deadline tasks from API")
    } catch {
      if isCurrent(lease) {
        logError("TasksStore: Failed to load more incomplete tasks", error: error)
      }
    }

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
    defer { isLoadingMore = false }

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

  nonisolated static func localMutationAuthorization(
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
      completedTasks.insert(updatedTask, at: 0)
      incompleteTasks.removeAll { $0.id == task.id }

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
      incompleteTasks.insert(updatedTask, at: 0)
      completedTasks.removeAll { $0.id == task.id }
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
      incompleteTasks.insert(task, at: 0)
      completedTasks.removeAll { $0.id == task.id }
    } else {
      completedTasks.insert(task, at: 0)
      incompleteTasks.removeAll { $0.id == task.id }
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
    // Local-first, but as a tombstone, not a hard delete: the row keeps `deleted = 1,
    // backendSynced = 0` until the server acknowledges, so a failed backend call cannot be
    // forgotten and hydration cannot resurrect the task. Hard-deleting here was how 450
    // deleted tasks came back after a reinstall.
    let isLocalOnly = ActionItemTaskIdentity(surfacedId: task.id).isLocalOnly
    do {
      if isLocalOnly {
        // No backend row exists; a tombstone would wait forever for an ack.
        try await ActionItemStorage.shared.deleteActionItemByBackendId(
          task.id,
          authorization: Self.localMutationAuthorization(
            snapshot: lease.authorizationSnapshot
          )
        )
      } else {
        try await ActionItemStorage.shared.markActionItemDeletedPendingBackendSync(
          backendId: task.id,
          authorization: Self.localMutationAuthorization(
            snapshot: lease.authorizationSnapshot
          )
        )
      }
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

    // Delete on backend; only an acknowledgement clears the local tombstone.
    if isLocalOnly {
      log("TasksStore: Skipped backend delete for unsynced local task \(task.id)")
      return
    }
    do {
      try await APIClient.shared.deleteActionItem(
        id: task.id,
        expectedOwnerId: ownerID,
        authorizationSnapshot: lease.authorizationSnapshot
      )
      guard isCurrent(lease) else { return }
      try? await ActionItemStorage.shared.markActionItemDeletionAcknowledged(
        backendId: task.id,
        authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
      )
    } catch {
      guard isCurrent(lease) else { return }
      logError(
        "TasksStore: Backend delete not acknowledged — tombstone retained for retry", error: error)
    }
  }

  /// Restore a previously deleted task (for undo)
  /// Re-inserts the task into SQLite and re-creates on backend (since both were hard-deleted).
  func restoreTask(
    _ task: TaskActionItem,
    expectedOwnerID: String? = nil
  ) async {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else { return }
    // Undo of a tombstoned delete: the row still exists locally (deleted, whether or not
    // the backend acked). Purge it before the re-insert below or undo would duplicate it.
    try? await ActionItemStorage.shared.deleteActionItemByBackendId(
      task.id,
      authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
    )
    guard isCurrent(lease) else { return }

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
    guard
      let lease = captureOwnerLease(
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot
      )
    else { return .ownerChanged }
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
    guard
      let lease = captureOwnerLease(
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot
      )
    else { return false }
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

  /// Sync all scored tasks' relevance scores to backend
  private func syncScoresToBackend(expectedOwnerID: String? = nil) async {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else { return }
    await syncScoresToBackend(lease: lease)
  }

  func syncScoresToBackend(lease: OwnerOperationLease) async {
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
