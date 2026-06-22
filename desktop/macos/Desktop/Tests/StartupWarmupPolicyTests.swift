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

    func testFloatingBarPlanFetchWaitsUntilAfterDeferredWarmupStarts() {
        XCTAssertGreaterThan(
            StartupWarmupPolicy.floatingBarPlanFetchDelay,
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
}
