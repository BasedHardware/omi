import SwiftUI

/// Central container that holds all ViewModels for eager data loading
/// and keeps views alive across tab switches
@MainActor
class ViewModelContainer: ObservableObject {
    // Shared stores (single source of truth)
    let tasksStore = TasksStore.shared

    // ViewModels for each page
    let dashboardViewModel = DashboardViewModel()
    let tasksViewModel = TasksViewModel()
    let appProvider = AppProvider()
    let memoriesViewModel = MemoriesViewModel()
    let chatProvider = ChatProvider()

    // Loading state
    @Published var isInitialLoadComplete = false
    @Published var isLoading = false
    @Published var databaseInitFailed = false
    @Published var initStatusMessage: String = "Preparing your data…"

    /// Load all data in parallel at app launch
    func loadAllData() async {
        guard !isLoading else { return }
        isLoading = true

        let timer = PerfTimer("ViewModelContainer.loadAllData", logCPU: true)
        logPerf("DATA LOAD: Starting eager data load for all pages", cpu: true)

        // Configure database for the current user before initialization
        let userId = UserDefaults.standard.string(forKey: "auth_userId")
        await RewindDatabase.shared.configure(userId: userId)

        // Pre-initialize database so local SQLite reads are instant
        do {
            try await RewindDatabase.shared.initialize()
            databaseInitFailed = false
        } catch {
            logError("ViewModelContainer: Database pre-init failed, DB-dependent loads will be skipped", error: error)
            databaseInitFailed = true
        }

        // Database is ready (or failed) — dismiss the loading screen
        // API calls and data fetches continue in the background
        isInitialLoadComplete = true

        // DB-dependent loads are guarded — skip them if database init failed
        // to prevent a stampede of retries from each storage actor
        let dbAvailable = !databaseInitFailed

        // Load shared stores first (both Dashboard and Tasks use these)
        async let tasks: Void = measurePerfAsync("DATA LOAD: TasksStore") {
            guard dbAvailable else {
                log("DATA LOAD: Skipping TasksStore (database unavailable)")
                return
            }
            await tasksStore.loadTasks()
        }

        // Load page-specific data in parallel
        async let dashboard: Void = measurePerfAsync("DATA LOAD: Dashboard") {
            guard dbAvailable else {
                log("DATA LOAD: Skipping Dashboard (database unavailable)")
                return
            }
            await dashboardViewModel.loadDashboardData()
        }
        // Apps and Chat don't depend on local DB
        async let apps: Void = measurePerfAsync("DATA LOAD: Apps") { await appProvider.fetchApps() }
        async let memories: Void = measurePerfAsync("DATA LOAD: Memories") {
            guard dbAvailable else {
                log("DATA LOAD: Skipping Memories (database unavailable)")
                return
            }
            await memoriesViewModel.loadMemories()
        }
        async let chat: Void = measurePerfAsync("DATA LOAD: Chat") { await chatProvider.initialize() }

        // Wait for all to complete
        _ = await (tasks, dashboard, apps, memories, chat)

        // Restore agent sessions from database (reconnect to live tmux sessions)
        if dbAvailable {
            await TaskAgentManager.shared.restoreSessionsFromDatabase()
        }

        isLoading = false

        timer.stop()
        logPerf("DATA LOAD: Complete - all pages loaded", cpu: true)
    }

    /// Retry database initialization and reload DB-dependent data
    func retryDatabaseInit() async {
        guard databaseInitFailed else { return }
        log("ViewModelContainer: Retrying database initialization...")

        // Re-configure userId in case it changed (e.g. sign-in completed since first attempt)
        let userId = UserDefaults.standard.string(forKey: "auth_userId")
        await RewindDatabase.shared.configure(userId: userId)

        do {
            try await RewindDatabase.shared.initialize()
            databaseInitFailed = false
            log("ViewModelContainer: Database retry succeeded, loading data...")

            // Load previously skipped DB-dependent data
            async let tasks: Void = tasksStore.loadTasks()
            async let dashboard: Void = dashboardViewModel.loadDashboardData()
            async let memories: Void = memoriesViewModel.loadMemories()
            _ = await (tasks, dashboard, memories)

            log("ViewModelContainer: DB-dependent data loaded after retry")
        } catch {
            logError("ViewModelContainer: Database retry failed", error: error)
        }
    }
}
