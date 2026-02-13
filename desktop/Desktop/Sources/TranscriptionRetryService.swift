import Foundation

/// Background service for retrying failed transcription uploads
/// Runs a periodic timer to check for pending/failed sessions and attempt upload
class TranscriptionRetryService {
    static let shared = TranscriptionRetryService()

    private var retryTimer: Timer?
    private var isProcessing = false
    private let retryInterval: TimeInterval = 60  // Check every 60 seconds
    private let maxRetries = 5

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
                log("TranscriptionRetryService: Found \(pendingSessions.count) pending sessions to upload")
                for session in pendingSessions {
                    await uploadSession(session)
                }
            }

            // Also check for failed sessions that can be retried
            let failedSessions = try await TranscriptionStorage.shared.getFailedSessions(maxRetries: maxRetries)
            if !failedSessions.isEmpty {
                log("TranscriptionRetryService: Found \(failedSessions.count) failed sessions to retry")
                for session in failedSessions {
                    if session.isReadyForRetry() {
                        await uploadSession(session)
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
        guard !isProcessing else {
            log("TranscriptionRetryService: Already processing, skipping")
            return
        }

        isProcessing = true
        defer { isProcessing = false }

        do {
            // Get pending sessions
            let pendingSessions = try await TranscriptionStorage.shared.getPendingUploadSessions()
            for session in pendingSessions {
                await uploadSession(session)
            }

            // Get failed sessions that are ready for retry
            let failedSessions = try await TranscriptionStorage.shared.getFailedSessions(maxRetries: maxRetries)
            for session in failedSessions {
                if session.isReadyForRetry() {
                    await uploadSession(session)
                }
            }

        } catch {
            logError("TranscriptionRetryService: Queue processing failed", error: error)
        }
    }

    // MARK: - Upload

    /// Upload a session to the backend
    private func uploadSession(_ session: TranscriptionSessionRecord) async {
        guard let sessionId = session.id else { return }

        log("TranscriptionRetryService: Uploading session \(sessionId) (retryCount: \(session.retryCount))")

        do {
            // Get session with segments
            guard let sessionWithSegments = try await TranscriptionStorage.shared.getSessionWithSegments(id: sessionId) else {
                log("TranscriptionRetryService: Session \(sessionId) not found, deleting")
                try? await TranscriptionStorage.shared.deleteSession(id: sessionId)
                return
            }

            // Check if we have content
            guard sessionWithSegments.hasContent else {
                log("TranscriptionRetryService: Session \(sessionId) has no segments, deleting")
                try? await TranscriptionStorage.shared.deleteSession(id: sessionId)
                return
            }

            // Mark as uploading
            try await TranscriptionStorage.shared.markSessionUploading(id: sessionId)

            // Convert segments to API format
            let apiSegments = sessionWithSegments.segments.map { segment in
                APIClient.TranscriptSegmentRequest(
                    text: segment.text,
                    speaker: "SPEAKER_\(String(format: "%02d", segment.speaker))",
                    speakerId: segment.speaker,
                    isUser: segment.speaker == 0,
                    start: segment.startTime,
                    end: segment.endTime
                )
            }

            // Determine conversation source
            let source = ConversationSource(rawValue: session.source) ?? .desktop

            // Upload to backend
            let response = try await APIClient.shared.createConversationFromSegments(
                segments: apiSegments,
                startedAt: session.startedAt,
                finishedAt: session.finishedAt ?? Date(),
                source: source,
                language: session.language,
                timezone: session.timezone,
                inputDeviceName: session.inputDeviceName
            )

            log("TranscriptionRetryService: Session \(sessionId) uploaded successfully (backendId: \(response.id))")

            // Mark as completed
            try await TranscriptionStorage.shared.markSessionCompleted(id: sessionId, backendId: response.id)

            // Track analytics
            let durationSeconds = Int(session.finishedAt?.timeIntervalSince(session.startedAt) ?? 0)
            await AnalyticsManager.shared.conversationCreated(
                conversationId: response.id,
                source: session.source,
                durationSeconds: durationSeconds
            )

        } catch {
            logError("TranscriptionRetryService: Upload failed for session \(sessionId)", error: error)

            // Increment retry count and mark as failed
            do {
                try await TranscriptionStorage.shared.incrementRetryCount(id: sessionId)
                try await TranscriptionStorage.shared.markSessionFailed(id: sessionId, error: error.localizedDescription)
            } catch {
                logError("TranscriptionRetryService: Failed to update session status", error: error)
            }
        }
    }

}
