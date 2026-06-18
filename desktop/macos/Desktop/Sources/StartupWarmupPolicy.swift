import Foundation

struct StartupWarmupScheduleState {
    private var didScheduleServiceWarmup = false
    private var didScheduleDatabaseWarmup = false

    mutating func reserveServiceWarmup() -> Bool {
        guard !didScheduleServiceWarmup else { return false }
        didScheduleServiceWarmup = true
        return true
    }

    mutating func reserveDatabaseWarmup(dbAvailable: Bool) -> Bool {
        guard dbAvailable, !didScheduleDatabaseWarmup else { return false }
        didScheduleDatabaseWarmup = true
        return true
    }
}

struct RetryableDelayedStartGate {
    private var isAttemptReserved = false

    mutating func reserve() -> Bool {
        guard !isAttemptReserved else { return false }
        isAttemptReserved = true
        return true
    }

    mutating func finishAttempt() {
        isAttemptReserved = false
    }
}

struct DelayedFileIndexingBackfillState {
    private var isScheduled = false
    private(set) var shouldMarkComplete = false

    mutating func reserveIfNeeded(hasCompletedBackfill: Bool) -> Bool {
        guard !hasCompletedBackfill, !isScheduled else { return false }
        isScheduled = true
        shouldMarkComplete = false
        return true
    }

    mutating func markScanCompleted() {
        isScheduled = false
        shouldMarkComplete = true
    }
}

enum TasksPageFirstUseLoadPolicy {
    static func shouldLoadTasks(hasRenderedTasks: Bool, isLoading: Bool) -> Bool {
        !hasRenderedTasks && !isLoading
    }
}

enum StartupWarmupPolicy {
    static let immediateWarmupDelay: TimeInterval = 0.25
    static let deferredWarmupDelay: TimeInterval = 2.0
    static let databaseRetryInitialDelay: TimeInterval = 1.0
    static let databaseRetryMaxDelay: TimeInterval = 30.0
    static let dashboardNetworkRefreshDelay: TimeInterval = 4.0
    static let initialSettingsSyncDelay: TimeInterval = 5.0
    static let apiKeyFetchDelay: TimeInterval = 9.0
    static let chatPromptContextWarmupDelay: TimeInterval = 10.0
    static let screenActivitySyncInitialDelay: TimeInterval = 10.0
    static let floatingBarPlanFetchDelay: TimeInterval = 12.0
    static let crispInitialPollDelay: TimeInterval = 15.0
    static let agentVMProvisioningDelay: TimeInterval = 20.0
    static let proactiveAssistantsStartDelay: TimeInterval = 30.0
    static let conversationWarmupDelay: TimeInterval = 6.0
    static let transcriptionRetryRecoveryDelay: TimeInterval = 8.0
    static let recurringTaskSchedulerInitialDelay: TimeInterval = 12.0
    static let initialFileIndexingDelay: TimeInterval = 45.0
}
