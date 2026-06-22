import Foundation

@MainActor
final class StartupWarmupCoordinator {
    private let tasksStore: TasksStore
    private let dashboardViewModel: DashboardViewModel
    private let appProvider: AppProvider
    private let chatProvider: ChatProvider
    private let retryDatabaseInit: () async -> Bool

    private var scheduleState = StartupWarmupScheduleState()
    private var serviceWarmupTask: Task<Void, Never>?
    private var databaseWarmupTask: Task<Void, Never>?
    private var dashboardNetworkRefreshTask: Task<Void, Never>?
    private var chatPromptContextWarmupTask: Task<Void, Never>?
    private var databaseRetryTask: Task<Void, Never>?

    init(
        tasksStore: TasksStore,
        dashboardViewModel: DashboardViewModel,
        appProvider: AppProvider,
        chatProvider: ChatProvider,
        retryDatabaseInit: @escaping () async -> Bool
    ) {
        self.tasksStore = tasksStore
        self.dashboardViewModel = dashboardViewModel
        self.appProvider = appProvider
        self.chatProvider = chatProvider
        self.retryDatabaseInit = retryDatabaseInit
    }

    func cancel() {
        serviceWarmupTask?.cancel()
        databaseWarmupTask?.cancel()
        dashboardNetworkRefreshTask?.cancel()
        chatPromptContextWarmupTask?.cancel()
        databaseRetryTask?.cancel()
    }

    func reset() {
        cancel()
        scheduleState = StartupWarmupScheduleState()
    }

    func schedulePostInteractiveWarmup(dbAvailable: Bool) {
        if scheduleState.reserveServiceWarmup() {
            serviceWarmupTask = Task { [weak self] in
                await self?.runServiceWarmup()
            }
        }

        scheduleDatabaseWarmup(dbAvailable: dbAvailable)
        scheduleDatabaseRetryIfNeeded(dbAvailable: dbAvailable)
    }

    private func scheduleDatabaseWarmup(dbAvailable: Bool) {
        guard scheduleState.reserveDatabaseWarmup(dbAvailable: dbAvailable) else {
            if !dbAvailable {
                log("DATA LOAD: Waiting to schedule DB warmup until database retry succeeds")
            }
            return
        }

        databaseWarmupTask = Task { [weak self] in
            await self?.runDatabaseWarmup()
        }
        scheduleDashboardNetworkRefresh(dbAvailable: true)
        scheduleChatPromptContextWarmup()
    }

    private func runDatabaseWarmup() async {
        guard await sleepForStartupDelay(StartupWarmupPolicy.immediateWarmupDelay) else { return }

        await measurePerfAsync("DATA LOAD: Immediate warmup") { [self] in
            async let tasks: Void = measurePerfAsync("DATA LOAD: TasksStore dashboard snapshot") {
                await tasksStore.loadDashboardTasks()
            }
            async let dashboard: Void = measurePerfAsync("DATA LOAD: Dashboard cached snapshot") {
                await dashboardViewModel.loadCachedDashboardData()
            }
            _ = await (tasks, dashboard)
        }

        guard await sleepForStartupDelay(StartupWarmupPolicy.deferredWarmupDelay) else { return }
        guard await AuthState.shared.isSignedIn else {
            log("DATA LOAD: Skipping DB lifecycle warmup because user is signed out")
            scheduleState.releaseDatabaseWarmup()
            return
        }

        await measurePerfAsync("DATA LOAD: DB lifecycle warmup") {
            await measurePerfAsync("DATA LOAD: Task agent restore") {
                await TaskAgentManager.shared.restoreSessionsFromDatabase()
            }
            await measurePerfAsync("DATA LOAD: Screen activity sync") {
                await ScreenActivitySyncService.shared.start(
                    initialDelay: StartupWarmupPolicy.screenActivitySyncInitialDelay
                )
            }
        }

        logPerf("DATA LOAD: DB warmup complete", cpu: true)
    }

    private func runServiceWarmup() async {
        guard await sleepForStartupDelay(
            StartupWarmupPolicy.immediateWarmupDelay + StartupWarmupPolicy.deferredWarmupDelay
        ) else { return }

        await measurePerfAsync("DATA LOAD: Deferred service warmup") { [self] in
            async let apps: Void = measurePerfAsync("DATA LOAD: Chat apps") {
                await appProvider.fetchChatAppsForStartup()
            }
            async let chatMessages: Void = measurePerfAsync("DATA LOAD: Chat messages") {
                await chatProvider.initializeVisibleMessages()
            }

            _ = await (apps, chatMessages)
        }

        logPerf("DATA LOAD: Service warmup complete", cpu: true)
    }

    private func scheduleDashboardNetworkRefresh(dbAvailable: Bool) {
        guard dbAvailable else {
            log("DATA LOAD: Skipping dashboard network refresh (database unavailable)")
            return
        }

        dashboardNetworkRefreshTask = Task { [weak self] in
            guard let self else { return }
            guard await sleepForStartupDelay(StartupWarmupPolicy.dashboardNetworkRefreshDelay) else { return }

            await measurePerfAsync("DATA LOAD: Dashboard network refresh") {
                await self.dashboardViewModel.loadDashboardData()
            }
        }
    }

    private func scheduleChatPromptContextWarmup() {
        chatPromptContextWarmupTask = Task { [weak self] in
            guard let self else { return }
            guard await sleepForStartupDelay(StartupWarmupPolicy.chatPromptContextWarmupDelay) else { return }

            await measurePerfAsync("DATA LOAD: Chat prompt context") {
                await self.chatProvider.warmupPromptContext()
            }
        }
    }

    private func scheduleDatabaseRetryIfNeeded(dbAvailable: Bool) {
        guard !dbAvailable else { return }
        guard databaseRetryTask == nil else { return }

        databaseRetryTask = Task { [weak self] in
            guard let self else { return }
            var delay = StartupWarmupPolicy.databaseRetryInitialDelay

            while !Task.isCancelled {
                guard await self.sleepForStartupDelay(delay) else { return }
                let didRecover = await self.retryDatabaseInit()
                if didRecover {
                    self.databaseRetryTask = nil
                    return
                }

                delay = min(delay * 2, StartupWarmupPolicy.databaseRetryMaxDelay)
            }
        }
    }

    func markDatabaseRetryComplete() {
        databaseRetryTask = nil
    }

    private func sleepForStartupDelay(_ seconds: TimeInterval) async -> Bool {
        guard seconds > 0 else { return !Task.isCancelled }
        do {
            try await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
            return !Task.isCancelled
        } catch {
            return false
        }
    }
}
