import BackgroundTasks
import Foundation
import OmiService

/// Background refresh and processing (`BGTaskScheduler`). Identifiers are the bundle id plus
/// `.refresh` / `.processing`, listed in Info.plist (`BGTaskSchedulerPermittedIdentifiers`). The
/// work itself is `BackgroundWork` (sync, upload pending recordings, refresh lists).
@MainActor
enum BackgroundTasks {
    static var refreshID: String {
        (Bundle.main.bundleIdentifier ?? "omi") + ".refresh"
    }

    static var processingID: String {
        (Bundle.main.bundleIdentifier ?? "omi") + ".processing"
    }

    /// iOS wakes the app for these at most this often (a hint; the system decides).
    static let refreshInterval: TimeInterval = 30 * 60

    /// At launch, before the app finishes launching (iOS requires it then).
    static func register(_ work: BackgroundWork) {
        for (identifier, kind) in [(refreshID, BackgroundWork.Kind.refresh), (processingID, .processing)] {
            BGTaskScheduler.shared.register(forTaskWithIdentifier: identifier, using: .main) { task in
                MainActor.assumeIsolated { run(task, kind: kind, work: work) }
            }
        }
    }

    /// When the app goes to the background: the next refresh, plus processing while recordings wait.
    static func schedule(pendingRecordings: Bool) {
        scheduleRefresh()
        guard pendingRecordings else {
            BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: processingID)
            return
        }
        let processing = BGProcessingTaskRequest(identifier: processingID)
        processing.requiresNetworkConnectivity = true
        processing.requiresExternalPower = false
        try? BGTaskScheduler.shared.submit(processing)
    }

    private static func scheduleRefresh() {
        let refresh = BGAppRefreshTaskRequest(identifier: refreshID)
        refresh.earliestBeginDate = Date(timeIntervalSinceNow: refreshInterval)
        try? BGTaskScheduler.shared.submit(refresh)
    }

    private static func run(_ task: BGTask, kind: BackgroundWork.Kind, work: BackgroundWork) {
        // A refresh schedules the next one, as Apple recommends.
        if kind == .refresh { scheduleRefresh() }
        let job = Task { @MainActor in
            let done = await work.run(kind)
            task.setTaskCompleted(success: done)
        }
        task.expirationHandler = { job.cancel() }
    }
}
