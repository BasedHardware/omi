import SwiftUI

/// Central container that holds all ViewModels for eager data loading
/// and keeps views alive across tab switches
@MainActor
class ViewModelContainer: ObservableObject {
  // Shared stores (single source of truth)
  let tasksStore = TasksStore.shared

  // ViewModels for each page
  let dashboardViewModel = DashboardViewModel()
  let homeStatusStore = HomeStatusStore()
  let homeTodayStore = HomeTodayStore()
  let tasksViewModel = TasksViewModel()
  let appProvider = AppProvider()
  let memoriesViewModel = MemoriesViewModel()
  /// Brain-map graph — persistent so the SceneKit scene, force layout, and
  /// camera survive page navigation instead of rebuilding every visit.
  let memoryGraphViewModel = MemoryGraphViewModel()
  let chatProvider: ChatProvider
  let taskChatCoordinator: TaskChatCoordinator
  private lazy var warmupCoordinator = StartupWarmupCoordinator(
    tasksStore: tasksStore,
    dashboardViewModel: dashboardViewModel,
    appProvider: appProvider,
    chatProvider: chatProvider,
    retryDatabaseInit: { [weak self] in
      await self?.retryDatabaseInit() ?? false
    }
  )

  init() {
    let provider = ChatProvider()
    chatProvider = provider
    taskChatCoordinator = TaskChatCoordinator(chatProvider: provider)
    ChatProvider.mainInstance = provider
    RecurringTaskScheduler.shared.configure(taskChatCoordinator: taskChatCoordinator)

    // Bind the headless task automation actions (create/toggle/delete/reorder/dump)
    // to this canonical, long-lived TasksViewModel so omi-ctl can drive TASK-01/02/03
    // without the Tasks page being on screen. Gated to the automation bridge, which
    // only runs on non-prod bundles.
    if DesktopAutomationLaunchOptions.isEnabled {
      tasksViewModel.registerAutomationActions()
      #if DEBUG
        taskChatCoordinator.registerAutomationActions()
      #endif
      memoriesViewModel.registerAutomationActions()
    }
  }

  // Loading state
  @Published var isInitialLoadComplete = false
  @Published var isLoading = false
  @Published var databaseInitFailed = false
  @Published var initStatusMessage: String = "Preparing your data…"
  private var loadedUserId: String?

  /// Load critical startup data, then stage warmup work after the first usable window.
  func loadAllData() async {
    let currentUserId = RuntimeOwnerIdentity.currentOwnerId()
    if loadedUserId != nil, loadedUserId != currentUserId {
      resetStartupState()
    }

    guard !isLoading else { return }
    guard !isInitialLoadComplete else {
      schedulePostInteractiveWarmup(dbAvailable: !databaseInitFailed)
      return
    }
    isLoading = true

    let startupStart = CFAbsoluteTimeGetCurrent()
    let timer = PerfTimer("ViewModelContainer.loadAllData", logCPU: true)
    logPerf("DATA LOAD: Starting critical startup path", cpu: true)

    // Pre-initialize database so local SQLite reads are instant
    let dbInitStart = CFAbsoluteTimeGetCurrent()
    let hadUncleanShutdown = await RewindDatabase.shared.hadUncleanShutdown()
    do {
      try await RewindDatabase.shared.initialize()
      databaseInitFailed = false
    } catch {
      logError("ViewModelContainer: Database pre-init failed, DB-dependent loads will be skipped", error: error)
      databaseInitFailed = true
    }
    let dbInitDuration = CFAbsoluteTimeGetCurrent() - dbInitStart

    // Database is ready (or failed) — dismiss the loading screen
    // API calls and data fetches continue in the background
    isInitialLoadComplete = true
    loadedUserId = currentUserId
    let timeToInteractive = CFAbsoluteTimeGetCurrent() - startupStart

    // Track startup timing
    logPerf(
      "DATA LOAD: DB init \(String(format: "%.1f", dbInitDuration * 1000))ms, time-to-interactive \(String(format: "%.1f", timeToInteractive * 1000))ms, uncleanShutdown=\(hadUncleanShutdown)"
    )
    AnalyticsManager.shared.trackStartupTiming(
      dbInitMs: dbInitDuration * 1000,
      timeToInteractiveMs: timeToInteractive * 1000,
      hadUncleanShutdown: hadUncleanShutdown,
      databaseInitFailed: databaseInitFailed
    )

    // DB-dependent loads are guarded — skip them if database init failed
    // to prevent a stampede of retries from each storage actor
    let dbAvailable = !databaseInitFailed
    if dbAvailable {
      await homeStatusStore.databaseDidBecomeReady()
    }

    schedulePostInteractiveWarmup(dbAvailable: dbAvailable)
    isLoading = false

    timer.stop()
    logPerf("DATA LOAD: Critical startup complete - post-interactive warmup scheduled", cpu: true)
  }

  private func schedulePostInteractiveWarmup(dbAvailable: Bool) {
    tasksViewModel.chatCoordinator = taskChatCoordinator
    warmupCoordinator.schedulePostInteractiveWarmup(dbAvailable: dbAvailable)
  }

  @discardableResult
  func scheduleSessionWarmup(
    id: StartupWarmupTaskID,
    delay: TimeInterval,
    onCancel: (@MainActor () -> Void)? = nil,
    operation: @MainActor @escaping () async -> Void
  ) -> Bool {
    warmupCoordinator.scheduleSessionWarmup(
      id: id,
      delay: delay,
      onCancel: onCancel,
      operation: operation
    )
  }

  func resetStartupState() {
    warmupCoordinator.reset()
    tasksStore.resetSessionState()
    dashboardViewModel.resetSessionState()
    homeStatusStore.resetSessionState()
    homeTodayStore.resetSessionState()
    memoriesViewModel.resetSessionState()
    appProvider.resetSessionState()
    memoryGraphViewModel.resetSessionState()
    isInitialLoadComplete = false
    isLoading = false
    databaseInitFailed = false
    initStatusMessage = "Preparing your data…"
    loadedUserId = nil
  }

  /// Retry database initialization and schedule the normal staged startup warmup.
  func retryDatabaseInit() async -> Bool {
    guard databaseInitFailed else { return true }
    log("ViewModelContainer: Retrying database initialization...")

    do {
      try await RewindDatabase.shared.initialize()
      databaseInitFailed = false
      await homeStatusStore.databaseDidBecomeReady()
      warmupCoordinator.markDatabaseRetryComplete()
      TranscriptionRetryService.shared.resumeAfterDatabaseRecovery()
      log("ViewModelContainer: Database retry succeeded, scheduling staged startup warmup")
      schedulePostInteractiveWarmup(dbAvailable: true)
      return true
    } catch {
      logError("ViewModelContainer: Database retry failed", error: error)
      return false
    }
  }
}
