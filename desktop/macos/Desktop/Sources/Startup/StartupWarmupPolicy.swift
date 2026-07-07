import Foundation

struct StartupWarmupScheduleState {
    private var didScheduleServiceWarmup = false
    private var didScheduleDatabaseWarmup = false

    mutating func reserveServiceWarmup() -> Bool {
        guard !didScheduleServiceWarmup else { return false }
        didScheduleServiceWarmup = true
        return true
    }

    mutating func releaseServiceWarmup() {
        didScheduleServiceWarmup = false
    }

    mutating func reserveDatabaseWarmup(dbAvailable: Bool) -> Bool {
        guard dbAvailable, !didScheduleDatabaseWarmup else { return false }
        didScheduleDatabaseWarmup = true
        return true
    }

    mutating func releaseDatabaseWarmup() {
        didScheduleDatabaseWarmup = false
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

enum StartupWarmupTaskID: Hashable {
    case serviceWarmup
    case databaseWarmup
    case dashboardNetworkRefresh
    case chatPromptContextWarmup
    case mcpKeyWarmup
    case databaseRetry
    case crispInitialPoll
    case agentVMProvisioning
    case conversationWarmup
    case initialFileIndexing
    case proactiveAssistantsStart
}

struct StartupWarmupSessionScope: Equatable {
    let userId: String?

    func matches(currentUserId: String?, isSignedIn: Bool) -> Bool {
        isSignedIn && userId != nil && currentUserId == userId
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

    mutating func releaseReservation() {
        isScheduled = false
        shouldMarkComplete = false
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
    static let mcpKeyWarmupDelay: TimeInterval = 0.5
    static let dashboardNetworkRefreshDelay: TimeInterval = 4.0
    static let initialSettingsSyncDelay: TimeInterval = 5.0
    static let apiKeyFetchDelay: TimeInterval = 9.0
    static let chatPromptContextWarmupDelay: TimeInterval = 10.0
    static let screenActivitySyncInitialDelay: TimeInterval = 10.0
    static let floatingBarPlanFetchDelay: TimeInterval = 0.0
    static let crispInitialPollDelay: TimeInterval = 15.0
    static let agentVMProvisioningDelay: TimeInterval = 20.0
    static let proactiveAssistantsStartDelay: TimeInterval = 6.0
    static let conversationWarmupDelay: TimeInterval = 6.0
    static let transcriptionRetryRecoveryDelay: TimeInterval = 8.0
    static let recurringTaskSchedulerInitialDelay: TimeInterval = 12.0
    static let initialFileIndexingDelay: TimeInterval = 45.0

    /// Remaining delay before proactive monitoring may start, measured from a
    /// launch anchor rather than from the triggering event. The warmup delay
    /// exists to keep capture out of the busy launch window, so late triggers
    /// (API-key load, app re-activation) must not re-pay the full delay —
    /// that compounding is what made the Capture pill sit "paused" for
    /// 30-60+ seconds after launch. Negative elapsed values (clock changes)
    /// clamp to the full delay.
    static func remainingProactiveAssistantsStartDelay(elapsedSinceLaunch: TimeInterval) -> TimeInterval {
        max(0, proactiveAssistantsStartDelay - max(0, elapsedSinceLaunch))
    }
}
