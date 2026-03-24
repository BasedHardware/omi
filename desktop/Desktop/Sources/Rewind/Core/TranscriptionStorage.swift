import Foundation
import GRDB

/// Actor-based storage manager for transcription sessions and segments
/// Provides crash-safe persistence for transcription data during recording
actor TranscriptionStorage {
    static let shared = TranscriptionStorage()

    private var _dbQueue: DatabasePool?
    private var isInitialized = false

    private init() {}

    /// Invalidate cached DB queue (called on user switch / sign-out)
    func invalidateCache() {
        _dbQueue = nil
        isInitialized = false
    }

    /// Ensure database is initialized before use
    private func ensureInitialized() async throws -> DatabasePool {
        if let db = _dbQueue {
            return db
        }

        // Initialize RewindDatabase which creates our tables via migrations
        do {
            try await RewindDatabase.shared.initialize()
        } catch {
            log("TranscriptionStorage: Database initialization failed: \(error.localizedDescription)")
            throw error
        }

        guard let db = await RewindDatabase.shared.getDatabaseQueue() else {
            throw TranscriptionStorageError.databaseNotInitialized
        }

        _dbQueue = db
        isInitialized = true
        return db
    }

    // MARK: - Session Lifecycle

    /// Start a new transcription session
    /// - Returns: The new session's ID
    @discardableResult
    func startSession(
        source: String,
        language: String = "en",
        timezone: String = "UTC",
        inputDeviceName: String? = nil
    ) async throws -> Int64 {
        let db = try await ensureInitialized()

        let session = TranscriptionSessionRecord(
            startedAt: Date(),
            source: source,
            language: language,
            timezone: timezone,
            inputDeviceName: inputDeviceName,
            status: .recording
        )

        let record = try await db.write { database in
            try session.inserted(database)
        }

        log("TranscriptionStorage: Started session \(record.id ?? -1) (source: \(source), device: \(inputDeviceName ?? "unknown"))")
        return record.id!
    }

    /// Mark session as finished (recording complete, ready for upload)
    func finishSession(id: Int64) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try TranscriptionSessionRecord.fetchOne(database, key: id) else {
                throw TranscriptionStorageError.sessionNotFound
            }

            record.finishedAt = Date()
            record.status = .pendingUpload
            record.updatedAt = Date()
            try record.update(database)
        }

        log("TranscriptionStorage: Finished session \(id)")
    }

    /// Mark session as pending upload
    func markSessionPendingUpload(id: Int64) async throws {
        try await updateSessionStatus(id: id, status: .pendingUpload)
    }

    /// Mark session as currently uploading
    func markSessionUploading(id: Int64) async throws {
        try await updateSessionStatus(id: id, status: .uploading)
    }

    /// Mark session as completed (uploaded successfully)
    func markSessionCompleted(id: Int64, backendId: String) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try TranscriptionSessionRecord.fetchOne(database, key: id) else {
                throw TranscriptionStorageError.sessionNotFound
            }

            record.status = .completed
            record.backendId = backendId
            record.backendSynced = true
            record.updatedAt = Date()
            try record.update(database)
        }

        log("TranscriptionStorage: Completed session \(id) (backendId: \(backendId))")
    }

    /// Mark session as failed with error
    func markSessionFailed(id: Int64, error: String) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try TranscriptionSessionRecord.fetchOne(database, key: id) else {
                throw TranscriptionStorageError.sessionNotFound
            }

            record.status = .failed
            record.lastError = error
            record.updatedAt = Date()
            try record.update(database)
        }

        log("TranscriptionStorage: Failed session \(id) (error: \(error))")
    }

    /// Increment retry count for a session
    func incrementRetryCount(id: Int64) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try TranscriptionSessionRecord.fetchOne(database, key: id) else {
                throw TranscriptionStorageError.sessionNotFound
            }

            record.retryCount += 1
            record.updatedAt = Date()
            try record.update(database)
        }

        log("TranscriptionStorage: Incremented retry count for session \(id)")
    }

    /// Delete a session and its segments
    func deleteSession(id: Int64) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "DELETE FROM transcription_sessions WHERE id = ?",
                arguments: [id]
            )
        }

        log("TranscriptionStorage: Deleted session \(id)")
    }

    /// Update session status helper
    private func updateSessionStatus(id: Int64, status: TranscriptionSessionStatus) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try TranscriptionSessionRecord.fetchOne(database, key: id) else {
                throw TranscriptionStorageError.sessionNotFound
            }

            record.status = status
            record.updatedAt = Date()
            try record.update(database)
        }

        log("TranscriptionStorage: Updated session \(id) status to \(status.rawValue)")
    }

    // MARK: - Conversation Field Updates (by backendId)

    /// Update starred status by backend conversation ID
    func updateStarredByBackendId(_ backendId: String, starred: Bool) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "UPDATE transcription_sessions SET starred = ?, updatedAt = ? WHERE backendId = ?",
                arguments: [starred, Date(), backendId]
            )
        }
    }

    /// Update title by backend conversation ID
    func updateTitleByBackendId(_ backendId: String, title: String) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "UPDATE transcription_sessions SET title = ?, updatedAt = ? WHERE backendId = ?",
                arguments: [title, Date(), backendId]
            )
        }
    }

    /// Soft-delete by backend conversation ID
    func deleteByBackendId(_ backendId: String) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "UPDATE transcription_sessions SET deleted = 1, updatedAt = ? WHERE backendId = ?",
                arguments: [Date(), backendId]
            )
        }
    }

    /// Update folder by backend conversation ID
    func updateFolderByBackendId(_ backendId: String, folderId: String?) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "UPDATE transcription_sessions SET folderId = ?, updatedAt = ? WHERE backendId = ?",
                arguments: [folderId, Date(), backendId]
            )
        }
    }

    // MARK: - Segment Operations

    /// Append a new segment to a session
    @discardableResult
    func appendSegment(
        sessionId: Int64,
        speaker: Int,
        text: String,
        startTime: Double,
        endTime: Double
    ) async throws -> Int64 {
        let db = try await ensureInitialized()

        // Get the next segment order
        let segmentOrder = try await db.read { database -> Int in
            try Int.fetchOne(
                database,
                sql: "SELECT COALESCE(MAX(segmentOrder), -1) + 1 FROM transcription_segments WHERE sessionId = ?",
                arguments: [sessionId]
            ) ?? 0
        }

        let segment = TranscriptionSegmentRecord(
            sessionId: sessionId,
            speaker: speaker,
            text: text,
            startTime: startTime,
            endTime: endTime,
            segmentOrder: segmentOrder
        )

        let record = try await db.write { database in
            try segment.inserted(database)
        }

        log("TranscriptionStorage: Appended segment \(record.id ?? -1) to session \(sessionId) (speaker: \(speaker), \(String(format: "%.1f", startTime))s-\(String(format: "%.1f", endTime))s)")
        return record.id!
    }

    /// Get all segments for a session ordered by segmentOrder
    func getSegments(sessionId: Int64) async throws -> [TranscriptionSegmentRecord] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try TranscriptionSegmentRecord
                .filter(Column("sessionId") == sessionId)
                .order(Column("segmentOrder").asc)
                .fetchAll(database)
        }
    }

    /// Get segment count for a session
    func getSegmentCount(sessionId: Int64) async throws -> Int {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try Int.fetchOne(
                database,
                sql: "SELECT COUNT(*) FROM transcription_segments WHERE sessionId = ?",
                arguments: [sessionId]
            ) ?? 0
        }
    }

    // MARK: - Queries

    /// Get a session by ID
    func getSession(id: Int64) async throws -> TranscriptionSessionRecord? {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try TranscriptionSessionRecord.fetchOne(database, key: id)
        }
    }

    /// Get the currently active recording session (if any)
    func getActiveSession() async throws -> TranscriptionSessionRecord? {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try TranscriptionSessionRecord
                .filter(Column("status") == TranscriptionSessionStatus.recording.rawValue)
                .order(Column("createdAt").desc)
                .fetchOne(database)
        }
    }

    /// Get sessions pending upload
    func getPendingUploadSessions() async throws -> [TranscriptionSessionRecord] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try TranscriptionSessionRecord
                .filter(Column("status") == TranscriptionSessionStatus.pendingUpload.rawValue)
                .order(Column("createdAt").asc)
                .fetchAll(database)
        }
    }

    /// Get failed sessions that can be retried
    func getFailedSessions(maxRetries: Int = 5) async throws -> [TranscriptionSessionRecord] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try TranscriptionSessionRecord
                .filter(Column("status") == TranscriptionSessionStatus.failed.rawValue)
                .filter(Column("retryCount") < maxRetries)
                .order(Column("updatedAt").asc)
                .fetchAll(database)
        }
    }

    /// Get sessions that were left in "recording" status (crashed)
    func getCrashedSessions() async throws -> [TranscriptionSessionRecord] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try TranscriptionSessionRecord
                .filter(Column("status") == TranscriptionSessionStatus.recording.rawValue)
                .order(Column("createdAt").asc)
                .fetchAll(database)
        }
    }

    /// Get sessions stuck in 'uploading' status for longer than the given threshold (in seconds)
    /// These are sessions where the app quit/crashed during upload or markSessionCompleted failed silently
    func getStuckUploadingSessions(olderThan seconds: TimeInterval) async throws -> [TranscriptionSessionRecord] {
        let db = try await ensureInitialized()
        let cutoff = Date().addingTimeInterval(-seconds)

        return try await db.read { database in
            try TranscriptionSessionRecord
                .filter(Column("status") == TranscriptionSessionStatus.uploading.rawValue)
                .filter(Column("updatedAt") < cutoff)
                .order(Column("createdAt").asc)
                .fetchAll(database)
        }
    }

    /// Get a session with its segments
    func getSessionWithSegments(id: Int64) async throws -> TranscriptionSessionWithSegments? {
        let db = try await ensureInitialized()

        return try await db.read { database in
            guard let session = try TranscriptionSessionRecord.fetchOne(database, key: id) else {
                return nil
            }

            let segments = try TranscriptionSegmentRecord
                .filter(Column("sessionId") == id)
                .order(Column("segmentOrder").asc)
                .fetchAll(database)

            return TranscriptionSessionWithSegments(session: session, segments: segments)
        }
    }

    /// Get all sessions needing recovery (crashed, pending, or failed with retries left)
    func getSessionsNeedingRecovery() async throws -> [TranscriptionSessionRecord] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try TranscriptionSessionRecord
                .filter(
                    Column("status") == TranscriptionSessionStatus.recording.rawValue ||
                    Column("status") == TranscriptionSessionStatus.pendingUpload.rawValue ||
                    (Column("status") == TranscriptionSessionStatus.failed.rawValue && Column("retryCount") < 5)
                )
                .order(Column("createdAt").asc)
                .fetchAll(database)
        }
    }

    /// Get storage statistics
    func getStats() async throws -> (totalSessions: Int, pendingCount: Int, failedCount: Int, completedCount: Int) {
        let db = try await ensureInitialized()

        return try await db.read { database in
            let total = try Int.fetchOne(database, sql: "SELECT COUNT(*) FROM transcription_sessions") ?? 0
            let pending = try Int.fetchOne(
                database,
                sql: "SELECT COUNT(*) FROM transcription_sessions WHERE status = ?",
                arguments: [TranscriptionSessionStatus.pendingUpload.rawValue]
            ) ?? 0
            let failed = try Int.fetchOne(
                database,
                sql: "SELECT COUNT(*) FROM transcription_sessions WHERE status = ?",
                arguments: [TranscriptionSessionStatus.failed.rawValue]
            ) ?? 0
            let completed = try Int.fetchOne(
                database,
                sql: "SELECT COUNT(*) FROM transcription_sessions WHERE status = ?",
                arguments: [TranscriptionSessionStatus.completed.rawValue]
            ) ?? 0

            return (total, pending, failed, completed)
        }
    }

    // MARK: - Backend Sync Operations

    /// Get a session by backend ID
    func getSessionByBackendId(_ backendId: String) async throws -> TranscriptionSessionRecord? {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try TranscriptionSessionRecord
                .filter(Column("backendId") == backendId)
                .fetchOne(database)
        }
    }

    /// Upsert a session from a ServerConversation (insert if not exists, update if exists)
    /// Returns the local session ID
    @discardableResult
    func upsertFromServerConversation(_ conversation: ServerConversation) async throws -> (sessionId: Int64, changed: Bool) {
        let db = try await ensureInitialized()

        return try await db.write { database -> (Int64, Bool) in
            // Check if session already exists by backendId
            if var existingSession = try TranscriptionSessionRecord
                .filter(Column("backendId") == conversation.id)
                .fetchOne(database) {
                // Skip if local record is newer than the conversation's latest timestamp.
                // This prevents sync from overwriting recent local mutations (star, delete, title edit, etc.)
                let serverTimestamp = conversation.finishedAt ?? conversation.startedAt ?? conversation.createdAt
                if existingSession.updatedAt >= serverTimestamp {
                    guard let sessionId = existingSession.id else {
                        throw TranscriptionStorageError.invalidState("Session ID is nil")
                    }
                    return (sessionId, false)
                }

                // Update existing session
                existingSession.updateFrom(conversation)
                try existingSession.update(database)
                guard let sessionId = existingSession.id else {
                    throw TranscriptionStorageError.invalidState("Session ID is nil after update")
                }
                log("TranscriptionStorage: Updated session \(sessionId) from backend \(conversation.id)")
                return (sessionId, true)
            } else {
                // Insert new session - use inserted() to get record with ID
                let newSession = TranscriptionSessionRecord.from(conversation)
                let insertedSession = try newSession.inserted(database)
                guard let sessionId = insertedSession.id else {
                    throw TranscriptionStorageError.invalidState("Session ID is nil after insert")
                }
                log("TranscriptionStorage: Inserted new session \(sessionId) from backend \(conversation.id)")
                return (sessionId, true)
            }
        }
    }

    /// Upsert segments from a ServerConversation
    /// Deletes existing segments and re-inserts from conversation
    func upsertSegmentsFromServerConversation(_ conversation: ServerConversation, sessionId: Int64) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            // Delete existing segments for this session
            try database.execute(
                sql: "DELETE FROM transcription_segments WHERE sessionId = ?",
                arguments: [sessionId]
            )

            // Insert new segments
            for (index, segment) in conversation.transcriptSegments.enumerated() {
                let record = TranscriptionSegmentRecord.from(segment, sessionId: sessionId, segmentOrder: index)
                _ = try record.inserted(database)
            }

            log("TranscriptionStorage: Upserted \(conversation.transcriptSegments.count) segments for session \(sessionId)")
        }
    }

    /// Sync a full ServerConversation (session + segments) to local storage
    @discardableResult
    func syncServerConversation(_ conversation: ServerConversation) async throws -> Int64 {
        // First upsert the session
        let (sessionId, changed) = try await upsertFromServerConversation(conversation)

        // Only re-sync segments if the session was actually inserted or updated
        if changed {
            try await upsertSegmentsFromServerConversation(conversation, sessionId: sessionId)
        }

        return sessionId
    }

    /// Get all sessions synced from backend (for display in Conversations page)
    func getSyncedSessions(limit: Int = 100, offset: Int = 0) async throws -> [TranscriptionSessionRecord] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try TranscriptionSessionRecord
                .filter(Column("backendSynced") == true)
                .filter(Column("deleted") == false)
                .filter(Column("discarded") == false)
                .order(Column("startedAt").desc)
                .limit(limit, offset: offset)
                .fetchAll(database)
        }
    }

    /// Update starred status for a session
    func updateStarred(id: Int64, starred: Bool) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try TranscriptionSessionRecord.fetchOne(database, key: id) else {
                throw TranscriptionStorageError.sessionNotFound
            }

            record.starred = starred
            record.updatedAt = Date()
            try record.update(database)
        }

        log("TranscriptionStorage: Updated starred=\(starred) for session \(id)")
    }

    /// Get starred sessions
    func getStarredSessions() async throws -> [TranscriptionSessionRecord] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try TranscriptionSessionRecord
                .filter(Column("starred") == true)
                .filter(Column("deleted") == false)
                .order(Column("startedAt").desc)
                .fetchAll(database)
        }
    }

    /// Get conversations from local storage as ServerConversation objects
    /// Used for instant display before API fetch completes
    /// Note: Does NOT load segments for performance - segments are loaded on-demand for detail view
    func getLocalConversations(
        limit: Int = 50,
        offset: Int = 0,
        starredOnly: Bool = false,
        folderId: String? = nil
    ) async throws -> [ServerConversation] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            var query = TranscriptionSessionRecord
                .filter(Column("backendSynced") == true)
                .filter(Column("deleted") == false)
                .filter(Column("discarded") == false)

            if starredOnly {
                query = query.filter(Column("starred") == true)
            }

            if let folderId = folderId {
                query = query.filter(Column("folderId") == folderId)
            }

            let sessions = try query
                .order(Column("startedAt").desc)
                .limit(limit, offset: offset)
                .fetchAll(database)

            // Convert each session to ServerConversation WITHOUT loading segments
            // Segments are only needed for conversation detail view, not list view
            // This makes the query O(1) instead of O(N) for much faster loading
            return sessions.compactMap { session in
                session.toServerConversation(segments: [])
            }
        }
    }

    /// Get count of local conversations
    func getLocalConversationsCount(starredOnly: Bool = false) async throws -> Int {
        let db = try await ensureInitialized()

        return try await db.read { database in
            var query = TranscriptionSessionRecord
                .filter(Column("backendSynced") == true)
                .filter(Column("deleted") == false)
                .filter(Column("discarded") == false)

            if starredOnly {
                query = query.filter(Column("starred") == true)
            }

            return try query.fetchCount(database)
        }
    }
}
