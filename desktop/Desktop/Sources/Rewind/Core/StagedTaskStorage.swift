import Foundation
import GRDB

/// Actor-based storage manager for staged tasks awaiting promotion to action_items.
/// Mirrors a subset of ActionItemStorage methods but operates on the staged_tasks table.
actor StagedTaskStorage {
    static let shared = StagedTaskStorage()

    private var _dbQueue: DatabaseQueue?
    private var isInitialized = false

    private init() {}

    func invalidateCache() {
        _dbQueue = nil
        isInitialized = false
    }

    private func ensureInitialized() async throws -> DatabaseQueue {
        if let db = _dbQueue {
            return db
        }

        do {
            try await RewindDatabase.shared.initialize()
        } catch {
            log("StagedTaskStorage: Database initialization failed: \(error.localizedDescription)")
            throw error
        }

        guard let db = await RewindDatabase.shared.getDatabaseQueue() else {
            throw ActionItemStorageError.databaseNotInitialized
        }

        _dbQueue = db
        isInitialized = true
        return db
    }

    // MARK: - Insert

    @discardableResult
    func insertLocalStagedTask(_ record: StagedTaskRecord) async throws -> StagedTaskRecord {
        let db = try await ensureInitialized()

        var insertRecord = record
        insertRecord.backendSynced = false
        let recordToInsert = insertRecord

        let inserted = try await db.write { database in
            try recordToInsert.inserted(database)
        }

        log("StagedTaskStorage: Inserted staged task (id: \(inserted.id ?? -1))")
        return inserted
    }

    /// Insert with score shift — pushes existing tasks with same or lower score down by 1
    func insertWithScoreShift(_ record: StagedTaskRecord) async throws -> StagedTaskRecord {
        let db = try await ensureInitialized()

        var insertRecord = record
        insertRecord.backendSynced = false
        let recordToInsert = insertRecord

        let inserted = try await db.write { database in
            if let score = recordToInsert.relevanceScore {
                try database.execute(sql: """
                    UPDATE staged_tasks
                    SET relevanceScore = relevanceScore + 1
                    WHERE relevanceScore IS NOT NULL AND relevanceScore >= ?
                      AND completed = 0 AND deleted = 0
                """, arguments: [score])
            }
            return try recordToInsert.inserted(database)
        }

        log("StagedTaskStorage: Inserted with score shift (id: \(inserted.id ?? -1), score: \(inserted.relevanceScore ?? -1))")
        return inserted
    }

    // MARK: - Sync

    func markSynced(id: Int64, backendId: String) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try StagedTaskRecord.fetchOne(database, key: id) else {
                throw ActionItemStorageError.recordNotFound
            }

            record.backendId = backendId
            record.backendSynced = true
            record.updatedAt = Date()
            try record.update(database)
        }

        log("StagedTaskStorage: Marked staged task \(id) as synced (backendId: \(backendId))")
    }

    /// Get unsynced staged tasks for retry
    func getUnsyncedStagedTasks(limit: Int = 50) async throws -> [StagedTaskRecord] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try StagedTaskRecord
                .filter(Column("backendSynced") == false)
                .filter(Column("deleted") == false)
                .order(Column("createdAt").desc)
                .limit(limit)
                .fetchAll(database)
        }
    }

    // MARK: - Read

    /// Get all active (non-completed, non-deleted) staged tasks
    func getAllStagedTasks(limit: Int = 10000) async throws -> [TaskActionItem] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            let records = try StagedTaskRecord
                .filter(Column("deleted") == false)
                .filter(Column("completed") == false)
                .order(Column("createdAt").desc)
                .limit(limit)
                .fetchAll(database)

            return records.map { $0.toTaskActionItem() }
        }
    }

    /// Get staged tasks ordered by relevance score (best first)
    func getScoredStagedTasks(limit: Int = 100) async throws -> [TaskActionItem] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            let records = try StagedTaskRecord
                .filter(Column("deleted") == false)
                .filter(Column("completed") == false)
                .order(sql: "COALESCE(relevanceScore, 999999) ASC")
                .limit(limit)
                .fetchAll(database)

            return records.map { $0.toTaskActionItem() }
        }
    }

    /// Get all scored tasks with backend IDs for syncing scores to backend
    func getAllScoredTasks() async throws -> [(id: String, score: Int)] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try Row.fetchAll(database, sql: """
                SELECT backendId, relevanceScore FROM staged_tasks
                WHERE backendId IS NOT NULL AND relevanceScore IS NOT NULL
                  AND deleted = 0 AND completed = 0
            """).compactMap { row in
                guard let backendId: String = row["backendId"],
                      let score: Int = row["relevanceScore"] else { return nil }
                return (id: backendId, score: score)
            }
        }
    }

    // MARK: - Delete

    /// Hard-delete a staged task by backend ID (after promotion)
    func deleteByBackendId(_ backendId: String) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "DELETE FROM staged_tasks WHERE backendId = ?",
                arguments: [backendId]
            )
        }

        log("StagedTaskStorage: Hard-deleted staged task with backendId \(backendId)")
    }

    /// Hard-delete a staged task by local ID
    func deleteById(_ id: Int64) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "DELETE FROM staged_tasks WHERE id = ?",
                arguments: [id]
            )
        }

        log("StagedTaskStorage: Hard-deleted staged task with id \(id)")
    }

    // MARK: - Re-ranking

    /// Apply selective re-ranking from Gemini response
    func applySelectiveReranking(_ reranks: [(backendId: String, newPosition: Int)]) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            let rows = try Row.fetchAll(database, sql: """
                SELECT id, backendId, relevanceScore
                FROM staged_tasks
                WHERE completed = 0 AND deleted = 0
                ORDER BY COALESCE(relevanceScore, 999999) ASC
            """)

            var orderedIds: [String] = rows.compactMap { $0["backendId"] as? String }
            let rerankedSet = Set(reranks.map { $0.backendId })

            orderedIds.removeAll { rerankedSet.contains($0) }

            let sorted = reranks.sorted { $0.newPosition < $1.newPosition }
            for rerank in sorted {
                let insertIdx = max(0, min(rerank.newPosition - 1, orderedIds.count))
                orderedIds.insert(rerank.backendId, at: insertIdx)
            }

            let now = Date()
            for (index, backendId) in orderedIds.enumerated() {
                try database.execute(
                    sql: "UPDATE staged_tasks SET relevanceScore = ?, scoredAt = ?, updatedAt = ? WHERE backendId = ?",
                    arguments: [index + 1, now, now, backendId]
                )
            }
        }
    }

    // MARK: - Embedding

    func updateEmbedding(id: Int64, embedding: Data) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "UPDATE staged_tasks SET embedding = ? WHERE id = ?",
                arguments: [embedding, id]
            )
        }
    }

    func getAllEmbeddings() async throws -> [(id: Int64, embedding: Data)] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try Row.fetchAll(database, sql: """
                SELECT id, embedding FROM staged_tasks
                WHERE embedding IS NOT NULL
            """).compactMap { row in
                guard let id: Int64 = row["id"],
                      let embedding: Data = row["embedding"] else { return nil }
                return (id: id, embedding: embedding)
            }
        }
    }

    // MARK: - FTS Search

    func searchFTS(
        query: String,
        limit: Int = 20
    ) async throws -> [(id: Int64, description: String, relevanceScore: Int?)] {
        let db = try await ensureInitialized()
        // Sanitize FTS5 query: strip special characters that could be misinterpreted
        let sanitizedQuery = query.map { $0.isLetter || $0.isNumber || $0 == "*" || $0 == " " ? $0 : Character(" ") }
            .map(String.init).joined()
            .components(separatedBy: .whitespaces).filter { !$0.isEmpty }.joined(separator: " ")
        guard !sanitizedQuery.isEmpty else { return [] }

        return try await db.read { database in
            let sql = """
                SELECT s.id, s.description, s.relevanceScore
                FROM staged_tasks s
                JOIN staged_tasks_fts fts ON fts.rowid = s.id
                WHERE staged_tasks_fts MATCH ?
                  AND s.completed = 0 AND s.deleted = 0
                ORDER BY bm25(staged_tasks_fts) ASC LIMIT ?
            """

            return try Row.fetchAll(database, sql: sql, arguments: [sanitizedQuery, limit]).map { row in
                (
                    id: row["id"] as Int64,
                    description: row["description"] as String,
                    relevanceScore: row["relevanceScore"] as Int?
                )
            }
        }
    }

    // MARK: - Single Record Lookup

    /// Get a single staged task by local ID (for vector search fallback)
    func getStagedTask(id: Int64) async throws -> (id: Int64, description: String, relevanceScore: Int?, completed: Bool, deleted: Bool)? {
        let db = try await ensureInitialized()

        return try await db.read { database in
            guard let record = try StagedTaskRecord.fetchOne(database, key: id) else {
                return nil
            }
            return (id: record.id ?? id, description: record.description, relevanceScore: record.relevanceScore, completed: record.completed, deleted: record.deleted)
        }
    }

    // MARK: - Missing Embeddings

    /// Get staged tasks missing embeddings (for backfill)
    func getItemsMissingEmbeddings(limit: Int = 100) async throws -> [(id: Int64, description: String)] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try Row.fetchAll(database, sql: """
                SELECT id, description FROM staged_tasks
                WHERE embedding IS NULL AND deleted = 0
                ORDER BY createdAt DESC LIMIT ?
            """, arguments: [limit]).map { row in
                (
                    id: row["id"] as Int64,
                    description: row["description"] as String
                )
            }
        }
    }

    // MARK: - Count

    func countActiveStagedTasks() async throws -> Int {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try Int.fetchOne(database, sql: """
                SELECT COUNT(*) FROM staged_tasks WHERE completed = 0 AND deleted = 0
            """) ?? 0
        }
    }
}
