import Foundation
import GRDB

// MARK: - Goal Storage Error

enum GoalStorageError: LocalizedError {
    case databaseNotInitialized
    case recordNotFound
    case syncFailed(String)

    var errorDescription: String? {
        switch self {
        case .databaseNotInitialized:
            return "Goal storage database is not initialized"
        case .recordNotFound:
            return "Goal record not found"
        case .syncFailed(let message):
            return "Sync failed: \(message)"
        }
    }
}

// MARK: - Goal Storage Actor

actor GoalStorage {
    static let shared = GoalStorage()

    private var _dbQueue: DatabaseQueue?
    private var isInitialized = false

    private init() {}

    /// Invalidate cached DB queue (called on user switch/sign-out)
    func invalidateCache() {
        _dbQueue = nil
        isInitialized = false
    }

    /// Ensure database is initialized before use
    private func ensureInitialized() async throws -> DatabaseQueue {
        if let db = _dbQueue {
            return db
        }

        try await RewindDatabase.shared.initialize()
        guard let db = await RewindDatabase.shared.getDatabaseQueue() else {
            throw GoalStorageError.databaseNotInitialized
        }

        _dbQueue = db
        isInitialized = true
        return db
    }

    // MARK: - Read Operations

    /// Get local goals, optionally filtered to active-only
    func getLocalGoals(activeOnly: Bool = true) async throws -> [Goal] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            var query = GoalRecord
                .filter(Column("deleted") == false)

            if activeOnly {
                query = query.filter(Column("isActive") == true)
            }

            let records = try query
                .order(Column("createdAt").desc)
                .fetchAll(database)

            return records.compactMap { $0.toGoal() }
        }
    }

    // MARK: - Sync Operations

    /// Batch upsert from API response
    func syncServerGoals(_ goals: [Goal]) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            for goal in goals {
                if var existingRecord = try GoalRecord
                    .filter(Column("backendId") == goal.id)
                    .fetchOne(database) {
                    existingRecord.updateFrom(goal)
                    try existingRecord.update(database)
                } else {
                    _ = try GoalRecord.from(goal).inserted(database)
                }
            }
        }

        log("GoalStorage: Synced \(goals.count) goals from server")
    }

    /// Single upsert from API
    @discardableResult
    func syncServerGoal(_ goal: Goal) async throws -> Int64 {
        let db = try await ensureInitialized()

        return try await db.write { database -> Int64 in
            if var existingRecord = try GoalRecord
                .filter(Column("backendId") == goal.id)
                .fetchOne(database) {
                existingRecord.updateFrom(goal)
                try existingRecord.update(database)
                guard let recordId = existingRecord.id else {
                    throw GoalStorageError.syncFailed("Record ID is nil after update")
                }
                return recordId
            } else {
                let newRecord = try GoalRecord.from(goal).inserted(database)
                guard let recordId = newRecord.id else {
                    throw GoalStorageError.syncFailed("Record ID is nil after insert")
                }
                return recordId
            }
        }
    }

    // MARK: - Local Write Operations

    /// Insert a locally-created goal (before backend sync)
    @discardableResult
    func insertLocalGoal(_ record: GoalRecord) async throws -> GoalRecord {
        let db = try await ensureInitialized()

        var insertRecord = record
        insertRecord.backendSynced = false

        let recordToInsert = insertRecord
        let inserted = try await db.write { database in
            try recordToInsert.inserted(database)
        }

        log("GoalStorage: Inserted local goal (id: \(inserted.id ?? -1))")
        return inserted
    }

    /// Mark a local goal as synced with backend ID
    func markSynced(id: Int64, backendId: String) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try GoalRecord.fetchOne(database, key: id) else {
                throw GoalStorageError.recordNotFound
            }

            record.backendId = backendId
            record.backendSynced = true
            record.updatedAt = Date()
            try record.update(database)
        }

        log("GoalStorage: Marked goal \(id) as synced (backendId: \(backendId))")
    }

    /// Get unsynced goals for background sync
    func getUnsyncedGoals() async throws -> [GoalRecord] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try GoalRecord
                .filter(Column("backendSynced") == false)
                .filter(Column("deleted") == false)
                .order(Column("createdAt").asc)
                .fetchAll(database)
        }
    }

    // MARK: - Update Operations

    /// Update progress for a goal by backendId
    func updateProgress(backendId: String, currentValue: Double) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try GoalRecord
                .filter(Column("backendId") == backendId)
                .fetchOne(database) else {
                throw GoalStorageError.recordNotFound
            }

            record.currentValue = currentValue
            record.updatedAt = Date()
            try record.update(database)
        }
    }

    /// Soft-delete a goal by backendId
    func softDelete(backendId: String) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try GoalRecord
                .filter(Column("backendId") == backendId)
                .fetchOne(database) else {
                throw GoalStorageError.recordNotFound
            }

            record.deleted = true
            record.updatedAt = Date()
            try record.update(database)
        }

        log("GoalStorage: Soft deleted goal (backendId: \(backendId))")
    }

    /// Mark a goal as completed by backendId
    func markCompleted(backendId: String) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try GoalRecord
                .filter(Column("backendId") == backendId)
                .fetchOne(database) else {
                throw GoalStorageError.recordNotFound
            }

            record.isActive = false
            record.completedAt = Date()
            record.updatedAt = Date()
            try record.update(database)
        }

        log("GoalStorage: Marked goal completed (backendId: \(backendId))")
    }
}
