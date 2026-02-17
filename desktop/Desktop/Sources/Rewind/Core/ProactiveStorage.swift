import Foundation
import GRDB

/// Unified storage manager for all proactive assistant data (memories, tasks, advice, focus sessions)
/// Uses SQLite for local persistence with backend sync
actor ProactiveStorage {
    static let shared = ProactiveStorage()

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
            log("ProactiveStorage: Database initialization failed: \(error.localizedDescription)")
            throw error
        }

        guard let db = await RewindDatabase.shared.getDatabaseQueue() else {
            throw ProactiveStorageError.databaseNotInitialized
        }

        _dbQueue = db
        isInitialized = true
        return db
    }

    // MARK: - Extraction Operations (Memory, Task, Advice)

    /// Insert a new extraction record
    @discardableResult
    func insertExtraction(_ extraction: ProactiveExtractionRecord) async throws -> ProactiveExtractionRecord {
        let db = try await ensureInitialized()

        let record = try await db.write { database in
            try extraction.inserted(database)
        }
        log("ProactiveStorage: Inserted \(extraction.type.rawValue) extraction (id: \(record.id ?? -1))")
        return record
    }

    /// Get extractions by type
    func getExtractions(
        type: ExtractionType,
        limit: Int = 100,
        offset: Int = 0,
        includeDismissed: Bool = false
    ) async throws -> [ProactiveExtractionRecord] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            var query = ProactiveExtractionRecord
                .filter(Column("type") == type.rawValue)

            if !includeDismissed {
                query = query.filter(Column("isDismissed") == false)
            }

            return try query
                .order(Column("createdAt").desc)
                .limit(limit, offset: offset)
                .fetchAll(database)
        }
    }

    /// Get extraction by ID
    func getExtraction(id: Int64) async throws -> ProactiveExtractionRecord? {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try ProactiveExtractionRecord.fetchOne(database, key: id)
        }
    }

    /// Get extraction with its screenshot
    func getExtractionWithScreenshot(id: Int64) async throws -> ExtractionWithScreenshot? {
        let db = try await ensureInitialized()

        return try await db.read { database in
            guard let extraction = try ProactiveExtractionRecord.fetchOne(database, key: id) else {
                return nil
            }

            let screenshot: Screenshot?
            if let screenshotId = extraction.screenshotId {
                screenshot = try Screenshot.fetchOne(database, key: screenshotId)
            } else {
                screenshot = nil
            }

            return ExtractionWithScreenshot(extraction: extraction, screenshot: screenshot)
        }
    }

    /// Get extractions with their screenshots
    func getExtractionsWithScreenshots(
        type: ExtractionType,
        limit: Int = 100,
        includeDismissed: Bool = false
    ) async throws -> [ExtractionWithScreenshot] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            var query = ProactiveExtractionRecord
                .filter(Column("type") == type.rawValue)

            if !includeDismissed {
                query = query.filter(Column("isDismissed") == false)
            }

            let extractions = try query
                .order(Column("createdAt").desc)
                .limit(limit)
                .fetchAll(database)

            return try extractions.map { extraction in
                let screenshot: Screenshot?
                if let screenshotId = extraction.screenshotId {
                    screenshot = try Screenshot.fetchOne(database, key: screenshotId)
                } else {
                    screenshot = nil
                }
                return ExtractionWithScreenshot(extraction: extraction, screenshot: screenshot)
            }
        }
    }

    /// Update extraction
    func updateExtraction(id: Int64, updates: ExtractionUpdate) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try ProactiveExtractionRecord.fetchOne(database, key: id) else {
                throw ProactiveStorageError.recordNotFound
            }

            if let content = updates.content {
                record.content = content
            }
            if let isRead = updates.isRead {
                record.isRead = isRead
            }
            if let isDismissed = updates.isDismissed {
                record.isDismissed = isDismissed
            }
            if let backendId = updates.backendId {
                record.backendId = backendId
            }
            if let backendSynced = updates.backendSynced {
                record.backendSynced = backendSynced
            }

            record.updatedAt = Date()
            try record.update(database)
        }
    }

    /// Mark extraction as read
    func markExtractionAsRead(id: Int64) async throws {
        try await updateExtraction(id: id, updates: ExtractionUpdate(isRead: true))
    }

    /// Mark all extractions of a type as read
    func markAllExtractionsAsRead(type: ExtractionType) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "UPDATE proactive_extractions SET isRead = 1, updatedAt = ? WHERE type = ? AND isRead = 0",
                arguments: [Date(), type.rawValue]
            )
        }
    }

    /// Dismiss extraction (hide from list)
    func dismissExtraction(id: Int64) async throws {
        try await updateExtraction(id: id, updates: ExtractionUpdate(isDismissed: true))
    }

    /// Delete extraction
    func deleteExtraction(id: Int64) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "DELETE FROM proactive_extractions WHERE id = ?",
                arguments: [id]
            )
        }
    }

    /// Get unsynced extractions
    func getUnsyncedExtractions(type: ExtractionType? = nil) async throws -> [ProactiveExtractionRecord] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            var query = ProactiveExtractionRecord
                .filter(Column("backendSynced") == false)

            if let type = type {
                query = query.filter(Column("type") == type.rawValue)
            }

            return try query.fetchAll(database)
        }
    }

    /// Get unread count for a type
    func getUnreadCount(type: ExtractionType) async throws -> Int {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try Int.fetchOne(
                database,
                sql: "SELECT COUNT(*) FROM proactive_extractions WHERE type = ? AND isRead = 0 AND isDismissed = 0",
                arguments: [type.rawValue]
            ) ?? 0
        }
    }

    /// Search extractions by content
    func searchExtractions(query: String, type: ExtractionType? = nil, limit: Int = 50) async throws -> [ProactiveExtractionRecord] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            var sql = """
                SELECT proactive_extractions.* FROM proactive_extractions
                JOIN proactive_extractions_fts ON proactive_extractions.id = proactive_extractions_fts.rowid
                WHERE proactive_extractions_fts MATCH ?
                """
            var arguments: [DatabaseValueConvertible] = [query + "*"]

            if let type = type {
                sql += " AND proactive_extractions.type = ?"
                arguments.append(type.rawValue)
            }

            sql += " ORDER BY proactive_extractions.createdAt DESC LIMIT ?"
            arguments.append(limit)

            return try ProactiveExtractionRecord.fetchAll(database, sql: sql, arguments: StatementArguments(arguments))
        }
    }

    // MARK: - Focus Session Operations

    /// Insert a new focus session
    @discardableResult
    func insertFocusSession(_ session: FocusSessionRecord) async throws -> FocusSessionRecord {
        let db = try await ensureInitialized()

        let record = try await db.write { database in
            try session.inserted(database)
        }
        log("ProactiveStorage: Inserted focus session (id: \(record.id ?? -1), status: \(session.status))")
        return record
    }

    /// Get focus sessions for a date range
    func getFocusSessions(from startDate: Date, to endDate: Date, limit: Int = 500) async throws -> [FocusSessionRecord] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try FocusSessionRecord
                .filter(Column("createdAt") >= startDate && Column("createdAt") <= endDate)
                .order(Column("createdAt").desc)
                .limit(limit)
                .fetchAll(database)
        }
    }

    /// Get today's focus sessions
    func getTodayFocusSessions() async throws -> [FocusSessionRecord] {
        let calendar = Calendar.current
        let startOfDay = calendar.startOfDay(for: Date())
        let endOfDay = calendar.date(byAdding: .day, value: 1, to: startOfDay) ?? Date()

        return try await getFocusSessions(from: startOfDay, to: endOfDay)
    }

    /// Get focus stats for a date
    func getFocusStats(for date: Date) async throws -> FocusStats {
        let calendar = Calendar.current
        let startOfDay = calendar.startOfDay(for: date)
        let endOfDay = calendar.date(byAdding: .day, value: 1, to: startOfDay) ?? Date()

        let db = try await ensureInitialized()

        return try await db.read { database in
            let sessions = try FocusSessionRecord
                .filter(Column("createdAt") >= startOfDay && Column("createdAt") < endOfDay)
                .fetchAll(database)

            var focusedCount = 0
            var distractedCount = 0
            var distractionMap: [String: (seconds: Int, count: Int)] = [:]

            for session in sessions {
                if session.isFocused {
                    focusedCount += 1
                } else {
                    distractedCount += 1
                    let current = distractionMap[session.appOrSite] ?? (0, 0)
                    let seconds = session.durationSeconds ?? 60
                    distractionMap[session.appOrSite] = (current.seconds + seconds, current.count + 1)
                }
            }

            let topDistractions = distractionMap
                .map { FocusStats.DistractionEntry(appOrSite: $0.key, totalSeconds: $0.value.seconds, count: $0.value.count) }
                .sorted { $0.totalSeconds > $1.totalSeconds }
                .prefix(5)

            return FocusStats(
                date: date,
                focusedCount: focusedCount,
                distractedCount: distractedCount,
                sessionCount: sessions.count,
                topDistractions: Array(topDistractions)
            )
        }
    }

    /// Get total count of all focus sessions
    func getTotalFocusSessionCount() async throws -> Int {
        let db = try await ensureInitialized()
        return try await db.read { database in
            try FocusSessionRecord.fetchCount(database)
        }
    }

    /// Update focus session sync status
    func updateFocusSessionSyncStatus(id: Int64, backendId: String, synced: Bool) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "UPDATE focus_sessions SET backendId = ?, backendSynced = ? WHERE id = ?",
                arguments: [backendId, synced, id]
            )
        }
    }

    /// Delete focus session
    func deleteFocusSession(id: Int64) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "DELETE FROM focus_sessions WHERE id = ?",
                arguments: [id]
            )
        }
    }

    /// Get unsynced focus sessions
    func getUnsyncedFocusSessions() async throws -> [FocusSessionRecord] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try FocusSessionRecord
                .filter(Column("backendSynced") == false)
                .fetchAll(database)
        }
    }

    /// Get most recent focus session
    func getMostRecentFocusSession() async throws -> FocusSessionRecord? {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try FocusSessionRecord
                .order(Column("createdAt").desc)
                .limit(1)
                .fetchOne(database)
        }
    }

    // MARK: - Task Dedup Log

    /// Insert a dedup log record tracking an AI-driven task deletion
    @discardableResult
    func insertDedupLogRecord(_ record: TaskDedupLogRecord) async throws -> TaskDedupLogRecord {
        let db = try await ensureInitialized()

        let inserted = try await db.write { database in
            try record.inserted(database)
        }
        log("ProactiveStorage: Inserted dedup log (deleted: \(record.deletedTaskId), kept: \(record.keptTaskId))")
        return inserted
    }

    /// Get dedup log records for review
    func getDedupLogRecords(limit: Int = 100, offset: Int = 0) async throws -> [TaskDedupLogRecord] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try TaskDedupLogRecord
                .order(Column("deletedAt").desc)
                .limit(limit, offset: offset)
                .fetchAll(database)
        }
    }

    // MARK: - Cleanup

    /// Delete old extractions (for data retention)
    func deleteExtractionsOlderThan(_ date: Date) async throws -> Int {
        let db = try await ensureInitialized()

        return try await db.write { database in
            let count = try Int.fetchOne(
                database,
                sql: "SELECT COUNT(*) FROM proactive_extractions WHERE createdAt < ?",
                arguments: [date]
            ) ?? 0

            try database.execute(
                sql: "DELETE FROM proactive_extractions WHERE createdAt < ?",
                arguments: [date]
            )

            return count
        }
    }

    /// Delete old focus sessions (for data retention)
    func deleteFocusSessionsOlderThan(_ date: Date) async throws -> Int {
        let db = try await ensureInitialized()

        return try await db.write { database in
            let count = try Int.fetchOne(
                database,
                sql: "SELECT COUNT(*) FROM focus_sessions WHERE createdAt < ?",
                arguments: [date]
            ) ?? 0

            try database.execute(
                sql: "DELETE FROM focus_sessions WHERE createdAt < ?",
                arguments: [date]
            )

            return count
        }
    }
}

// MARK: - Supporting Types

/// Update parameters for extractions
struct ExtractionUpdate {
    var content: String?
    var isRead: Bool?
    var isDismissed: Bool?
    var backendId: String?
    var backendSynced: Bool?
}

/// Focus statistics for a day
struct FocusStats {
    let date: Date
    let focusedCount: Int
    let distractedCount: Int
    let sessionCount: Int
    let topDistractions: [DistractionEntry]

    struct DistractionEntry {
        let appOrSite: String
        let totalSeconds: Int
        let count: Int
    }

    var focusRate: Double {
        let total = focusedCount + distractedCount
        guard total > 0 else { return 0 }
        return Double(focusedCount) / Double(total) * 100
    }
}

/// Errors for ProactiveStorage operations
enum ProactiveStorageError: LocalizedError {
    case databaseNotInitialized
    case recordNotFound
    case syncFailed(String)

    var errorDescription: String? {
        switch self {
        case .databaseNotInitialized:
            return "Proactive storage database is not initialized"
        case .recordNotFound:
            return "Record not found"
        case .syncFailed(let message):
            return "Sync failed: \(message)"
        }
    }
}
