import Foundation

/// Background service for retrying failed transcription uploads
/// Runs a periodic timer to check for pending/failed sessions and attempt upload
class TranscriptionRetryService {
    static let shared = TranscriptionRetryService()

    private var retryTimer: Timer?
    private var isProcessing = false
    private let retryInterval: TimeInterval = 60  // Check every 60 seconds
    private let maxRetries = 5
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
                        try await TranscriptionStorage.shared.finishSession(id: session.id!)
                    }
                }
            }

            // Now process any pending sessions
            let pendingSessions = try await TranscriptionStorage.shared.getPendingUploadSessions()
            if !pendingSessions.isEmpty {
                log("TranscriptionRetryService: Found \(pendingSessions.count) pending sessions to reconcile")
                for session in pendingSessions {
                    await reconcileSession(session)
                }
            }

            // Recover sessions stuck in 'uploading' (app quit/crash during upload, or markSessionCompleted failed)
            let stuckUploadingSessions = try await TranscriptionStorage.shared.getStuckUploadingSessions(olderThan: 300)
            if !stuckUploadingSessions.isEmpty {
                log("TranscriptionRetryService: Found \(stuckUploadingSessions.count) stuck uploading sessions")
                for session in stuckUploadingSessions {
                    await recoverStuckSession(session)
                }
            }

            // Also check for failed sessions that can be retried
            let failedSessions = try await TranscriptionStorage.shared.getFailedSessions(maxRetries: maxRetries)
            if !failedSessions.isEmpty {
                log("TranscriptionRetryService: Found \(failedSessions.count) failed sessions to retry")
                for session in failedSessions {
                    if session.isReadyForRetry() {
                        await reconcileSession(session)
                    } else {
                        log("TranscriptionRetryService: Session \(session.id!) not ready for retry (backoff)")
                    }
                }
            }

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
            // Get pending sessions
            let pendingSessions = try await TranscriptionStorage.shared.getPendingUploadSessions()
            consecutiveDBFailures = 0 // DB query succeeded, reset counter

            for session in pendingSessions {
                await reconcileSession(session)
            }

            // Recover sessions stuck in 'uploading' for more than 5 minutes
            let stuckSessions = try await TranscriptionStorage.shared.getStuckUploadingSessions(olderThan: 300)
            for session in stuckSessions {
                await recoverStuckSession(session)
            }

            // Get failed sessions that are ready for retry
            let failedSessions = try await TranscriptionStorage.shared.getFailedSessions(maxRetries: maxRetries)
            for session in failedSessions {
                if session.isReadyForRetry() {
                    await reconcileSession(session)
                }
            }

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

    // MARK: - Stuck Session Recovery

    /// Recover a session stuck in 'uploading' — check if backend already has it before re-uploading
    private func recoverStuckSession(_ session: TranscriptionSessionRecord) async {
        guard let sessionId = session.id else { return }

        log("TranscriptionRetryService: Recovering stuck session \(sessionId)")

        // Check if the backend already has a conversation for this time window
        // (upload succeeded but markSessionCompleted failed silently)
        do {
            let finishedAt = session.finishedAt ?? session.startedAt.addingTimeInterval(1)
            let existing = try await APIClient.shared.getConversations(
                limit: 5,
                startDate: session.startedAt.addingTimeInterval(-2),
                endDate: finishedAt.addingTimeInterval(2)
            )

            // Look for a desktop conversation with matching started_at/finished_at
            if let match = existing.first(where: { conv in
                guard let convStarted = conv.startedAt, let convFinished = conv.finishedAt else { return false }
                guard conv.source == .desktop else { return false }
                return abs(convStarted.timeIntervalSince(session.startedAt)) < 5
                    && abs(convFinished.timeIntervalSince(finishedAt)) < 5
            }) {
                log("TranscriptionRetryService: Session \(sessionId) already exists on backend as \(match.id), marking completed")
                try await TranscriptionStorage.shared.markSessionCompleted(id: sessionId, backendId: match.id)
                return
            }
        } catch {
            log("TranscriptionRetryService: Could not check backend for session \(sessionId), will re-upload: \(error.localizedDescription)")
        }

        // No match found — mark as pending so it gets re-uploaded
        log("TranscriptionRetryService: Session \(sessionId) not found on backend, marking as pending upload")
        do {
            try await TranscriptionStorage.shared.finishSession(id: sessionId)
        } catch {
            logError("TranscriptionRetryService: Failed to mark session \(sessionId) as pending", error: error)
        }
    }

    // MARK: - Reconciliation

    /// Reconcile a pending session with the backend.
    /// Since /v4/listen stores segments in Firestore as they stream, the backend already has the
    /// conversation data. We just need to find the matching backend conversation and mark local
    /// session as completed. No segment re-upload needed.
    private func reconcileSession(_ session: TranscriptionSessionRecord) async {
        guard let sessionId = session.id else { return }

        log("TranscriptionRetryService: Reconciling session \(sessionId) (retryCount: \(session.retryCount))")

        do {
            // Check if backend already has a conversation for this time window
            let finishedAt = session.finishedAt ?? session.startedAt.addingTimeInterval(1)
            if let existing = try? await APIClient.shared.getConversations(
                limit: 5,
                includeDiscarded: true,
                startDate: session.startedAt.addingTimeInterval(-5),
                endDate: finishedAt.addingTimeInterval(5)
            ), let match = existing.first(where: { conv in
                guard let convStarted = conv.startedAt else { return false }
                // Must be a desktop conversation with matching start time
                guard conv.source == .desktop else { return false }
                return abs(convStarted.timeIntervalSince(session.startedAt)) < 10
            }) {
                log("TranscriptionRetryService: Session \(sessionId) found on backend as \(match.id), marking completed")
                try await TranscriptionStorage.shared.markSessionCompleted(id: sessionId, backendId: match.id)
                return
            }

            // No matching conversation found on backend.
            // Do NOT call force-process here — it acts on the user's current in-progress
            // conversation which may belong to another device or a new recording session.
            // Force-process is only safe immediately after stopping (in AppState.stopTranscription).
            // The retry service only reconciles by timestamp; if no match exists yet, retry later.
            log("TranscriptionRetryService: No backend match for session \(sessionId), will retry")
            try await TranscriptionStorage.shared.incrementRetryCount(id: sessionId)
            try await TranscriptionStorage.shared.markSessionFailed(
                id: sessionId, error: "No matching desktop conversation found on backend")

            // Fire error event after all retries exhausted
            if session.retryCount + 1 >= maxRetries {
                await AnalyticsManager.shared.recordingError(
                    error: "Session \(sessionId) could not be reconciled after \(maxRetries) attempts")
            }

        } catch {
            logError("TranscriptionRetryService: Reconciliation failed for session \(sessionId)", error: error)
        }
    }

}
