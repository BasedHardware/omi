import Foundation

/// Background service for retrying failed transcription uploads
/// Runs a periodic timer to check for pending/failed sessions and attempt upload
class TranscriptionRetryService {
    static let shared = TranscriptionRetryService()

    private var retryTimer: Timer?
    private var isProcessing = false
    private let retryInterval: TimeInterval = 60  // Check every 60 seconds
    private var consecutiveDBFailures = 0
    private let maxConsecutiveDBFailures = 3

    private init() {}

    // MARK: - Service Lifecycle

    /// Start the retry service (call on app launch)
    func start() {
        guard retryTimer == nil else { return }

        log("TranscriptionRetryService: Starting retry timer (interval: \(retryInterval)s)")

        retryTimer = Timer.scheduledTimer(withTimeInterval: retryInterval, repeats: true) { [weak self] _ in
            Task {
                await self?.processRetryQueue()
            }
        }
    }

    /// Stop the retry service (call on app termination)
    func stop() {
        log("TranscriptionRetryService: Stopping")
        retryTimer?.invalidate()
        retryTimer = nil
    }

    // MARK: - Recovery

    /// Recover pending transcriptions on app launch
    /// Call this after database initialization
    func recoverPendingTranscriptions() async {
        log("TranscriptionRetryService: Checking for pending transcriptions...")

        do {
            // First, find any crashed sessions (status = 'recording' from previous run)
            let crashedSessions = try await TranscriptionStorage.shared.getCrashedSessions()
            if !crashedSessions.isEmpty {
                log("TranscriptionRetryService: Found \(crashedSessions.count) crashed sessions")
                for session in crashedSessions {
                    // Skip sessions that are too recent - they might be actively recording
                    // (race condition: recovery runs before segments arrive)
                    let sessionAge = Date().timeIntervalSince(session.createdAt)
                    if sessionAge < 30 {
                        log("TranscriptionRetryService: Skipping recent session \(session.id!) (age: \(String(format: "%.1f", sessionAge))s)")
                        continue
                    }

                    // Check if session has segments - if not, delete it
                    let segmentCount = try await TranscriptionStorage.shared.getSegmentCount(sessionId: session.id!)
                    if segmentCount == 0 {
                        log("TranscriptionRetryService: Deleting empty crashed session \(session.id!)")
                        try await TranscriptionStorage.shared.deleteSession(id: session.id!)
                    } else {
                        // Mark as pending upload so it will be retried
                        log("TranscriptionRetryService: Marking crashed session \(session.id!) as pending upload (\(segmentCount) segments)")
                        try await TranscriptionStorage.shared.finishSession(id: session.id!, reason: .crashRecovery)
                    }
                }
            }

            await ConversationFinalizationService.shared.recoverPendingFinalizations()

            // Log stats
            let stats = try await TranscriptionStorage.shared.getStats()
            log("TranscriptionRetryService: Stats - total=\(stats.totalSessions), pending=\(stats.pendingCount), failed=\(stats.failedCount), completed=\(stats.completedCount)")

        } catch {
            logError("TranscriptionRetryService: Recovery failed", error: error)
        }
    }

    // MARK: - Retry Queue Processing

    /// Process the retry queue (called periodically by timer)
    private func processRetryQueue() async {
        // Skip if user is signed out (tokens are cleared)
        guard await AuthState.shared.isSignedIn else { return }
        guard !isProcessing else {
            log("TranscriptionRetryService: Already processing, skipping")
            return
        }

        isProcessing = true
        defer { isProcessing = false }

        do {
            _ = try await TranscriptionStorage.shared.getStats()
            consecutiveDBFailures = 0 // DB query succeeded, reset counter
            await ConversationFinalizationService.shared.recoverPendingFinalizations()

        } catch {
            consecutiveDBFailures += 1
            // Report to RewindDatabase for runtime corruption detection
            await RewindDatabase.shared.reportQueryError(error)
            if consecutiveDBFailures >= maxConsecutiveDBFailures {
                log("TranscriptionRetryService: \(consecutiveDBFailures) consecutive DB failures, stopping timer to avoid error flood")
                stop()
            } else {
                logError("TranscriptionRetryService: Queue processing failed (\(consecutiveDBFailures)/\(maxConsecutiveDBFailures))", error: error)
            }
        }
    }

}
