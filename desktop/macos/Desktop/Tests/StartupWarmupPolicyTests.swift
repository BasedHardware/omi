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
        XCTAssertEqual(await counter.fullSyncAndRetryCount, 1)
        XCTAssertEqual(await counter.relevanceBackfillCount, 1)

        store.scheduleStartupMaintenanceIfNeeded(
            fullSyncAndRetry: { await counter.recordFullSyncAndRetry() },
            relevanceBackfill: { await counter.recordRelevanceBackfill() }
        )

        try? await Task.sleep(nanoseconds: 50_000_000)
        XCTAssertEqual(await counter.fullSyncAndRetryCount, 1)
        XCTAssertEqual(await counter.relevanceBackfillCount, 1)
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
