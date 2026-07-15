import Foundation
@preconcurrency import GRDB

private func withConversationCacheScope<T>(
  _ scope: ConversationCacheWriteScope?,
  generation: Int?,
  operation: () throws -> T
) throws -> T {
  if let scope, let generation {
    return try scope.withCurrent(generation, operation)
  }
  return try operation()
}

/// Actor-based storage manager for transcription sessions and segments
/// Provides crash-safe persistence for transcription data during recording
actor TranscriptionStorage {
  static let shared = TranscriptionStorage()

  private var _dbQueue: DatabasePool?
  private var _dbGeneration = -1
  private var isInitialized = false

  private init() {}

  /// Invalidate cached DB queue (called on user switch / sign-out)
  func invalidateCache() {
    _dbQueue = nil
    isInitialized = false
  }

  /// Ensure database is initialized before use
  private func ensureInitialized() async throws -> DatabasePool {
    if let db = _dbQueue, await RewindDatabase.shared.poolGeneration() == _dbGeneration {
      return db
    }

    // Initialize RewindDatabase which creates our tables via migrations
    do {
      try await RewindDatabase.shared.initialize()
    } catch {
      log("TranscriptionStorage: Database initialization failed: \(error.localizedDescription)")
      throw error
    }

    let (queue, generation) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let db = queue else {
      throw TranscriptionStorageError.databaseNotInitialized
    }

    _dbQueue = db
    _dbGeneration = generation
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
    inputDeviceName: String? = nil,
    clientConversationId: String? = nil,
    finalizationStrategy: TranscriptionFinalizationStrategy = .cloudReconcile
  ) async throws -> Int64 {
    let db = try await ensureInitialized()

    let session = TranscriptionSessionRecord(
      startedAt: Date(),
      source: source,
      language: language,
      timezone: timezone,
      inputDeviceName: inputDeviceName,
      status: .recording,
      clientConversationId: clientConversationId,
      finalizationStrategy: finalizationStrategy
    )

    let record = try await db.write { database in
      try session.inserted(database)
    }

    log(
      "TranscriptionStorage: Started session \(record.id ?? -1) (source: \(source), device: \(inputDeviceName ?? "unknown"))"
    )
    return record.id!
  }

  /// Mark session as finished (recording complete, ready for upload/reconciliation)
  func finishSession(
    id: Int64,
    strategy: TranscriptionFinalizationStrategy? = nil,
    reason: TranscriptionFinalizationReason = .userStop
  ) async throws {
    let db = try await ensureInitialized()

    let didFinish = try await db.write { database -> Bool in
      guard var record = try TranscriptionSessionRecord.fetchOne(database, key: id) else {
        throw TranscriptionStorageError.sessionNotFound
      }

      guard record.status != .completed && !record.backendSynced else {
        log("TranscriptionStorage: Skipping finishSession for completed backend-synced session \(id)")
        return false
      }

      let now = Date()
      record.finishedAt = max(now, record.startedAt.addingTimeInterval(1.0))
      record.status = .pendingUpload
      if let strategy {
        record.finalizationStrategy = strategy
      } else if record.finalizationStrategy == nil {
        record.finalizationStrategy =
          (record.backendId?.isEmpty == false)
          ? .cloudReconcile : (record.source == ConversationSource.desktop.rawValue ? .localSegments : .cloudReconcile)
      }
      record.finalizationReason = reason
      record.finalizationStartedAt = nil
      record.finalizationCompletedAt = nil
      record.updatedAt = Date()
      try record.update(database)
      return true
    }

    if didFinish {
      log("TranscriptionStorage: Finished session \(id)")
    }
  }

  /// Bind a local recording session to the backend conversation id announced by `/v4/listen`.
  /// This is not completion: the backend conversation may still be `in_progress` until stop/finalize.
  func bindBackendConversation(id: Int64, backendId: String) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      guard var record = try TranscriptionSessionRecord.fetchOne(database, key: id) else {
        throw TranscriptionStorageError.sessionNotFound
      }

      guard record.canAcceptCompletion(backendId: backendId) else {
        log(
          "TranscriptionStorage: Skipping conflicting backend bind for session \(id) (existing: \(record.backendId ?? "nil"), incoming: \(backendId))"
        )
        return
      }

      record.backendId = backendId
      record.conversationStatus = .inProgress
      record.updatedAt = Date()
      try record.update(database)
    }

    log("TranscriptionStorage: Bound session \(id) to backend conversation \(backendId)")
  }

  /// Mark session as pending upload
  func markSessionPendingUpload(id: Int64) async throws {
    try await updateSessionStatus(id: id, status: .pendingUpload)
  }

  /// Mark session as currently uploading
  @discardableResult
  func markSessionUploading(id: Int64) async throws -> Bool {
    let db = try await ensureInitialized()

    let claimed = try await db.write { database -> Bool in
      guard var record = try TranscriptionSessionRecord.fetchOne(database, key: id) else {
        throw TranscriptionStorageError.sessionNotFound
      }

      let now = Date()
      let staleUploadingCutoff = now.addingTimeInterval(-300)
      guard record.status != .uploading || record.updatedAt < staleUploadingCutoff else {
        log("TranscriptionStorage: Skipping markSessionUploading for in-progress session \(id)")
        return false
      }

      guard record.status != .completed && !record.backendSynced else {
        log("TranscriptionStorage: Skipping markSessionUploading for completed backend-synced session \(id)")
        return false
      }

      record.status = .uploading
      record.finalizationStartedAt = now
      record.updatedAt = now
      try record.update(database)
      return true
    }

    if claimed {
      log("TranscriptionStorage: Marked session \(id) finalization in progress")
    }
    return claimed
  }

  /// Mark session as completed (uploaded successfully)
  @discardableResult
  func markSessionCompleted(
    id: Int64,
    backendId: String,
    conversationStatus: LocalConversationStatus = .completed,
    allowBackendIdOverride: Bool = false
  ) async throws -> Bool {
    let db = try await ensureInitialized()

    let completed = try await db.write { database -> Bool in
      guard var record = try TranscriptionSessionRecord.fetchOne(database, key: id) else {
        throw TranscriptionStorageError.sessionNotFound
      }

      guard allowBackendIdOverride || record.canAcceptCompletion(backendId: backendId) else {
        log(
          "TranscriptionStorage: Skipping conflicting completion for session \(id) (existing: \(record.backendId ?? "nil"), incoming: \(backendId))"
        )
        return false
      }

      let completedAt = Date()
      record.status = .completed
      record.conversationStatus = conversationStatus
      record.finishedAt = record.finishedAt ?? completedAt
      record.backendId = backendId
      record.backendSynced = true
      record.retryCount = 0
      record.lastError = nil
      record.finalizationCompletedAt = completedAt
      record.updatedAt = completedAt
      try record.update(database)
      return true
    }

    if completed {
      log("TranscriptionStorage: Completed session \(id) (backendId: \(backendId))")
    }
    return completed
  }

  /// Mark session as failed with error.
  /// No-op if the session is already completed (prevents race with concurrent completion).
  func markSessionFailed(id: Int64, error: String) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      guard var record = try TranscriptionSessionRecord.fetchOne(database, key: id) else {
        throw TranscriptionStorageError.sessionNotFound
      }

      // Don't regress a completed session back to failed
      guard record.status != .completed else {
        log("TranscriptionStorage: Skipping markSessionFailed for already-completed session \(id)")
        return
      }
      guard record.status != .completed && !record.backendSynced else {
        log("TranscriptionStorage: Skipping markSessionFailed for completed backend-synced session \(id)")
        return
      }

      record.status = .failed
      record.lastError = error
      record.updatedAt = Date()
      try record.update(database)
    }

    log("TranscriptionStorage: Failed session \(id) (error: \(error))")
  }

  /// Increment retry count for a session.
  /// No-op if the session is already completed (prevents race with concurrent completion).
  func incrementRetryCount(id: Int64) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      guard var record = try TranscriptionSessionRecord.fetchOne(database, key: id) else {
        throw TranscriptionStorageError.sessionNotFound
      }

      // Don't modify a completed session
      guard record.status != .completed else {
        log("TranscriptionStorage: Skipping incrementRetryCount for already-completed session \(id)")
        return
      }
      guard record.status != .completed && !record.backendSynced else {
        log("TranscriptionStorage: Skipping incrementRetryCount for completed backend-synced session \(id)")
        return
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

      guard record.status != .completed && !record.backendSynced else {
        log("TranscriptionStorage: Skipping status update for completed backend-synced session \(id)")
        return
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
  func deleteByBackendId(
    _ backendId: String,
    cacheScope: ConversationCacheWriteScope? = nil,
    cacheGeneration: Int? = nil
  ) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      try withConversationCacheScope(cacheScope, generation: cacheGeneration) {
        try database.execute(
          sql: "UPDATE transcription_sessions SET deleted = 1, updatedAt = ? WHERE backendId = ?",
          arguments: [Date(), backendId]
        )
      }
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

    log(
      "TranscriptionStorage: Appended segment \(record.id ?? -1) to session \(sessionId) (speaker: \(speaker), \(String(format: "%.1f", startTime))s-\(String(format: "%.1f", endTime))s)"
    )
    return record.id!
  }

  /// Upsert a segment by backend segment ID — update if exists, insert if not.
  /// This handles the Python backend protocol where segments are sent with updates.
  @discardableResult
  func upsertSegment(
    sessionId: Int64,
    backendSegmentId: String?,
    speaker: Int,
    text: String,
    startTime: Double,
    endTime: Double,
    isUser: Bool = false,
    personId: String? = nil,
    speakerLabel: String? = nil,
    translationsJson: String? = nil
  ) async throws -> Int64 {
    let db = try await ensureInitialized()

    // If we have a backend segment ID, try to update existing
    if let segId = backendSegmentId {
      let updated = try await db.write { database -> Bool in
        try database.execute(
          sql: """
            UPDATE transcription_segments
            SET text = ?, speaker = ?, startTime = ?, endTime = ?, isUser = ?, personId = ?,
                speakerLabel = COALESCE(?, speakerLabel),
                translationsJson = COALESCE(?, translationsJson)
            WHERE sessionId = ? AND segmentId = ?
            """,
          arguments: [
            text, speaker, startTime, endTime, isUser, personId, speakerLabel, translationsJson, sessionId, segId,
          ]
        )
        return database.changesCount > 0
      }
      if updated {
        return 0  // Updated existing row
      }
    }

    // Insert new segment
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
      segmentOrder: segmentOrder,
      segmentId: backendSegmentId,
      speakerLabel: speakerLabel,
      isUser: isUser,
      personId: personId,
      translationsJson: translationsJson
    )

    let record = try await db.write { database in
      try segment.inserted(database)
    }

    return record.id!
  }

  /// Update personId/isUser for segments by their backend segment IDs (UUIDs)
  func updateSegmentSpeakerAssignment(
    backendConversationId: String, segmentIds: [String], personId: String?, isUser: Bool
  ) async throws {
    guard !segmentIds.isEmpty else { return }
    guard let session = try await getSessionByBackendId(backendConversationId) else { return }
    guard let sessionId = session.id else { return }
    let db = try await ensureInitialized()

    for segId in segmentIds {
      try await db.write { database in
        try database.execute(
          sql: "UPDATE transcription_segments SET personId = ?, isUser = ? WHERE sessionId = ? AND segmentId = ?",
          arguments: [personId, isUser, sessionId, segId]
        )
      }
    }
    log("TranscriptionStorage: Updated speaker assignment for \(segmentIds.count) segments in session \(sessionId)")
  }

  /// Delete segments by their backend segment IDs
  func deleteSegmentsByBackendIds(sessionId: Int64, segmentIds: [String]) async throws {
    guard !segmentIds.isEmpty else { return }
    let db = try await ensureInitialized()

    _ = try await db.write { database in
      try TranscriptionSegmentRecord
        .filter(Column("sessionId") == sessionId)
        .filter(segmentIds.contains(Column("segmentId")))
        .deleteAll(database)
    }
    log("TranscriptionStorage: Deleted \(segmentIds.count) segments by backend IDs from session \(sessionId)")
  }

  /// Update speaker assignment metadata for existing segments in a synced conversation.
  /// Matches by backend segment IDs when available, then falls back to local segment order.
  func updateSpeakerAssignmentByBackendId(
    _ backendId: String,
    segmentIds: [String],
    fallbackSegmentOrders: [Int],
    isUser: Bool,
    personId: String?
  ) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      guard
        let sessionId = try Int64.fetchOne(
          database,
          sql: "SELECT id FROM transcription_sessions WHERE backendId = ?",
          arguments: [backendId]
        )
      else {
        return
      }

      let encodedSegmentIds = String(
        decoding: try JSONEncoder().encode(segmentIds),
        as: UTF8.self
      )
      let encodedFallbackOrders = String(
        decoding: try JSONEncoder().encode(fallbackSegmentOrders),
        as: UTF8.self
      )

      if !segmentIds.isEmpty {
        try database.execute(
          sql: """
            UPDATE transcription_segments
            SET isUser = ?, personId = ?
            WHERE sessionId = ? AND segmentId IN (
                SELECT value FROM json_each(?)
            )
            """,
          arguments: [isUser, personId, sessionId, encodedSegmentIds]
        )
      }

      if !fallbackSegmentOrders.isEmpty {
        try database.execute(
          sql: """
            UPDATE transcription_segments
            SET isUser = ?, personId = ?
            WHERE sessionId = ? AND segmentOrder IN (
                SELECT value FROM json_each(?)
            )
            """,
          arguments: [isUser, personId, sessionId, encodedFallbackOrders]
        )
      }
    }
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
        .filter(Column("backendSynced") == false)
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
        .filter(Column("backendSynced") == false)
        .order(Column("updatedAt").asc)
        .fetchAll(database)
    }
  }

  /// Get all unfinished sessions that should be finalized or retried by the canonical finalizer.
  func getSessionsNeedingFinalization(maxRetries: Int = 5, uploadingStaleAfter seconds: TimeInterval = 300) async throws
    -> [TranscriptionSessionRecord]
  {
    let db = try await ensureInitialized()
    let uploadingCutoff = Date().addingTimeInterval(-seconds)

    return try await db.read { database in
      try TranscriptionSessionRecord
        .filter(Column("backendSynced") == false)
        .filter(
          Column("status") == TranscriptionSessionStatus.pendingUpload.rawValue
            || (Column("status") == TranscriptionSessionStatus.uploading.rawValue
              && Column("updatedAt") < uploadingCutoff)
            || (Column("status") == TranscriptionSessionStatus.failed.rawValue && Column("retryCount") < maxRetries)
        )
        .order(Column("createdAt").asc)
        .fetchAll(database)
    }
  }

  /// Get failed cloud-reconciliation sessions that exhausted normal retries but still have saved
  /// local transcript segments. These can be recovered by uploading those segments directly.
  func getExhaustedCloudSessionsWithLocalSegments(
    maxRetries: Int = 5,
    maxLocalFallbackRetries: Int = 3
  ) async throws -> [TranscriptionSessionRecord] {
    let db = try await ensureInitialized()
    let retryLimit = maxRetries + maxLocalFallbackRetries

    return try await db.read { database in
      try TranscriptionSessionRecord
        .filter(Column("backendSynced") == false)
        .filter(Column("status") == TranscriptionSessionStatus.failed.rawValue)
        .filter(Column("retryCount") >= maxRetries)
        .filter(Column("retryCount") < retryLimit)
        .filter(
          sql: """
            finalizationStrategy = ?
            OR (
                finalizationStrategy IS NULL
                AND ((backendId IS NOT NULL AND backendId != '') OR source != ?)
            )
            """,
          arguments: [
            TranscriptionFinalizationStrategy.cloudReconcile.rawValue,
            ConversationSource.desktop.rawValue,
          ]
        )
        .filter(
          sql: """
            EXISTS (
                SELECT 1
                FROM transcription_segments
                WHERE transcription_segments.sessionId = transcription_sessions.id
            )
            """
        )
        .order(Column("createdAt").asc)
        .fetchAll(database)
    }
  }

  /// Get sessions that were left in "recording" status (crashed)
  func getCrashedSessions() async throws -> [TranscriptionSessionRecord] {
    let db = try await ensureInitialized()

    return try await db.read { database in
      try TranscriptionSessionRecord
        .filter(Column("status") == TranscriptionSessionStatus.recording.rawValue)
        .filter(Column("backendSynced") == false)
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
        .filter(Column("backendSynced") == false)
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

      let segments =
        try TranscriptionSegmentRecord
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
          Column("status") == TranscriptionSessionStatus.recording.rawValue
            || Column("status") == TranscriptionSessionStatus.pendingUpload.rawValue
            || (Column("status") == TranscriptionSessionStatus.failed.rawValue && Column("retryCount") < 5)
        )
        .filter(Column("backendSynced") == false)
        .order(Column("createdAt").asc)
        .fetchAll(database)
    }
  }

  /// Get storage statistics
  func getStats() async throws -> (totalSessions: Int, pendingCount: Int, failedCount: Int, completedCount: Int) {
    let db = try await ensureInitialized()

    return try await db.read { database in
      let total = try Int.fetchOne(database, sql: "SELECT COUNT(*) FROM transcription_sessions") ?? 0
      let pending =
        try Int.fetchOne(
          database,
          sql: "SELECT COUNT(*) FROM transcription_sessions WHERE status = ?",
          arguments: [TranscriptionSessionStatus.pendingUpload.rawValue]
        ) ?? 0
      let failed =
        try Int.fetchOne(
          database,
          sql: "SELECT COUNT(*) FROM transcription_sessions WHERE status = ?",
          arguments: [TranscriptionSessionStatus.failed.rawValue]
        ) ?? 0
      let completed =
        try Int.fetchOne(
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
  func upsertFromServerConversation(
    _ conversation: ServerConversation,
    cacheScope: ConversationCacheWriteScope? = nil,
    cacheGeneration: Int? = nil
  ) async throws -> (sessionId: Int64, changed: Bool) {
    let db = try await ensureInitialized()

    return try await db.write { database -> (Int64, Bool) in
      try withConversationCacheScope(cacheScope, generation: cacheGeneration) {
        // Check if session already exists by backendId
        if var existingSession =
          try TranscriptionSessionRecord
          .filter(Column("backendId") == conversation.id)
          .fetchOne(database)
        {
          // Firestore update_time is the only server freshness authority.
          // Local cache-write time and recording timestamps are unrelated clocks.
          let incomingIsOlder: Bool
          if let incomingRevision = conversation.updatedAt,
            let cachedRevision = existingSession.serverUpdatedAt
          {
            incomingIsOlder = incomingRevision < cachedRevision
          } else {
            incomingIsOlder = false
          }
          let shouldHydrateLocalShell = existingSession.hasHydratableServerFields(from: conversation)
          let upgradesDetail =
            conversation.transcriptSegmentsIncluded
            && existingSession.cacheCompleteness == .list
          let requiresConservativeMerge = conversation.updatedAt == nil || incomingIsOlder
          if requiresConservativeMerge && !shouldHydrateLocalShell && !upgradesDetail {
            guard let sessionId = existingSession.id else {
              throw TranscriptionStorageError.invalidState("Session ID is nil")
            }
            return (sessionId, false)
          }

          if requiresConservativeMerge {
            existingSession.hydrateMissingFields(from: conversation)
          } else {
            existingSession.updateFrom(conversation)
          }
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
  }

  /// Upsert segments from a ServerConversation.
  /// Replaces backend-owned transcript fields while preserving existing local speaker assignments.
  /// Skips when incoming segments are empty to avoid wiping locally-cached data
  /// (list endpoints often return conversations without transcript segments).
  func upsertSegmentsFromServerConversation(
    _ conversation: ServerConversation,
    sessionId: Int64,
    cacheScope: ConversationCacheWriteScope? = nil,
    cacheGeneration: Int? = nil
  ) async throws {
    guard !conversation.transcriptSegments.isEmpty else { return }

    let db = try await ensureInitialized()

    try await db.write { database in
      try withConversationCacheScope(cacheScope, generation: cacheGeneration) {
        let existingSegments =
          try TranscriptionSegmentRecord
          .filter(Column("sessionId") == sessionId)
          .fetchAll(database)
        var existingBySegmentId: [String: TranscriptionSegmentRecord] = [:]
        var existingByOrder: [Int: TranscriptionSegmentRecord] = [:]
        for segment in existingSegments {
          if let segmentId = segment.segmentId {
            existingBySegmentId[segmentId] = segment
          }
          existingByOrder[segment.segmentOrder] = segment
        }

        // Delete existing segments for this session
        try database.execute(
          sql: "DELETE FROM transcription_segments WHERE sessionId = ?",
          arguments: [sessionId]
        )

        // Insert new segments
        for (index, segment) in conversation.transcriptSegments.enumerated() {
          var record = TranscriptionSegmentRecord.from(segment, sessionId: sessionId, segmentOrder: index)
          let existing = segment.backendId.flatMap { existingBySegmentId[$0] } ?? existingByOrder[index]
          if let existing, existing.hasSpeakerAssignment {
            record.isUser = existing.isUser
            record.personId = existing.personId
          }
          _ = try record.inserted(database)
        }

        log("TranscriptionStorage: Upserted \(conversation.transcriptSegments.count) segments for session \(sessionId)")
      }
    }
  }

  /// Sync a full ServerConversation (session + segments) to local storage
  @discardableResult
  func syncServerConversation(
    _ conversation: ServerConversation,
    cacheScope: ConversationCacheWriteScope? = nil,
    cacheGeneration: Int? = nil
  ) async throws -> Int64 {
    // First upsert the session
    let (sessionId, changed) = try await upsertFromServerConversation(
      conversation,
      cacheScope: cacheScope,
      cacheGeneration: cacheGeneration
    )

    // Detail responses can carry backend segment ids, speaker assignments, or translations even
    // when session metadata is skipped by the local-newer timestamp guard.
    if changed || conversation.transcriptPresenceState == .includedNonEmpty {
      try await upsertSegmentsFromServerConversation(
        conversation,
        sessionId: sessionId,
        cacheScope: cacheScope,
        cacheGeneration: cacheGeneration
      )
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
      var query =
        TranscriptionSessionRecord
        .filter(Column("backendSynced") == true)
        .filter(Column("deleted") == false)
        .filter(Column("discarded") == false)

      if starredOnly {
        query = query.filter(Column("starred") == true)
      }

      if let folderId = folderId {
        query = query.filter(Column("folderId") == folderId)
      }

      let sessions =
        try query
        .order(Column("startedAt").desc)
        .limit(limit, offset: offset)
        .fetchAll(database)

      // Convert each session to ServerConversation WITHOUT loading segments
      // Segments are only needed for conversation detail view, not list view
      // This makes the query O(1) instead of O(N) for much faster loading
      return sessions.compactMap { session in
        session.toServerConversation(segments: [], transcriptIncluded: false)
      }
    }
  }

  /// Source-scoped cache read for the cohort-only Omi capture archive.
  /// Filtering happens before ordering and limiting so a cached page cannot
  /// be filled by another source and then client-filtered.
  func getLocalOmiCaptureConversations(
    limit: Int = 50,
    offset: Int = 0
  ) async throws -> [ServerConversation] {
    let db = try await ensureInitialized()

    return try await db.read { database in
      let sessions = try TranscriptionSessionRecord
        .filter(Column("backendSynced") == true)
        .filter(Column("deleted") == false)
        .filter(Column("discarded") == false)
        .filter(Column("source") == ConversationSource.omi.rawValue)
        .filter(
          Column("conversationStatus") == LocalConversationStatus.completed.rawValue
            || Column("conversationStatus") == LocalConversationStatus.processing.rawValue
        )
        .order(Column("startedAt").desc)
        .limit(limit, offset: offset)
        .fetchAll(database)

      return sessions.compactMap { session in
        session.toServerConversation(segments: [], transcriptIncluded: false)
      }
    }
  }

  /// Read the richest cached projection for a detail screen.
  func getCachedConversation(id: String) async throws -> ServerConversation? {
    guard let session = try await getSessionByBackendId(id), let sessionId = session.id else {
      return nil
    }
    let segments = try await getSegments(sessionId: sessionId)
    return session.toServerConversation(segments: segments)
  }

  /// Get count of local conversations
  func getLocalConversationsCount(starredOnly: Bool = false, folderId: String? = nil) async throws -> Int {
    let db = try await ensureInitialized()

    return try await db.read { database in
      var query =
        TranscriptionSessionRecord
        .filter(Column("backendSynced") == true)
        .filter(Column("deleted") == false)
        .filter(Column("discarded") == false)

      if starredOnly {
        query = query.filter(Column("starred") == true)
      }

      if let folderId = folderId {
        query = query.filter(Column("folderId") == folderId)
      }

      return try query.fetchCount(database)
    }
  }

  /// Count companion to getLocalOmiCaptureConversations. Keeping the same
  /// predicate prevents the archive from reporting a mixed-source cache total.
  func getLocalOmiCaptureConversationsCount() async throws -> Int {
    let db = try await ensureInitialized()
    return try await db.read { database in
      try TranscriptionSessionRecord
        .filter(Column("backendSynced") == true)
        .filter(Column("deleted") == false)
        .filter(Column("discarded") == false)
        .filter(Column("source") == ConversationSource.omi.rawValue)
        .filter(
          Column("conversationStatus") == LocalConversationStatus.completed.rawValue
            || Column("conversationStatus") == LocalConversationStatus.processing.rawValue
        )
        .fetchCount(database)
    }
  }
}
