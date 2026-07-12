import Foundation

@MainActor
final class StartupWarmupCoordinator {
    private let tasksStore: TasksStore
    private let dashboardViewModel: DashboardViewModel
    private let appProvider: AppProvider
    private let chatProvider: ChatProvider
    private let retryDatabaseInit: () async -> Bool

    private var scheduleState = StartupWarmupScheduleState()
    private var sessionTasks: [StartupWarmupTaskID: Task<Void, Never>] = [:]
    private var sessionTaskTokens: [StartupWarmupTaskID: UUID] = [:]

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
        sessionTasks.values.forEach { $0.cancel() }
        sessionTasks.removeAll()
        sessionTaskTokens.removeAll()
    }

    func reset() {
        cancel()
        scheduleState = StartupWarmupScheduleState()
    }

    @discardableResult
    func scheduleSessionWarmup(
        id: StartupWarmupTaskID,
        delay: TimeInterval,
        onCancel: (@MainActor () -> Void)? = nil,
        operation: @MainActor @escaping () async -> Void
    ) -> Bool {
        let scope = currentSessionScope()
        guard isCurrentSession(scope) else { return false }

        sessionTasks[id]?.cancel()
        let token = UUID()
        sessionTaskTokens[id] = token
        sessionTasks[id] = Task { [weak self] in
            guard let self else { return }
            guard await self.sleepForStartupDelay(delay) else {
                await MainActor.run { onCancel?() }
                return
            }
            guard self.isCurrentSession(scope) else {
                await MainActor.run { onCancel?() }
                return
            }
            await operation()
            await MainActor.run {
                guard self.sessionTaskTokens[id] == token else { return }
                self.sessionTasks[id] = nil
                self.sessionTaskTokens[id] = nil
            }
        }
        return true
    }

    func schedulePostInteractiveWarmup(dbAvailable: Bool) {
        if scheduleState.reserveServiceWarmup() {
            let scheduled = scheduleSessionWarmup(id: .serviceWarmup, delay: 0) { [weak self] in
                await self?.runServiceWarmup()
            }
            if !scheduled { scheduleState.releaseServiceWarmup() }
        }

        scheduleDatabaseWarmup(dbAvailable: dbAvailable)
        scheduleDatabaseRetryIfNeeded(dbAvailable: dbAvailable)
        scheduleMCPKeyWarmup()
    }

    private func scheduleDatabaseWarmup(dbAvailable: Bool) {
        guard scheduleState.reserveDatabaseWarmup(dbAvailable: dbAvailable) else {
            if !dbAvailable {
                log("DATA LOAD: Waiting to schedule DB warmup until database retry succeeds")
            }
            return
        }

        let scheduled = scheduleSessionWarmup(id: .databaseWarmup, delay: 0) { [weak self] in
            await self?.runDatabaseWarmup()
        }
        guard scheduled else {
            scheduleState.releaseDatabaseWarmup()
            return
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
        guard AuthState.shared.isSignedIn else {
            log("DATA LOAD: Skipping DB lifecycle warmup because user is signed out")
            scheduleState.releaseDatabaseWarmup()
            return
        }

        tasksStore.scheduleStartupMaintenanceIfNeeded()

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

        scheduleSessionWarmup(id: .dashboardNetworkRefresh, delay: StartupWarmupPolicy.dashboardNetworkRefreshDelay) { [weak self] in
            guard let self else { return }
            await measurePerfAsync("DATA LOAD: Dashboard network refresh") {
                await self.dashboardViewModel.loadDashboardData()
            }
        }
    }

    private func scheduleChatPromptContextWarmup() {
        scheduleSessionWarmup(id: .chatPromptContextWarmup, delay: StartupWarmupPolicy.chatPromptContextWarmupDelay) { [weak self] in
            guard let self else { return }
            await measurePerfAsync("DATA LOAD: Chat prompt context") {
                await self.chatProvider.warmupPromptContext()
            }
        }
    }

    private func scheduleMCPKeyWarmup() {
        scheduleSessionWarmup(id: .mcpKeyWarmup, delay: StartupWarmupPolicy.mcpKeyWarmupDelay) {
            await measurePerfAsync("DATA LOAD: Hosted MCP key warmup") {
                await MemoryExportService.shared.warmMCPKeyForCurrentUser()
            }
        }
    }

    private func scheduleDatabaseRetryIfNeeded(dbAvailable: Bool) {
        guard !dbAvailable else { return }
        guard sessionTasks[.databaseRetry] == nil else { return }

        let scope = currentSessionScope()
        guard isCurrentSession(scope) else { return }

        sessionTasks[.databaseRetry] = Task { [weak self] in
            guard let self else { return }
            var delay = StartupWarmupPolicy.databaseRetryInitialDelay

            while !Task.isCancelled {
                guard await self.sleepForStartupDelay(delay) else { return }
                guard self.isCurrentSession(scope) else {
                    await MainActor.run { self.sessionTasks[.databaseRetry] = nil }
                    return
                }
                let didRecover = await self.retryDatabaseInit()
                guard self.isCurrentSession(scope) else {
                    await MainActor.run { self.sessionTasks[.databaseRetry] = nil }
                    return
                }
                if didRecover {
                    self.sessionTasks[.databaseRetry] = nil
                    return
                }

                delay = min(delay * 2, StartupWarmupPolicy.databaseRetryMaxDelay)
            }
        }
    }

    func markDatabaseRetryComplete() {
        sessionTasks[.databaseRetry] = nil
    }

    private func currentSessionScope() -> StartupWarmupSessionScope {
        StartupWarmupSessionScope(userId: UserDefaults.standard.string(forKey: "auth_userId"))
    }

    private func isCurrentSession(_ scope: StartupWarmupSessionScope) -> Bool {
        scope.matches(
            currentUserId: UserDefaults.standard.string(forKey: "auth_userId"),
            isSignedIn: AuthState.shared.isSignedIn
        )
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
