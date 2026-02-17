import Foundation
import GRDB

/// Actor-based storage manager for memories with bidirectional sync
/// Provides local-first caching for fast startup and background sync with backend
actor MemoryStorage {
    static let shared = MemoryStorage()

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
            log("MemoryStorage: Database initialization failed: \(error.localizedDescription)")
            throw error
        }

        guard let db = await RewindDatabase.shared.getDatabaseQueue() else {
            throw MemoryStorageError.databaseNotInitialized
        }

        _dbQueue = db
        isInitialized = true
        return db
    }

    // MARK: - Local-First Read Operations

    /// Get memories from local cache for instant display
    /// Supports filtering by category and tags
    func getLocalMemories(
        limit: Int = 50,
        offset: Int = 0,
        category: String? = nil,
        tags: [String]? = nil,
        includeDismissed: Bool = false
    ) async throws -> [ServerMemory] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            var query = MemoryRecord
                .filter(Column("deleted") == false)
                // Show ALL local memories (synced or not) for local-first experience

            if !includeDismissed {
                query = query.filter(Column("isDismissed") == false)
            }

            if let category = category {
                query = query.filter(Column("category") == category)
            }

            // Tag filtering using JSON
            if let tags = tags, !tags.isEmpty {
                for tag in tags {
                    // Use LIKE for JSON array contains check
                    query = query.filter(Column("tagsJson").like("%\"\(tag)\"%"))
                }
            }

            let records = try query
                .order(Column("createdAt").desc)
                .limit(limit, offset: offset)
                .fetchAll(database)

            return records.compactMap { $0.toServerMemory() }
        }
    }

    /// Get count of local memories
    func getLocalMemoriesCount(
        category: String? = nil,
        tags: [String]? = nil,
        includeDismissed: Bool = false
    ) async throws -> Int {
        let db = try await ensureInitialized()

        return try await db.read { database in
            var query = MemoryRecord
                .filter(Column("deleted") == false)
                // Count ALL local memories (synced or not) for local-first experience

            if !includeDismissed {
                query = query.filter(Column("isDismissed") == false)
            }

            if let category = category {
                query = query.filter(Column("category") == category)
            }

            if let tags = tags, !tags.isEmpty {
                for tag in tags {
                    query = query.filter(Column("tagsJson").like("%\"\(tag)\"%"))
                }
            }

            return try query.fetchCount(database)
        }
    }

    /// Get memories matching ANY of the specified tags (OR logic)
    /// Used for filter dropdowns where selecting multiple tags shows items matching any tag
    func getFilteredMemories(
        limit: Int = 200,
        offset: Int = 0,
        matchAnyTag: [String]? = nil,     // OR logic: matches any of these tags
        matchAnyCategory: [String]? = nil, // OR logic: matches any of these categories
        excludeTags: [String]? = nil,      // Exclude memories containing these tags
        includeDismissed: Bool = false
    ) async throws -> [ServerMemory] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            // Build SQL for complex OR/AND logic
            var conditions: [String] = ["deleted = 0"]
            var arguments: [DatabaseValue] = []

            if !includeDismissed {
                conditions.append("isDismissed = 0")
            }

            // Tag OR conditions
            if let tags = matchAnyTag, !tags.isEmpty {
                let tagConditions = tags.map { _ in "tagsJson LIKE ?" }.joined(separator: " OR ")
                conditions.append("(\(tagConditions))")
                for tag in tags {
                    if let dbValue = DatabaseValue(value: "%\"\(tag)\"%") {
                        arguments.append(dbValue)
                    }
                }
            }

            // Category OR conditions
            if let categories = matchAnyCategory, !categories.isEmpty {
                let placeholders = categories.map { _ in "?" }.joined(separator: ", ")
                conditions.append("category IN (\(placeholders))")
                for cat in categories {
                    if let dbValue = DatabaseValue(value: cat) {
                        arguments.append(dbValue)
                    }
                }
            }

            // Exclude tags
            if let excludeTags = excludeTags, !excludeTags.isEmpty {
                for tag in excludeTags {
                    conditions.append("tagsJson NOT LIKE ?")
                    if let dbValue = DatabaseValue(value: "%\"\(tag)\"%") {
                        arguments.append(dbValue)
                    }
                }
            }

            let sql = """
                SELECT * FROM memories
                WHERE \(conditions.joined(separator: " AND "))
                ORDER BY createdAt DESC
                LIMIT ? OFFSET ?
            """
            if let limitValue = DatabaseValue(value: limit) {
                arguments.append(limitValue)
            }
            if let offsetValue = DatabaseValue(value: offset) {
                arguments.append(offsetValue)
            }

            let records = try MemoryRecord.fetchAll(database, sql: sql, arguments: StatementArguments(arguments))
            return records.compactMap { $0.toServerMemory() }
        }
    }

    /// Search memories by content text (case-insensitive)
    /// Queries SQLite directly for efficient full-database search
    func searchLocalMemories(
        query searchText: String,
        limit: Int = 100,
        offset: Int = 0,
        category: String? = nil,
        tags: [String]? = nil,
        includeDismissed: Bool = false
    ) async throws -> [ServerMemory] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            var query = MemoryRecord
                .filter(Column("deleted") == false)

            if !includeDismissed {
                query = query.filter(Column("isDismissed") == false)
            }

            // Search in content (case-insensitive)
            if !searchText.isEmpty {
                query = query.filter(Column("content").like("%\(searchText)%"))
            }

            if let category = category {
                query = query.filter(Column("category") == category)
            }

            if let tags = tags, !tags.isEmpty {
                for tag in tags {
                    query = query.filter(Column("tagsJson").like("%\"\(tag)\"%"))
                }
            }

            let records = try query
                .order(Column("createdAt").desc)
                .limit(limit, offset: offset)
                .fetchAll(database)

            return records.compactMap { $0.toServerMemory() }
        }
    }

    /// Get count of unread tips from SQLite
    func getUnreadTipsCount() async throws -> Int {
        let db = try await ensureInitialized()

        return try await db.read { database in
            let sql = """
                SELECT COUNT(*) FROM memories
                WHERE deleted = 0 AND isDismissed = 0
                AND tagsJson LIKE '%"tips"%'
                AND isRead = 0
            """
            return try Int.fetchOne(database, sql: sql) ?? 0
        }
    }

    /// Get count of memories matching search query
    func searchLocalMemoriesCount(
        query searchText: String,
        category: String? = nil,
        tags: [String]? = nil,
        includeDismissed: Bool = false
    ) async throws -> Int {
        let db = try await ensureInitialized()

        return try await db.read { database in
            var query = MemoryRecord
                .filter(Column("deleted") == false)

            if !includeDismissed {
                query = query.filter(Column("isDismissed") == false)
            }

            if !searchText.isEmpty {
                query = query.filter(Column("content").like("%\(searchText)%"))
            }

            if let category = category {
                query = query.filter(Column("category") == category)
            }

            if let tags = tags, !tags.isEmpty {
                for tag in tags {
                    query = query.filter(Column("tagsJson").like("%\"\(tag)\"%"))
                }
            }

            return try query.fetchCount(database)
        }
    }

    /// Get a memory by local ID
    func getMemory(id: Int64) async throws -> MemoryRecord? {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try MemoryRecord.fetchOne(database, key: id)
        }
    }

    /// Get a memory by backend ID
    func getMemoryByBackendId(_ backendId: String) async throws -> MemoryRecord? {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try MemoryRecord
                .filter(Column("backendId") == backendId)
                .fetchOne(database)
        }
    }

    // MARK: - Bidirectional Sync Operations

    /// Sync a single ServerMemory to local storage (upsert)
    /// Used when fetching from API to cache locally
    @discardableResult
    func syncServerMemory(_ memory: ServerMemory) async throws -> Int64 {
        let db = try await ensureInitialized()

        return try await db.write { database -> Int64 in
            // Check if memory already exists by backendId
            if var existingRecord = try MemoryRecord
                .filter(Column("backendId") == memory.id)
                .fetchOne(database) {
                // Update existing record
                existingRecord.updateFrom(memory)
                try existingRecord.update(database)
                guard let recordId = existingRecord.id else {
                    throw MemoryStorageError.syncFailed("Record ID is nil after update")
                }
                return recordId
            } else {
                // Insert new record
                let newRecord = try MemoryRecord.from(memory).inserted(database)
                guard let recordId = newRecord.id else {
                    throw MemoryStorageError.syncFailed("Record ID is nil after insert")
                }
                return recordId
            }
        }
    }

    /// Sync multiple ServerMemory objects to local storage (batch upsert)
    /// Used for efficient background sync after API fetch
    func syncServerMemories(_ memories: [ServerMemory]) async throws {
        let db = try await ensureInitialized()

        let (skipped, adopted) = try await db.write { database -> (Int, Int) in
            var skipped = 0
            var adopted = 0
            for memory in memories {
                if var existingRecord = try MemoryRecord
                    .filter(Column("backendId") == memory.id)
                    .fetchOne(database) {
                    // Skip if local record is newer than incoming API data
                    // This prevents auto-refresh from overwriting recent local changes
                    if existingRecord.updatedAt > memory.updatedAt {
                        skipped += 1
                        continue
                    }
                    existingRecord.updateFrom(memory)
                    try existingRecord.update(database)
                } else if var orphan = try MemoryRecord
                    .filter(Column("backendSynced") == false)
                    .filter(Column("backendId") == nil)
                    .filter(Column("content") == memory.content)
                    .fetchOne(database) {
                    // Adopt orphaned local record: link it to the backend ID.
                    // This heals records where insertLocalMemory succeeded but
                    // markSynced hasn't run yet (or failed).
                    orphan.backendId = memory.id
                    orphan.backendSynced = true
                    orphan.updateFrom(memory)
                    try orphan.update(database)
                    adopted += 1
                } else {
                    _ = try MemoryRecord.from(memory).inserted(database)
                }
            }
            return (skipped, adopted)
        }

        if skipped > 0 || adopted > 0 {
            log("MemoryStorage: Synced \(memories.count - skipped) memories from backend (skipped \(skipped) newer local, adopted \(adopted) orphans)")
        } else {
            log("MemoryStorage: Synced \(memories.count) memories from backend")
        }
    }

    // MARK: - Local Extraction Operations

    /// Insert a locally extracted memory (before backend sync)
    /// Used by MemoryAssistant and AdviceAssistant
    @discardableResult
    func insertLocalMemory(_ record: MemoryRecord) async throws -> MemoryRecord {
        let db = try await ensureInitialized()

        var insertRecord = record
        insertRecord.backendSynced = false  // Mark as not yet synced

        let recordToInsert = insertRecord
        let inserted = try await db.write { database in
            try recordToInsert.inserted(database)
        }

        log("MemoryStorage: Inserted local memory (id: \(inserted.id ?? -1))")
        return inserted
    }

    /// Mark a local memory as synced with backend ID
    func markSynced(id: Int64, backendId: String) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard let record = try MemoryRecord.fetchOne(database, key: id) else {
                throw MemoryStorageError.recordNotFound
            }

            // Check if another record already has this backendId
            // (race: syncServerMemories inserted it from an API fetch before we got here)
            if let existing = try MemoryRecord
                .filter(Column("backendId") == backendId)
                .fetchOne(database) {
                // Another record owns this backendId — delete our local duplicate
                if existing.id != record.id {
                    try record.delete(database)
                    return
                }
            }

            var mutableRecord = record
            mutableRecord.backendId = backendId
            mutableRecord.backendSynced = true
            mutableRecord.updatedAt = Date()
            try mutableRecord.update(database)
        }

        log("MemoryStorage: Marked memory \(id) as synced (backendId: \(backendId))")
    }

    /// Get memories that haven't been synced to backend yet
    func getUnsyncedMemories() async throws -> [MemoryRecord] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try MemoryRecord
                .filter(Column("backendSynced") == false)
                .filter(Column("deleted") == false)
                .order(Column("createdAt").asc)
                .fetchAll(database)
        }
    }

    // MARK: - Update Operations

    /// Update memory read status
    func updateReadStatus(id: Int64, isRead: Bool) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try MemoryRecord.fetchOne(database, key: id) else {
                throw MemoryStorageError.recordNotFound
            }

            record.isRead = isRead
            record.updatedAt = Date()
            try record.update(database)
        }
    }

    /// Update memory dismissed status
    func updateDismissedStatus(id: Int64, isDismissed: Bool) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try MemoryRecord.fetchOne(database, key: id) else {
                throw MemoryStorageError.recordNotFound
            }

            record.isDismissed = isDismissed
            record.updatedAt = Date()
            try record.update(database)
        }
    }

    /// Mark all memories as read
    func markAllAsRead() async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "UPDATE memories SET isRead = 1, updatedAt = ? WHERE isRead = 0",
                arguments: [Date()]
            )
        }

        log("MemoryStorage: Marked all memories as read")
    }

    /// Soft delete a memory
    func deleteMemory(id: Int64) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try MemoryRecord.fetchOne(database, key: id) else {
                throw MemoryStorageError.recordNotFound
            }

            record.deleted = true
            record.updatedAt = Date()
            try record.update(database)
        }

        log("MemoryStorage: Soft deleted memory \(id)")
    }

    /// Soft delete a memory by backend ID
    func deleteMemoryByBackendId(_ backendId: String) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "UPDATE memories SET deleted = 1, updatedAt = ? WHERE backendId = ?",
                arguments: [Date(), backendId]
            )
        }

        log("MemoryStorage: Soft deleted memory with backendId \(backendId)")
    }

    /// Soft delete all memories
    func deleteAllMemories() async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "UPDATE memories SET deleted = 1, updatedAt = ? WHERE deleted = 0",
                arguments: [Date()]
            )
        }

        log("MemoryStorage: Soft deleted all memories")
    }

    /// Update content by backend ID
    func updateContentByBackendId(_ backendId: String, content: String) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "UPDATE memories SET content = ?, updatedAt = ? WHERE backendId = ?",
                arguments: [content, Date(), backendId]
            )
        }
    }

    /// Update visibility by backend ID
    func updateVisibilityByBackendId(_ backendId: String, visibility: String) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "UPDATE memories SET visibility = ?, updatedAt = ? WHERE backendId = ?",
                arguments: [visibility, Date(), backendId]
            )
        }
    }

    /// Update read status by backend ID
    func updateReadStatusByBackendId(_ backendId: String, isRead: Bool) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "UPDATE memories SET isRead = ?, updatedAt = ? WHERE backendId = ?",
                arguments: [isRead, Date(), backendId]
            )
        }
    }

    // MARK: - Stats

    /// Get memory storage statistics
    func getStats() async throws -> (total: Int, synced: Int, unsynced: Int, unread: Int) {
        let db = try await ensureInitialized()

        return try await db.read { database in
            let total = try MemoryRecord
                .filter(Column("deleted") == false)
                .fetchCount(database)

            let synced = try MemoryRecord
                .filter(Column("deleted") == false)
                .filter(Column("backendSynced") == true)
                .fetchCount(database)

            let unsynced = try MemoryRecord
                .filter(Column("deleted") == false)
                .filter(Column("backendSynced") == false)
                .fetchCount(database)

            let unread = try MemoryRecord
                .filter(Column("deleted") == false)
                .filter(Column("isRead") == false)
                .filter(Column("isDismissed") == false)
                .fetchCount(database)

            return (total, synced, unsynced, unread)
        }
    }

    // MARK: - Cleanup

    /// Permanently delete old dismissed memories
    func cleanupOldDismissedMemories(olderThan date: Date) async throws -> Int {
        let db = try await ensureInitialized()

        return try await db.write { database in
            let count = try Int.fetchOne(
                database,
                sql: "SELECT COUNT(*) FROM memories WHERE isDismissed = 1 AND updatedAt < ?",
                arguments: [date]
            ) ?? 0

            try database.execute(
                sql: "DELETE FROM memories WHERE isDismissed = 1 AND updatedAt < ?",
                arguments: [date]
            )

            return count
        }
    }
}
