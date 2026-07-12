import XCTest

@testable import Omi_Computer

final class StartupWarmupPolicyTests: XCTestCase {
    func testDeferredWarmupStartsAfterImmediateWorkHasAChanceToSettle() {
        XCTAssertGreaterThan(
            StartupWarmupPolicy.deferredWarmupDelay,
            StartupWarmupPolicy.immediateWarmupDelay
        )
    }

    func testScreenActivitySyncWaitsUntilAfterDeferredWarmupStarts() {
        XCTAssertGreaterThan(
            StartupWarmupPolicy.screenActivitySyncInitialDelay,
            StartupWarmupPolicy.deferredWarmupDelay
        )
    }

    func testCrispInitialPollWaitsUntilAfterDeferredWarmupStarts() {
        XCTAssertGreaterThan(
            StartupWarmupPolicy.crispInitialPollDelay,
            StartupWarmupPolicy.deferredWarmupDelay
        )
    }

    func testAgentVMProvisioningWaitsUntilAfterDeferredWarmupStarts() {
        XCTAssertGreaterThan(
            StartupWarmupPolicy.agentVMProvisioningDelay,
            StartupWarmupPolicy.deferredWarmupDelay
        )
    }

    func testProactiveAssistantsWaitUntilAfterDeferredWarmupStarts() {
        XCTAssertGreaterThan(
            StartupWarmupPolicy.proactiveAssistantsStartDelay,
            StartupWarmupPolicy.deferredWarmupDelay
        )
    }

    func testProactiveAssistantsRemainingDelayIsFullAtLaunch() {
        XCTAssertEqual(
            StartupWarmupPolicy.remainingProactiveAssistantsStartDelay(elapsedSinceLaunch: 0),
            StartupWarmupPolicy.proactiveAssistantsStartDelay
        )
    }

    func testProactiveAssistantsRemainingDelayCountsDownFromLaunch() {
        XCTAssertEqual(
            StartupWarmupPolicy.remainingProactiveAssistantsStartDelay(elapsedSinceLaunch: 2.0),
            StartupWarmupPolicy.proactiveAssistantsStartDelay - 2.0,
            accuracy: 0.0001
        )
    }

    func testProactiveAssistantsRemainingDelayIsZeroOnceWindowHasElapsed() {
        XCTAssertEqual(
            StartupWarmupPolicy.remainingProactiveAssistantsStartDelay(
                elapsedSinceLaunch: StartupWarmupPolicy.proactiveAssistantsStartDelay + 60),
            0
        )
    }

    func testProactiveAssistantsRemainingDelayClampsNegativeElapsedToFullDelay() {
        XCTAssertEqual(
            StartupWarmupPolicy.remainingProactiveAssistantsStartDelay(elapsedSinceLaunch: -5),
            StartupWarmupPolicy.proactiveAssistantsStartDelay
        )
    }

    func testConversationWarmupWaitsUntilAfterDeferredWarmupStarts() {
        XCTAssertGreaterThan(
            StartupWarmupPolicy.conversationWarmupDelay,
            StartupWarmupPolicy.deferredWarmupDelay
        )
    }

    func testInitialFileIndexingWaitsUntilAfterDeferredWarmupStarts() {
        XCTAssertGreaterThan(
            StartupWarmupPolicy.initialFileIndexingDelay,
            StartupWarmupPolicy.deferredWarmupDelay
        )
    }

    func testTranscriptionRetryRecoveryWaitsUntilAfterDeferredWarmupStarts() {
        XCTAssertGreaterThan(
            StartupWarmupPolicy.transcriptionRetryRecoveryDelay,
            StartupWarmupPolicy.deferredWarmupDelay
        )
    }

    func testRecurringTaskSchedulerWaitsUntilAfterDeferredWarmupStarts() {
        XCTAssertGreaterThan(
            StartupWarmupPolicy.recurringTaskSchedulerInitialDelay,
            StartupWarmupPolicy.deferredWarmupDelay
        )
    }

    func testDashboardNetworkRefreshWaitsUntilAfterDeferredWarmupStarts() {
        XCTAssertGreaterThan(
            StartupWarmupPolicy.dashboardNetworkRefreshDelay,
            StartupWarmupPolicy.deferredWarmupDelay
        )
    }

    func testFloatingBarPlanFetchRunsImmediatelyForQuotaGate() {
        XCTAssertEqual(StartupWarmupPolicy.floatingBarPlanFetchDelay, 0)
    }

    func testMCPKeyWarmupRunsAfterInteractiveLoadButBeforeDeferredWarmup() {
        XCTAssertGreaterThan(
            StartupWarmupPolicy.mcpKeyWarmupDelay,
            StartupWarmupPolicy.immediateWarmupDelay
        )
        XCTAssertLessThan(
            StartupWarmupPolicy.mcpKeyWarmupDelay,
            StartupWarmupPolicy.deferredWarmupDelay
        )
    }

    func testInitialSettingsSyncWaitsUntilAfterDeferredWarmupStarts() {
        XCTAssertGreaterThan(
            StartupWarmupPolicy.initialSettingsSyncDelay,
            StartupWarmupPolicy.deferredWarmupDelay
        )
    }

    func testInitialSettingsSyncRunsBeforeProactiveAssistantsStart() {
        XCTAssertLessThan(
            StartupWarmupPolicy.initialSettingsSyncDelay,
            StartupWarmupPolicy.proactiveAssistantsStartDelay
        )
    }

    func testAPIKeyFetchWaitsUntilAfterDashboardNetworkRefresh() {
        XCTAssertGreaterThan(
            StartupWarmupPolicy.apiKeyFetchDelay,
            StartupWarmupPolicy.dashboardNetworkRefreshDelay
        )
    }

    func testTranscriptionDeferralStartsAPIKeyFetchImmediately() throws {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let homeURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/MainWindow/DesktopHomeView.swift")
        let source = try String(contentsOf: homeURL, encoding: .utf8)

        guard let deferralRange = source.range(of: "DesktopHomeView: Deferring transcription — API keys not yet loaded"),
              let immediateFetchRange = source.range(of: "Task { await APIKeyService.shared.waitForKeys() }") else {
            return XCTFail("Transcription auto-start deferral must kick off API key fetch immediately")
        }

        XCTAssertGreaterThan(
            immediateFetchRange.lowerBound,
            deferralRange.lowerBound,
            "Immediate key fetch should be started from the transcription deferral branch"
        )
    }

    func testAPIKeyFetchFailureDoesNotBlockFutureWaiters() throws {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let serviceURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/APIKeyService.swift")
        let source = try String(contentsOf: serviceURL, encoding: .utf8)

        XCTAssertTrue(
            source.contains("fetchTask = nil"),
            "A failed API key fetch must clear fetchTask so later Calendar waits can retry"
        )
        XCTAssertTrue(
            source.contains("key fetch completed without loaded keys, retrying once"),
            "waitForKeys() must retry after awaiting a failed completed fetch"
        )
    }

    func testChatPromptContextWarmupWaitsUntilAfterDeferredWarmupStarts() {
        XCTAssertGreaterThan(
            StartupWarmupPolicy.chatPromptContextWarmupDelay,
            StartupWarmupPolicy.deferredWarmupDelay
        )
    }

    func testWarmupScheduleStateRunsServiceWarmupWhenDatabaseIsUnavailable() {
        var state = StartupWarmupScheduleState()

        XCTAssertTrue(state.reserveServiceWarmup())
        XCTAssertFalse(state.reserveServiceWarmup())
        XCTAssertFalse(state.reserveDatabaseWarmup(dbAvailable: false))

        XCTAssertTrue(state.reserveDatabaseWarmup(dbAvailable: true))
        XCTAssertFalse(state.reserveDatabaseWarmup(dbAvailable: true))
    }

    func testWarmupScheduleStateCanRetryServiceWarmupAfterRelease() {
        var state = StartupWarmupScheduleState()

        XCTAssertTrue(state.reserveServiceWarmup())
        XCTAssertFalse(state.reserveServiceWarmup())

        state.releaseServiceWarmup()

        XCTAssertTrue(state.reserveServiceWarmup())
    }

    func testWarmupScheduleStateCanRetryDatabaseWarmupAfterRelease() {
        var state = StartupWarmupScheduleState()

        XCTAssertTrue(state.reserveDatabaseWarmup(dbAvailable: true))
        XCTAssertFalse(state.reserveDatabaseWarmup(dbAvailable: true))

        state.releaseDatabaseWarmup()

        XCTAssertTrue(state.reserveDatabaseWarmup(dbAvailable: true))
    }

    func testTasksPageFirstUseLoadsWhenStoreHasNoRenderedTasks() {
        XCTAssertTrue(
            TasksPageFirstUseLoadPolicy.shouldLoadTasks(hasRenderedTasks: false, isLoading: false)
        )
        XCTAssertFalse(
            TasksPageFirstUseLoadPolicy.shouldLoadTasks(hasRenderedTasks: true, isLoading: false)
        )
        XCTAssertFalse(
            TasksPageFirstUseLoadPolicy.shouldLoadTasks(hasRenderedTasks: false, isLoading: true)
        )
    }

    func testRetryableDelayedStartGateAllowsFutureAttemptsAfterAttemptFinishes() {
        var gate = RetryableDelayedStartGate()

        XCTAssertTrue(gate.reserve())
        XCTAssertFalse(gate.reserve())

        gate.finishAttempt()

        XCTAssertTrue(gate.reserve())
    }

    func testFileIndexingBackfillMarksCompleteOnlyAfterScanCompletes() {
        var backfill = DelayedFileIndexingBackfillState()

        XCTAssertTrue(backfill.reserveIfNeeded(hasCompletedBackfill: false))
        XCTAssertFalse(backfill.shouldMarkComplete)

        backfill.markScanCompleted()

        XCTAssertTrue(backfill.shouldMarkComplete)
        XCTAssertFalse(backfill.reserveIfNeeded(hasCompletedBackfill: true))
    }

    func testFileIndexingBackfillCanRescheduleAfterReservationRelease() {
        var backfill = DelayedFileIndexingBackfillState()

        XCTAssertTrue(backfill.reserveIfNeeded(hasCompletedBackfill: false))
        XCTAssertFalse(backfill.reserveIfNeeded(hasCompletedBackfill: false))

        backfill.releaseReservation()

        XCTAssertFalse(backfill.shouldMarkComplete)
        XCTAssertTrue(backfill.reserveIfNeeded(hasCompletedBackfill: false))
    }

    func testSessionScopeRejectsSignedOutAndMismatchedUsers() {
        let scope = StartupWarmupSessionScope(userId: "user-a")

        XCTAssertTrue(scope.matches(currentUserId: "user-a", isSignedIn: true))
        XCTAssertFalse(scope.matches(currentUserId: "user-b", isSignedIn: true))
        XCTAssertFalse(scope.matches(currentUserId: "user-a", isSignedIn: false))
        XCTAssertFalse(StartupWarmupSessionScope(userId: nil).matches(currentUserId: "user-a", isSignedIn: true))
    }

    func testStartupWarmupCoordinatorUsesSessionScopedTasks() throws {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let sourceURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/StartupWarmupCoordinator.swift")
        let source = try String(contentsOf: sourceURL, encoding: .utf8)

        XCTAssertTrue(source.contains("private var sessionTasks: [StartupWarmupTaskID: Task<Void, Never>]"))
        XCTAssertTrue(source.contains("scheduleSessionWarmup(id: .mcpKeyWarmup"))
        XCTAssertTrue(source.contains("guard self.isCurrentSession(scope) else"))
        XCTAssertTrue(source.contains("guard isCurrentSession(scope) else { return }"))
        XCTAssertTrue(source.contains("sessionTasks.values.forEach { $0.cancel() }"))
        XCTAssertTrue(source.contains("sessionTasks.removeAll()"))
    }

    func testDelayedDesktopHomeWarmupsUseSessionScopedCoordinator() throws {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let sourceURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/MainWindow/DesktopHomeView.swift")
        let source = try String(contentsOf: sourceURL, encoding: .utf8)

        XCTAssertTrue(source.contains("id: .agentVMProvisioning"))
        XCTAssertTrue(source.contains("id: .conversationWarmup"))
        XCTAssertTrue(source.contains("id: .initialFileIndexing"))
        XCTAssertTrue(source.contains("id: .proactiveAssistantsStart"))
        XCTAssertTrue(source.contains("viewModelContainer.resetStartupState()"))
        XCTAssertTrue(source.contains("resetSessionScopedStartupWarmups(preserveCrispReadState: true)"))
        XCTAssertTrue(source.contains("resetSessionScopedStartupWarmups(preserveCrispReadState: false)"))
        XCTAssertTrue(source.contains("CrispManager.shared.stop(preserveReadState: preserveCrispReadState)"))
        XCTAssertTrue(source.contains("NSApplication.willTerminateNotification"))
    }

    @MainActor
    func testTasksStoreStartupMaintenanceSchedulesOnceForFirstUseLoadPath() async {
        let store = TasksStore.shared
        store.resetSessionState()
        let counter = StartupMaintenanceCounter()

        store.scheduleStartupMaintenanceIfNeeded(
            fullSyncAndRetry: { await counter.recordFullSyncAndRetry() },
            relevanceBackfill: { await counter.recordRelevanceBackfill() }
        )

        try? await Task.sleep(nanoseconds: 50_000_000)
        XCTAssertTrue(store.hasScheduledStartupMaintenance)
        let initialFullSyncAndRetryCount = await counter.fullSyncAndRetryCount
        let initialRelevanceBackfillCount = await counter.relevanceBackfillCount
        XCTAssertEqual(initialFullSyncAndRetryCount, 1)
        XCTAssertEqual(initialRelevanceBackfillCount, 1)

        store.scheduleStartupMaintenanceIfNeeded(
            fullSyncAndRetry: { await counter.recordFullSyncAndRetry() },
            relevanceBackfill: { await counter.recordRelevanceBackfill() }
        )

        try? await Task.sleep(nanoseconds: 50_000_000)
        let finalFullSyncAndRetryCount = await counter.fullSyncAndRetryCount
        let finalRelevanceBackfillCount = await counter.relevanceBackfillCount
        XCTAssertEqual(finalFullSyncAndRetryCount, 1)
        XCTAssertEqual(finalRelevanceBackfillCount, 1)
    }

    func testDashboardOnlyActivationRefreshDoesNotRequireTasksPageHydration() throws {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let sourceURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/Stores/TasksStore.swift")
        let source = try String(contentsOf: sourceURL, encoding: .utf8)

        guard let dashboardRefreshRange = source.range(of: "await refreshDashboardTasksFromServer()"),
              let hydrationGuardRange = source.range(of: "guard hasLoadedIncomplete else") else {
            return XCTFail("TasksStore.refreshTasksIfNeeded must refresh dashboard slices before requiring Tasks page hydration")
        }

        XCTAssertLessThan(
            hydrationGuardRange.lowerBound,
            dashboardRefreshRange.lowerBound,
            "Dashboard-only activation/Cmd+R refresh must fall back to the scoped dashboard refresh from the Tasks page hydration guard"
        )
    }

    func testDatabaseWarmupSchedulesTaskMaintenanceWithoutTasksPageHydration() throws {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let sourceURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/StartupWarmupCoordinator.swift")
        let source = try String(contentsOf: sourceURL, encoding: .utf8)

        guard let maintenanceRange = source.range(of: "tasksStore.scheduleStartupMaintenanceIfNeeded()"),
              let lifecycleRange = source.range(of: "DATA LOAD: DB lifecycle warmup") else {
            return XCTFail("Startup warmup must schedule task maintenance before DB lifecycle warmup")
        }

        XCTAssertLessThan(
            maintenanceRange.lowerBound,
            lifecycleRange.lowerBound,
            "Startup maintenance must run from the startup warmup path, not only after opening Tasks"
        )
    }

    func testStartupResetClearsPerUserMemoriesState() throws {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let containerURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/ViewModelContainer.swift")
        let memoriesURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/MainWindow/Pages/MemoriesPage.swift")
        let containerSource = try String(contentsOf: containerURL, encoding: .utf8)
        let memoriesSource = try String(contentsOf: memoriesURL, encoding: .utf8)

        XCTAssertTrue(
            containerSource.contains("memoriesViewModel.resetSessionState()"),
            "Startup reset must clear MemoriesViewModel so account switches cannot show the previous user's memories"
        )
        XCTAssertTrue(
            memoriesSource.contains("hasLoadedInitially = false"),
            "Memories reset must release the first-use load guard for the next signed-in user"
        )
        XCTAssertTrue(
            memoriesSource.contains("memories = []"),
            "Memories reset must clear any previous user's published memory rows"
        )
    }

    func testStartupResetClearsPerUserDashboardState() throws {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let containerURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/ViewModelContainer.swift")
        let dashboardURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/MainWindow/Pages/DashboardPage.swift")
        let containerSource = try String(contentsOf: containerURL, encoding: .utf8)
        let dashboardSource = try String(contentsOf: dashboardURL, encoding: .utf8)

        XCTAssertTrue(
            containerSource.contains("dashboardViewModel.resetSessionState()"),
            "Startup reset must clear DashboardViewModel so account switches cannot show the previous user's score or goals"
        )
        XCTAssertTrue(
            dashboardSource.contains("scoreResponse = nil"),
            "Dashboard reset must clear the previous user's score"
        )
        XCTAssertTrue(
            dashboardSource.contains("goals = []"),
            "Dashboard reset must clear the previous user's goals"
        )
    }

    func testStartupResetClearsPerUserAppProviderState() throws {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let containerURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/ViewModelContainer.swift")
        let appProviderURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/Providers/AppProvider.swift")
        let containerSource = try String(contentsOf: containerURL, encoding: .utf8)
        let appProviderSource = try String(contentsOf: appProviderURL, encoding: .utf8)

        XCTAssertTrue(
            containerSource.contains("appProvider.resetSessionState()"),
            "Startup reset must clear AppProvider so account switches cannot show the previous user's app state"
        )
        XCTAssertTrue(
            appProviderSource.contains("func resetSessionState()"),
            "AppProvider must expose an explicit session reset hook"
        )
        for requiredReset in [
            "apps = []",
            "popularApps = []",
            "integrationApps = []",
            "chatApps = []",
            "summaryApps = []",
            "notificationApps = []",
            "enabledApps = []",
            "categories = []",
            "capabilities = []",
            "marketplaceApps = []",
            "filteredAppsCache = [:]",
            "filteredAppsCacheOrder = []",
            "appLoadingStates = [:]",
            "filteredApps = nil",
            "hasMoreFilteredApps = false",
            "filteredAppsOffset = 0",
            "searchQuery = \"\"",
            "selectedCategory = nil",
            "selectedCapability = nil",
            "showInstalledOnly = false",
            "errorMessage = nil"
        ] {
            XCTAssertTrue(
                appProviderSource.contains(requiredReset),
                "AppProvider reset must include \(requiredReset)"
            )
        }
    }

    func testAuthSignInFetchesFloatingBarPlanImmediately() throws {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let authURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/AuthService.swift")
        let source = try String(contentsOf: authURL, encoding: .utf8)

        XCTAssertGreaterThanOrEqual(
            source.components(separatedBy: "FloatingBarUsageLimiter.shared.fetchPlan()").count - 1,
            2,
            "Both Apple and web OAuth sign-in paths must fetch quota immediately after successful sign-in"
        )
    }

    func testChatProviderClearsPromptContextOnSignOut() throws {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let chatURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/Providers/ChatProvider.swift")
        let source = try String(contentsOf: chatURL, encoding: .utf8)

        XCTAssertTrue(
            source.contains("resetSessionStateForAuthChange()"),
            "Sign-out must clear ChatProvider prompt caches and visible chat state"
        )
        XCTAssertTrue(
            source.contains("memoriesLoaded = false"),
            "ChatProvider auth reset must release the memories-loaded guard"
        )
        XCTAssertTrue(
            source.contains("await self.resolvedAgentClient().clearOwnerState()"),
            "Sign-out must clear the previous owner's kernel sessions and context snapshots"
        )
    }
}

private actor StartupMaintenanceCounter {
    private var fullSyncAndRetryTotal = 0
    private var relevanceBackfillTotal = 0

    var fullSyncAndRetryCount: Int { fullSyncAndRetryTotal }
    var relevanceBackfillCount: Int { relevanceBackfillTotal }

    func recordFullSyncAndRetry() {
        fullSyncAndRetryTotal += 1
    }

    func recordRelevanceBackfill() {
        relevanceBackfillTotal += 1
    }
}
