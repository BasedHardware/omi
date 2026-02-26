import Foundation
import GRDB

/// Actor-based storage manager for action items/tasks with bidirectional sync
/// Provides local-first caching for fast startup and background sync with backend
actor ActionItemStorage {
    static let shared = ActionItemStorage()

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
            log("ActionItemStorage: Database initialization failed: \(error.localizedDescription)")
            throw error
        }

        guard let db = await RewindDatabase.shared.getDatabaseQueue() else {
            throw ActionItemStorageError.databaseNotInitialized
        }

        _dbQueue = db
        isInitialized = true
        return db
    }

    // MARK: - Local-First Read Operations

    /// Get action items from local cache for instant display
    /// Returns TaskActionItem for full UI compatibility
    /// Supports filtering by category, source, and priority for efficient SQLite queries
    func getLocalActionItems(
        limit: Int = 50,
        offset: Int = 0,
        completed: Bool? = nil,
        includeDeleted: Bool = false,
        startDate: Date? = nil,
        category: String? = nil,
        source: String? = nil,
        priority: String? = nil
    ) async throws -> [TaskActionItem] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            var query = ActionItemRecord.all()
            // Show ALL local items (synced or not) for local-first experience

            if !includeDeleted {
                query = query.filter(Column("deleted") == false)
            }

            if let completed = completed {
                query = query.filter(Column("completed") == completed)
            }

            // Filter by start date (for 7-day filter)
            if let startDate = startDate {
                query = query.filter(Column("createdAt") >= startDate)
            }

            // Filter by category (check both tagsJson and legacy category column)
            if let category = category {
                query = query.filter(
                    Column("tagsJson").like("%\"\(category)\"%") ||
                    Column("category") == category
                )
            }

            // Filter by source
            if let source = source {
                query = query.filter(Column("source") == source)
            }

            // Filter by priority
            if let priority = priority {
                query = query.filter(Column("priority") == priority)
            }

            // Sort by sortOrder first (drag-and-drop), then due_at, created_at
            let records = try query
                .order(Column("sortOrder").ascNullsLast, Column("dueAt").ascNullsLast, Column("createdAt").desc)
                .limit(limit, offset: offset)
                .fetchAll(database)

            return records.map { $0.toTaskActionItem() }
        }
    }

    /// Get a single action item by its backend ID
    func getLocalActionItem(byBackendId backendId: String) async throws -> TaskActionItem? {
        let db = try await ensureInitialized()

        return try await db.read { database in
            guard let record = try ActionItemRecord
                .filter(Column("backendId") == backendId)
                .fetchOne(database) else {
                return nil
            }
            return record.toTaskActionItem()
        }
    }

    /// Get count of local action items
    func getLocalActionItemsCount(
        completed: Bool? = nil,
        includeDeleted: Bool = false,
        startDate: Date? = nil
    ) async throws -> Int {
        let db = try await ensureInitialized()

        return try await db.read { database in
            var query = ActionItemRecord.all()
            // Count ALL local items (synced or not) for local-first experience

            if !includeDeleted {
                query = query.filter(Column("deleted") == false)
            }

            if let completed = completed {
                query = query.filter(Column("completed") == completed)
            }

            if let startDate = startDate {
                query = query.filter(Column("createdAt") >= startDate)
            }

            return try query.fetchCount(database)
        }
    }

    /// Get action items with multiple filter values (OR within groups, AND between groups)
    /// Used when user selects multiple filters in the UI
    func getFilteredActionItems(
        limit: Int = 200,
        offset: Int = 0,
        completedStates: [Bool]? = nil,  // e.g., [true, false] for both done and todo
        includeDeleted: Bool = false,
        categories: [String]? = nil,     // OR logic: matches any category
        sources: [String]? = nil,        // OR logic: matches any source
        priorities: [String]? = nil,     // OR logic: matches any priority
        originCategories: [String]? = nil, // OR logic: matches any source_category in metadata
        dateAfter: Date? = nil,          // last7Days: dueAt >= date OR (dueAt IS NULL AND createdAt >= date)
        dueDateAfter: Date? = nil,       // dueAt >= date
        dueDateBefore: Date? = nil,      // dueAt < date
        dueDateIsNull: Bool? = nil,      // true = only tasks without dueAt
        createdAfter: Date? = nil        // createdAt >= date (independent of dueAt, unlike dateAfter)
    ) async throws -> [TaskActionItem] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            var query = ActionItemRecord.all()

            if !includeDeleted {
                query = query.filter(Column("deleted") == false)
            }

            // Filter by completed states (OR logic)
            if let states = completedStates, !states.isEmpty {
                if states.count == 1 {
                    query = query.filter(Column("completed") == states[0])
                }
                // If both true and false, no filter needed (show all)
            }

            // Filter by date (last7Days logic: dueAt >= date OR (dueAt IS NULL AND createdAt >= date))
            if let dateAfter = dateAfter {
                query = query.filter(
                    Column("dueAt") >= dateAfter ||
                    (Column("dueAt") == nil && Column("createdAt") >= dateAfter)
                )
            }

            // Filter by due date range (for dashboard overdue/today queries)
            if let dueDateAfter = dueDateAfter {
                query = query.filter(Column("dueAt") >= dueDateAfter)
            }
            if let dueDateBefore = dueDateBefore {
                query = query.filter(Column("dueAt") < dueDateBefore)
            }
            if let dueDateIsNull = dueDateIsNull {
                query = dueDateIsNull
                    ? query.filter(Column("dueAt") == nil)
                    : query.filter(Column("dueAt") != nil)
            }
            if let createdAfter = createdAfter {
                query = query.filter(Column("createdAt") >= createdAfter)
            }

            // Filter by categories (OR logic, checking tagsJson and legacy category)
            if let categories = categories, !categories.isEmpty {
                let tagConditions = categories.map { cat in
                    Column("tagsJson").like("%\"\(cat)\"%") || Column("category") == cat
                }
                if let combined = tagConditions.first {
                    let merged = tagConditions.dropFirst().reduce(combined) { result, next in result || next }
                    query = query.filter(merged)
                }
            }

            // Filter by sources (OR logic)
            if let sources = sources, !sources.isEmpty {
                query = query.filter(sources.contains(Column("source")))
            }

            // Filter by priorities (OR logic)
            if let priorities = priorities, !priorities.isEmpty {
                query = query.filter(priorities.contains(Column("priority")))
            }

            // Filter by origin categories (OR logic, checking metadataJson for source_category)
            if let originCategories = originCategories, !originCategories.isEmpty {
                let originConditions = originCategories.map { cat in
                    Column("metadataJson").like("%\"source_category\":\"\(cat)\"%")
                }
                if let combined = originConditions.first {
                    let merged = originConditions.dropFirst().reduce(combined) { result, next in result || next }
                    query = query.filter(merged)
                }
            }

            // Sort by sortOrder first (drag-and-drop), then due_at, created_at
            let records = try query
                .order(Column("sortOrder").ascNullsLast, Column("dueAt").ascNullsLast, Column("createdAt").desc)
                .limit(limit, offset: offset)
                .fetchAll(database)

            return records.map { $0.toTaskActionItem() }
        }
    }

    /// Search action items by description text (case-insensitive)
    /// Queries SQLite directly for efficient full-database search
    func searchLocalActionItems(
        query searchText: String,
        limit: Int = 100,
        offset: Int = 0,
        completed: Bool? = nil,
        includeDeleted: Bool = false,
        category: String? = nil,
        source: String? = nil,
        priority: String? = nil
    ) async throws -> [TaskActionItem] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            var query = ActionItemRecord.all()

            if !includeDeleted {
                query = query.filter(Column("deleted") == false)
            }

            // Search in description (case-insensitive)
            if !searchText.isEmpty {
                query = query.filter(Column("description").like("%\(searchText)%"))
            }

            if let completed = completed {
                query = query.filter(Column("completed") == completed)
            }

            if let category = category {
                query = query.filter(
                    Column("tagsJson").like("%\"\(category)\"%") ||
                    Column("category") == category
                )
            }

            if let source = source {
                query = query.filter(Column("source") == source)
            }

            if let priority = priority {
                query = query.filter(Column("priority") == priority)
            }

            // Sort by sortOrder first (drag-and-drop), then due_at, created_at
            let records = try query
                .order(Column("sortOrder").ascNullsLast, Column("dueAt").ascNullsLast, Column("createdAt").desc)
                .limit(limit, offset: offset)
                .fetchAll(database)

            return records.map { $0.toTaskActionItem() }
        }
    }

    /// Get count of action items matching search and filters
    func searchLocalActionItemsCount(
        query searchText: String,
        completed: Bool? = nil,
        includeDeleted: Bool = false,
        category: String? = nil,
        source: String? = nil,
        priority: String? = nil
    ) async throws -> Int {
        let db = try await ensureInitialized()

        return try await db.read { database in
            var query = ActionItemRecord.all()

            if !includeDeleted {
                query = query.filter(Column("deleted") == false)
            }

            if !searchText.isEmpty {
                query = query.filter(Column("description").like("%\(searchText)%"))
            }

            if let completed = completed {
                query = query.filter(Column("completed") == completed)
            }

            if let category = category {
                query = query.filter(
                    Column("tagsJson").like("%\"\(category)\"%") ||
                    Column("category") == category
                )
            }

            if let source = source {
                query = query.filter(Column("source") == source)
            }

            if let priority = priority {
                query = query.filter(Column("priority") == priority)
            }

            return try query.fetchCount(database)
        }
    }

    /// Get count of action items by filter criteria (for filter tag counts)
    func getFilterCounts() async throws -> (
        todo: Int,
        done: Int,
        deleted: Int,
        deletedByAI: Int,
        deletedByUser: Int,
        categories: [String: Int],
        sources: [String: Int],
        priorities: [String: Int],
        origins: [String: Int]
    ) {
        let db = try await ensureInitialized()

        return try await db.read { database in
            let todo = try ActionItemRecord
                .filter(Column("deleted") == false)
                .filter(Column("completed") == false)
                .fetchCount(database)

            let done = try ActionItemRecord
                .filter(Column("deleted") == false)
                .filter(Column("completed") == true)
                .fetchCount(database)

            let deleted = try ActionItemRecord
                .filter(Column("deleted") == true)
                .fetchCount(database)

            let deletedByAI = try Int.fetchOne(database, sql: """
                SELECT COUNT(*) FROM action_items
                WHERE deleted = 1 AND (deletedBy IS NULL OR deletedBy != 'user')
            """) ?? 0

            let deletedByUser = try ActionItemRecord
                .filter(Column("deleted") == true)
                .filter(Column("deletedBy") == "user")
                .fetchCount(database)

            // Category/tag counts - count each known tag using LIKE on tagsJson
            // Only count incomplete tasks so numbers match the default (todo) view
            var categories: [String: Int] = [:]
            let knownTags = ["personal", "work", "feature", "bug", "code", "research", "communication", "finance", "health", "other"]
            for tag in knownTags {
                let count = try Int.fetchOne(database, sql: """
                    SELECT COUNT(*) FROM action_items
                    WHERE deleted = 0 AND completed = 0 AND (tagsJson LIKE ? OR (tagsJson IS NULL AND category = ?))
                """, arguments: ["%\"\(tag)\"%", tag]) ?? 0
                if count > 0 {
                    categories[tag] = count
                }
            }

            // Source counts (incomplete only to match default view)
            var sources: [String: Int] = [:]
            let sourceRows = try Row.fetchAll(database, sql: """
                SELECT source, COUNT(*) as count FROM action_items
                WHERE deleted = 0 AND completed = 0 AND source IS NOT NULL
                GROUP BY source
            """)
            for row in sourceRows {
                if let src: String = row["source"], let count: Int = row["count"] {
                    sources[src] = count
                }
            }

            // Priority counts (incomplete only to match default view)
            var priorities: [String: Int] = [:]
            let priorityRows = try Row.fetchAll(database, sql: """
                SELECT priority, COUNT(*) as count FROM action_items
                WHERE deleted = 0 AND completed = 0 AND priority IS NOT NULL
                GROUP BY priority
            """)
            for row in priorityRows {
                if let pri: String = row["priority"], let count: Int = row["count"] {
                    priorities[pri] = count
                }
            }

            // Origin (source_category) counts from metadataJson
            var origins: [String: Int] = [:]
            let knownOrigins = ["direct_request", "self_generated", "calendar_driven", "reactive", "external_system", "other"]
            for origin in knownOrigins {
                let count = try Int.fetchOne(database, sql: """
                    SELECT COUNT(*) FROM action_items
                    WHERE deleted = 0 AND completed = 0 AND metadataJson LIKE ?
                """, arguments: ["%\"source_category\":\"\(origin)\"%"]) ?? 0
                if count > 0 {
                    origins[origin] = count
                }
            }

            return (todo, done, deleted, deletedByAI, deletedByUser, categories, sources, priorities, origins)
        }
    }

    /// Get an action item by local ID
    func getActionItem(id: Int64) async throws -> ActionItemRecord? {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try ActionItemRecord.fetchOne(database, key: id)
        }
    }

    /// Get an action item by backend ID
    func getActionItemByBackendId(_ backendId: String) async throws -> ActionItemRecord? {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try ActionItemRecord
                .filter(Column("backendId") == backendId)
                .fetchOne(database)
        }
    }

    // MARK: - Bidirectional Sync Operations

    /// Sync a single ActionItem to local storage (upsert)
    @discardableResult
    func syncActionItem(_ item: ActionItem, conversationId: String? = nil) async throws -> Int64 {
        let db = try await ensureInitialized()

        return try await db.write { database -> Int64 in
            if var existingRecord = try ActionItemRecord
                .filter(Column("backendId") == item.id)
                .fetchOne(database) {
                existingRecord.updateFrom(item)
                try existingRecord.update(database)
                guard let recordId = existingRecord.id else {
                    throw ActionItemStorageError.syncFailed("Record ID is nil after update")
                }
                return recordId
            } else {
                // Insert new record, catching UNIQUE constraint from concurrent syncs
                do {
                    let newRecord = try ActionItemRecord.from(item, conversationId: conversationId).inserted(database)
                    guard let recordId = newRecord.id else {
                        throw ActionItemStorageError.syncFailed("Record ID is nil after insert")
                    }
                    return recordId
                } catch let dbError as DatabaseError where dbError.resultCode == .SQLITE_CONSTRAINT {
                    // Race: another sync path already inserted this backendId — update instead
                    if var record = try ActionItemRecord.filter(Column("backendId") == item.id).fetchOne(database) {
                        record.updateFrom(item)
                        try record.update(database)
                        return record.id ?? 0
                    }
                    throw dbError
                }
            }
        }
    }

    /// Sync multiple ActionItems to local storage (batch upsert)
    func syncActionItems(_ items: [ActionItem]) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            for item in items {
                if var existingRecord = try ActionItemRecord
                    .filter(Column("backendId") == item.id)
                    .fetchOne(database) {
                    existingRecord.updateFrom(item)
                    try existingRecord.update(database)
                } else {
                    do {
                        let newRecord = ActionItemRecord.from(item)
                        try newRecord.insert(database)
                    } catch let dbError as DatabaseError where dbError.resultCode == .SQLITE_CONSTRAINT {
                        // Race: record already exists — update instead
                        if var record = try ActionItemRecord.filter(Column("backendId") == item.id).fetchOne(database) {
                            record.updateFrom(item)
                            try record.update(database)
                        }
                    }
                }
            }
        }

        log("ActionItemStorage: Synced \(items.count) action items from backend")
    }

    /// Sync multiple TaskActionItems to local storage (batch upsert with full data)
    /// - Parameter overrideStagedDeletions: When true, API data overrides local "staged" deletions
    ///   (used during full sync where we have the complete dataset). When false (default),
    ///   staged deletions are preserved to avoid un-deleting tasks during partial refreshes.
    func syncTaskActionItems(_ items: [TaskActionItem], overrideStagedDeletions: Bool = false) async throws {
        let db = try await ensureInitialized()

        let (skipped, adopted) = try await db.write { database -> (Int, Int) in
            var skipped = 0
            var adopted = 0
            for item in items {
                if var existingRecord = try ActionItemRecord
                    .filter(Column("backendId") == item.id)
                    .fetchOne(database) {
                    // Skip if local record is newer than incoming API data AND the
                    // local change is very recent (< 60s). This protects in-flight
                    // optimistic updates (e.g. toggling a task) from being overwritten
                    // by stale auto-refresh data. Beyond 60s, trust the API as source
                    // of truth — this prevents failed optimistic updates from persisting
                    // forever (e.g. user toggled on desktop but API call failed/app crashed).
                    let incomingTimestamp = item.updatedAt ?? item.createdAt
                    let isLocalStagedGuess = overrideStagedDeletions && existingRecord.deletedBy == "staged"
                    let isRecentLocalChange = Date().timeIntervalSince(existingRecord.updatedAt) < 60
                    if isRecentLocalChange && existingRecord.updatedAt > incomingTimestamp && !isLocalStagedGuess {
                        skipped += 1
                        continue
                    }
                    existingRecord.updateFrom(item)
                    try existingRecord.update(database)
                } else if var orphan = try ActionItemRecord
                    .filter(Column("backendSynced") == false)
                    .filter(Column("backendId") == nil || Column("backendId") == "")
                    .filter(Column("description") == item.description)
                    .filter(Column("source") == (item.source ?? ""))
                    .fetchOne(database) {
                    // Adopt orphaned local record: link it to the backend ID.
                    // This heals records where saveTaskToSQLite succeeded but
                    // markSynced failed (e.g. app crash between backend sync and local update).
                    orphan.backendId = item.id
                    orphan.backendSynced = true
                    orphan.updateFrom(item)
                    try orphan.update(database)
                    adopted += 1
                } else {
                    var newRecord = ActionItemRecord.from(item)
                    // Auto-assign max+1 score for tasks arriving without a score
                    if newRecord.relevanceScore == nil {
                        let maxScore = try Int.fetchOne(database, sql: """
                            SELECT COALESCE(MAX(relevanceScore), 0) FROM action_items
                            WHERE completed = 0 AND deleted = 0 AND relevanceScore IS NOT NULL
                        """) ?? 0
                        newRecord.relevanceScore = maxScore + 1
                        newRecord.scoredAt = Date()
                    }
                    try newRecord.insert(database)
                }
            }
            return (skipped, adopted)
        }

        if skipped > 0 || adopted > 0 {
            log("ActionItemStorage: Synced \(items.count) task action items from backend (skipped \(skipped) newer local, adopted \(adopted) orphans)")
        } else {
            log("ActionItemStorage: Synced \(items.count) task action items from backend")
        }
    }


    /// Hard-delete incomplete tasks NOT present in the API response.
    /// This cleans up tasks that were moved to staged_tasks or deleted on the backend
    /// but still linger in local SQLite, preventing phantom entries in the task list.
    func markAbsentTasksAsStaged(apiIds: Set<String>) async throws {
        let db = try await ensureInitialized()

        let deleted = try await db.write { database -> Int in
            let records = try ActionItemRecord
                .filter(Column("completed") == false)
                .filter(Column("deleted") == false)
                .filter(Column("backendId") != nil)
                .fetchAll(database)

            var count = 0
            for record in records {
                guard let backendId = record.backendId, !backendId.isEmpty else { continue }
                if !apiIds.contains(backendId) {
                    try record.delete(database)
                    count += 1
                }
            }
            return count
        }

        if deleted > 0 {
            log("ActionItemStorage: Hard-deleted \(deleted) absent tasks during full sync")
        }
    }

    /// Hard-delete local tasks whose backendId is NOT in the given API set.
    /// Only targets synced records (backendSynced=true, backendId present) to avoid
    /// deleting locally-created tasks that haven't been pushed yet.
    /// Returns the number of records deleted.
    func hardDeleteAbsentTasks(apiIds: Set<String>) async throws -> Int {
        let db = try await ensureInitialized()

        let deleted = try await db.write { database -> Int in
            let records = try ActionItemRecord
                .filter(Column("completed") == false)
                .filter(Column("deleted") == false)
                .filter(Column("backendId") != nil)
                .filter(Column("backendSynced") == true)
                .fetchAll(database)

            var count = 0
            for record in records {
                guard let backendId = record.backendId, !backendId.isEmpty else { continue }
                if !apiIds.contains(backendId) {
                    try database.execute(
                        sql: "DELETE FROM action_items WHERE id = ?",
                        arguments: [record.id]
                    )
                    count += 1
                }
            }
            return count
        }

        if deleted > 0 {
            log("ActionItemStorage: hard-deleted \(deleted) absent tasks")
        }

        return deleted
    }

    /// Returns all active scored tasks for batch-syncing scores to backend
    func getAllScoredTasks() async throws -> [TaskActionItem] {
        let db = try await ensureInitialized()
        return try await db.read { database in
            try ActionItemRecord
                .filter(Column("deleted") == false && Column("completed") == false && Column("relevanceScore") != nil)
                .fetchAll(database)
                .map { $0.toTaskActionItem() }
        }
    }

    /// Permanently delete an action item from local cache by backend ID.
    /// Used when user explicitly deletes a task.
    func hardDeleteByBackendId(_ backendId: String) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "DELETE FROM action_items WHERE backendId = ?",
                arguments: [backendId]
            )
        }

        log("ActionItemStorage: Hard deleted action item with backendId \(backendId)")
    }

    // MARK: - Local Extraction Operations

    /// Insert a locally extracted action item (before backend sync)
    @discardableResult
    func insertLocalActionItem(_ record: ActionItemRecord) async throws -> ActionItemRecord {
        let db = try await ensureInitialized()

        var insertRecord = record
        insertRecord.backendSynced = false
        let recordToInsert = insertRecord

        let inserted = try await db.write { database in
            try recordToInsert.inserted(database)
        }

        log("ActionItemStorage: Inserted local action item (id: \(inserted.id ?? -1))")
        return inserted
    }

    /// Insert a screen observation (context captured during task extraction)
    @discardableResult
    func insertObservation(_ record: ObservationRecord) async throws -> ObservationRecord {
        let db = try await ensureInitialized()

        let inserted = try await db.write { database in
            try record.inserted(database)
        }

        log("ActionItemStorage: Inserted observation (id: \(inserted.id ?? -1), app: \(inserted.appName), hasTask: \(inserted.hasTask))")
        return inserted
    }

    /// Mark a local action item as synced with backend ID
    func markSynced(id: Int64, backendId: String) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try ActionItemRecord.fetchOne(database, key: id) else {
                throw ActionItemStorageError.recordNotFound
            }

            record.backendId = backendId
            record.backendSynced = true
            record.updatedAt = Date()
            try record.update(database)
        }

        log("ActionItemStorage: Marked action item \(id) as synced (backendId: \(backendId))")
    }

    /// Get action items that haven't been synced to backend yet
    func getUnsyncedActionItems() async throws -> [ActionItemRecord] {
        let db = try await ensureInitialized()
        let ageThreshold = Date().addingTimeInterval(-30)

        return try await db.read { database in
            try ActionItemRecord
                .filter(Column("backendSynced") == false)
                .filter(Column("backendId") == nil || Column("backendId") == "")
                .filter(Column("deleted") == false)
                .filter(Column("createdAt") < ageThreshold)
                .order(Column("createdAt").asc)
                .fetchAll(database)
        }
    }

    // MARK: - Update Operations

    /// Update action item completion status
    func updateCompletedStatus(id: Int64, completed: Bool) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try ActionItemRecord.fetchOne(database, key: id) else {
                throw ActionItemStorageError.recordNotFound
            }

            record.completed = completed
            record.updatedAt = Date()
            try record.update(database)
        }
    }

    /// Hard-delete an action item by local SQLite ID
    func deleteActionItem(id: Int64) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard let record = try ActionItemRecord.fetchOne(database, key: id) else {
                throw ActionItemStorageError.recordNotFound
            }

            try record.delete(database)
        }

        log("ActionItemStorage: Hard-deleted action item \(id)")
    }

    /// Optimistically update completion status locally (before API call)
    /// Sets updatedAt to Date() so auto-refresh timestamp check skips this record
    func updateCompletionStatus(backendId: String, completed: Bool) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try ActionItemRecord
                .filter(Column("backendId") == backendId)
                .fetchOne(database) else {
                throw ActionItemStorageError.recordNotFound
            }
            record.completed = completed
            record.updatedAt = Date()
            try record.update(database)
        }

        log("ActionItemStorage: Locally set completed=\(completed) for \(backendId)")
    }

    /// Optimistically update task fields locally (before API call)
    /// Sets updatedAt to Date() so auto-refresh timestamp check skips this record
    func updateActionItemFields(
        backendId: String,
        description: String? = nil,
        dueAt: Date? = nil,
        priority: String? = nil,
        metadata: [String: Any]? = nil,
        recurrenceRule: String? = nil
    ) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try ActionItemRecord
                .filter(Column("backendId") == backendId)
                .fetchOne(database) else {
                throw ActionItemStorageError.recordNotFound
            }
            if let description = description {
                record.description = description
            }
            if let dueAt = dueAt {
                record.dueAt = dueAt
            }
            if let priority = priority {
                record.priority = priority
            }
            if let metadata = metadata {
                record.setMetadata(metadata)
            }
            if let recurrenceRule = recurrenceRule {
                record.recurrenceRule = recurrenceRule.isEmpty ? nil : recurrenceRule
            }
            record.updatedAt = Date()
            try record.update(database)
        }

        log("ActionItemStorage: Locally updated fields for \(backendId)")
    }

    /// Batch update sort orders and indent levels in SQLite
    func updateSortOrders(_ updates: [(backendId: String, sortOrder: Int, indentLevel: Int)]) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            for update in updates {
                try database.execute(
                    sql: "UPDATE action_items SET sortOrder = ?, indentLevel = ?, updatedAt = ? WHERE backendId = ?",
                    arguments: [update.sortOrder, update.indentLevel, Date(), update.backendId]
                )
            }
        }

        log("ActionItemStorage: Updated sort orders for \(updates.count) items")
    }

    /// Un-soft-delete an action item by backend ID (for undo)
    func undeleteActionItemByBackendId(_ backendId: String) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "UPDATE action_items SET deleted = 0, deletedBy = NULL, updatedAt = ? WHERE backendId = ?",
                arguments: [Date(), backendId]
            )
        }

        log("ActionItemStorage: Undeleted action item with backendId \(backendId)")
    }

    /// Purge all soft-deleted items from local SQLite (one-time cleanup during full sync)
    func purgeAllSoftDeletedItems() async throws -> Int {
        let db = try await ensureInitialized()

        let count = try await db.write { database -> Int in
            let count = try Int.fetchOne(database, sql: "SELECT COUNT(*) FROM action_items WHERE deleted = 1") ?? 0
            if count > 0 {
                try database.execute(sql: "DELETE FROM action_items WHERE deleted = 1")
            }
            return count
        }

        if count > 0 {
            log("ActionItemStorage: Purged \(count) soft-deleted items from SQLite")
        }
        return count
    }

    /// Hard-delete an action item by backend ID
    func deleteActionItemByBackendId(_ backendId: String, deletedBy: String? = nil) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "DELETE FROM action_items WHERE backendId = ?",
                arguments: [backendId]
            )
        }

        log("ActionItemStorage: Hard-deleted action item with backendId \(backendId)")
    }

    // MARK: - FTS5 Search & Context Methods

    /// Full-text search on action item descriptions using FTS5 with BM25 ranking
    func searchFTS(
        query: String,
        limit: Int = 20,
        includeCompleted: Bool = true,
        includeDeleted: Bool = false
    ) async throws -> [(id: Int64, description: String, completed: Bool, deleted: Bool, deletedBy: String?, relevanceScore: Int?)] {
        let db = try await ensureInitialized()
        // Sanitize FTS5 query: strip special characters that could be misinterpreted
        let sanitizedQuery = query.map { $0.isLetter || $0.isNumber || $0 == "*" || $0 == " " ? $0 : Character(" ") }
            .map(String.init).joined()
            .components(separatedBy: .whitespaces).filter { !$0.isEmpty }.joined(separator: " ")
        guard !sanitizedQuery.isEmpty else { return [] }

        return try await db.read { database in
            var sql = """
                SELECT a.id, a.description, a.completed, a.deleted, a.deletedBy, a.relevanceScore
                FROM action_items a
                JOIN action_items_fts fts ON fts.rowid = a.id
                WHERE action_items_fts MATCH ?
                """
            var arguments: [DatabaseValueConvertible] = [sanitizedQuery]

            if !includeCompleted {
                sql += " AND a.completed = 0"
            }
            if !includeDeleted {
                sql += " AND a.deleted = 0"
            }

            sql += " ORDER BY bm25(action_items_fts) ASC LIMIT ?"
            arguments.append(limit)

            return try Row.fetchAll(database, sql: sql, arguments: StatementArguments(arguments)).map { row in
                (
                    id: row["id"] as Int64,
                    description: row["description"] as String,
                    completed: row["completed"] as Bool,
                    deleted: row["deleted"] as Bool,
                    deletedBy: row["deletedBy"] as String?,
                    relevanceScore: row["relevanceScore"] as Int?
                )
            }
        }
    }

    /// Get active tasks with the highest relevance (lowest score = most important)
    func getTopRelevanceTasks(limit: Int = 30) async throws -> [(id: Int64, description: String, priority: String?, relevanceScore: Int?)] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try Row.fetchAll(database, sql: """
                SELECT id, description, priority, relevanceScore FROM action_items
                WHERE completed = 0 AND deleted = 0 AND relevanceScore IS NOT NULL
                ORDER BY relevanceScore ASC LIMIT ?
            """, arguments: [limit]).map { row in
                (
                    id: row["id"] as Int64,
                    description: row["description"] as String,
                    priority: row["priority"] as String?,
                    relevanceScore: row["relevanceScore"] as Int?
                )
            }
        }
    }

    /// Get most recently created active tasks
    func getRecentActiveTasks(limit: Int = 30) async throws -> [(id: Int64, description: String, priority: String?, relevanceScore: Int?)] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try Row.fetchAll(database, sql: """
                SELECT id, description, priority, relevanceScore FROM action_items
                WHERE completed = 0 AND deleted = 0
                ORDER BY createdAt DESC LIMIT ?
            """, arguments: [limit]).map { row in
                (
                    id: row["id"] as Int64,
                    description: row["description"] as String,
                    priority: row["priority"] as String?,
                    relevanceScore: row["relevanceScore"] as Int?
                )
            }
        }
    }

    /// One-time backfill: assign max+1 sequentially to all active unscored tasks.
    /// Returns the number of tasks that were backfilled.
    func backfillUnscoredTasks() async throws -> Int {
        let db = try await ensureInitialized()

        return try await db.write { database in
            let maxScore = try Int.fetchOne(database, sql: """
                SELECT COALESCE(MAX(relevanceScore), 0) FROM action_items
                WHERE completed = 0 AND deleted = 0 AND relevanceScore IS NOT NULL
            """) ?? 0

            let unscoredIds = try Int64.fetchAll(database, sql: """
                SELECT id FROM action_items
                WHERE completed = 0 AND deleted = 0 AND relevanceScore IS NULL
                ORDER BY createdAt ASC
            """)

            guard !unscoredIds.isEmpty else { return 0 }

            for (index, id) in unscoredIds.enumerated() {
                try database.execute(
                    sql: "UPDATE action_items SET relevanceScore = ? WHERE id = ?",
                    arguments: [maxScore + 1 + index, id]
                )
            }

            return unscoredIds.count
        }
    }

    /// Get the current relevance score range (min and max) for active tasks
    func getRelevanceScoreRange() async throws -> (min: Int, max: Int) {
        let db = try await ensureInitialized()

        return try await db.read { database in
            let row = try Row.fetchOne(database, sql: """
                SELECT COALESCE(MIN(relevanceScore), 0) as minScore,
                       COALESCE(MAX(relevanceScore), 0) as maxScore
                FROM action_items
                WHERE completed = 0 AND deleted = 0 AND relevanceScore IS NOT NULL
            """)
            return (
                min: row?["minScore"] as? Int ?? 0,
                max: row?["maxScore"] as? Int ?? 0
            )
        }
    }

    /// Insert a task with a specific relevanceScore, shifting existing tasks at that score
    /// and below down by 1 to maintain uniqueness
    func insertWithScoreShift(_ record: ActionItemRecord) async throws -> ActionItemRecord {
        let db = try await ensureInitialized()

        var insertRecord = record
        insertRecord.backendSynced = false
        let recordToInsert = insertRecord

        let inserted = try await db.write { database in
            // Shift all active tasks at this score and below down by 1 (push less important tasks further down)
            // Score 1 = most important (top), so shifting down means incrementing scores >= this one
            if let score = recordToInsert.relevanceScore {
                try database.execute(sql: """
                    UPDATE action_items
                    SET relevanceScore = relevanceScore + 1
                    WHERE relevanceScore IS NOT NULL AND relevanceScore >= ?
                      AND completed = 0 AND deleted = 0
                """, arguments: [score])
            }

            return try recordToInsert.inserted(database)
        }

        log("ActionItemStorage: Inserted with score shift (id: \(inserted.id ?? -1), score: \(inserted.relevanceScore ?? -1))")
        return inserted
    }

    /// Compact relevance scores after a task is completed or deleted.
    /// Shifts all scores above the removed score down by 1 to fill the gap.
    func compactScoresAfterRemoval(removedScore: Int) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            let now = Date()
            try database.execute(sql: """
                UPDATE action_items
                SET relevanceScore = relevanceScore - 1, updatedAt = ?
                WHERE relevanceScore IS NOT NULL AND relevanceScore > ?
                  AND completed = 0 AND deleted = 0
            """, arguments: [now, removedScore])
        }
        log("ActionItemStorage: Compacted scores after removing score \(removedScore)")
    }

    /// Get recent completed tasks
    func getRecentCompletedTasks(limit: Int = 10) async throws -> [(id: Int64, description: String)] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try Row.fetchAll(database, sql: """
                SELECT id, description FROM action_items
                WHERE completed = 1 AND deleted = 0
                ORDER BY updatedAt DESC LIMIT ?
            """, arguments: [limit]).map { row in
                (
                    id: row["id"] as Int64,
                    description: row["description"] as String
                )
            }
        }
    }

    /// Get recent user-deleted tasks (deletedBy = "user")
    func getRecentDeletedTasks(limit: Int = 10, deletedBy: String? = "user") async throws -> [(id: Int64, description: String)] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            var sql = "SELECT id, description FROM action_items WHERE deleted = 1"
            var arguments: [DatabaseValueConvertible] = []

            if let deletedBy = deletedBy {
                sql += " AND deletedBy = ?"
                arguments.append(deletedBy)
            }

            sql += " ORDER BY updatedAt DESC LIMIT ?"
            arguments.append(limit)

            return try Row.fetchAll(database, sql: sql, arguments: StatementArguments(arguments)).map { row in
                (
                    id: row["id"] as Int64,
                    description: row["description"] as String
                )
            }
        }
    }

    /// Get all embeddings for loading into memory index
    func getAllEmbeddings() async throws -> [(id: Int64, embedding: Data)] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try Row.fetchAll(database, sql: """
                SELECT id, embedding FROM action_items
                WHERE embedding IS NOT NULL
            """).compactMap { row in
                guard let id: Int64 = row["id"],
                      let embedding: Data = row["embedding"] else { return nil }
                return (id: id, embedding: embedding)
            }
        }
    }

    /// Get action items missing embeddings (for backfill)
    func getItemsMissingEmbeddings(limit: Int = 100) async throws -> [(id: Int64, description: String)] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try Row.fetchAll(database, sql: """
                SELECT id, description FROM action_items
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

    /// Store embedding BLOB for a specific action item
    func updateEmbedding(id: Int64, embedding: Data) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "UPDATE action_items SET embedding = ? WHERE id = ?",
                arguments: [embedding, id]
            )
        }
    }

    // MARK: - Relevance Scores

    /// Clear all relevance scores (for force re-scoring)
    func clearAllRelevanceScores() async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "UPDATE action_items SET relevanceScore = NULL, scoredAt = NULL WHERE relevanceScore IS NOT NULL"
            )
        }
    }

    /// Get ALL incomplete AI tasks regardless of score status (for full rescore)
    func getAllAITasks(limit: Int = 10000) async throws -> [TaskActionItem] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            let records = try ActionItemRecord
                .filter(Column("deleted") == false)
                .filter(Column("completed") == false)
                .filter(Column("source") != "manual")
                .order(Column("dueAt").ascNullsLast, Column("createdAt").desc)
                .limit(limit)
                .fetchAll(database)

            return records.map { $0.toTaskActionItem() }
        }
    }

    /// Get AI tasks that have been scored, ordered by score ascending (1 = most important)
    /// - Parameter minDate: If set, only return tasks created or due after this date
    func getScoredAITasks(limit: Int = 10000, minDate: Date? = nil) async throws -> [TaskActionItem] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            var request = ActionItemRecord
                .filter(Column("deleted") == false)
                .filter(Column("completed") == false)
                .filter(Column("source") != "manual")
                .filter(Column("relevanceScore") != nil)

            if let minDate = minDate {
                // Task must be visible in UI: created or due within the date window
                request = request.filter(
                    Column("createdAt") >= minDate || Column("dueAt") >= minDate
                )
            }

            let records = try request
                .order(Column("relevanceScore").asc)
                .limit(limit)
                .fetchAll(database)

            return records.map { $0.toTaskActionItem() }
        }
    }

    /// Get the top scored AI task with no due date (score 1 = most important)
    func getTopScoredNoDeadlineTask() async throws -> TaskActionItem? {
        let db = try await ensureInitialized()

        return try await db.read { database in
            guard let record = try ActionItemRecord
                .filter(Column("deleted") == false)
                .filter(Column("completed") == false)
                .filter(Column("source") != "manual")
                .filter(Column("relevanceScore") != nil)
                .filter(Column("dueAt") == nil)
                .order(Column("relevanceScore").asc)
                .limit(1)
                .fetchOne(database) else {
                return nil
            }
            return record.toTaskActionItem()
        }
    }

    /// Apply selective re-ranking: pull re-ranked tasks out of the ordered list,
    /// insert them at their new positions, then renumber all tasks 1..N.
    func applySelectiveReranking(_ reranks: [(backendId: String, newPosition: Int)]) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            // 1. Get all active tasks ordered by current relevanceScore ASC (1 = top)
            let rows = try Row.fetchAll(database, sql: """
                SELECT id, backendId, relevanceScore
                FROM action_items
                WHERE completed = 0 AND deleted = 0
                ORDER BY COALESCE(relevanceScore, 999999) ASC
            """)

            // 2. Build ordered list of backendIds (current ranking)
            var orderedIds: [String] = rows.compactMap { $0["backendId"] as? String }
            let rerankedSet = Set(reranks.map { $0.backendId })

            // 3. Remove re-ranked tasks from the list
            orderedIds.removeAll { rerankedSet.contains($0) }

            // 4. Insert re-ranked tasks at their new positions (sorted by position to insert correctly)
            let sorted = reranks.sorted { $0.newPosition < $1.newPosition }
            for rerank in sorted {
                let insertIdx = max(0, min(rerank.newPosition - 1, orderedIds.count))
                orderedIds.insert(rerank.backendId, at: insertIdx)
            }

            // 5. Reassign sequential scores 1..N
            let now = Date()
            for (index, backendId) in orderedIds.enumerated() {
                try database.execute(
                    sql: "UPDATE action_items SET relevanceScore = ?, scoredAt = ?, updatedAt = ? WHERE backendId = ?",
                    arguments: [index + 1, now, now, backendId]
                )
            }
        }
    }

    // MARK: - Agent Session Persistence

    /// Update agent state for an action item (keyed by backendId or local_ prefix)
    func updateAgentState(
        taskId: String,
        status: String?,
        sessionName: String?,
        prompt: String?,
        plan: String?,
        startedAt: Date?,
        completedAt: Date?,
        editedFilesJson: String?
    ) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            // Find by backendId, or by local ID (local_<rowid>)
            var record: ActionItemRecord?
            if taskId.hasPrefix("local_"), let localId = Int64(taskId.dropFirst(6)) {
                record = try ActionItemRecord.fetchOne(database, key: localId)
            } else {
                record = try ActionItemRecord
                    .filter(Column("backendId") == taskId)
                    .fetchOne(database)
            }

            guard var rec = record else {
                log("ActionItemStorage: updateAgentState - record not found for taskId \(taskId)")
                return
            }

            rec.agentStatus = status
            rec.agentSessionName = sessionName
            rec.agentPrompt = prompt
            rec.agentPlan = plan
            rec.agentStartedAt = startedAt
            rec.agentCompletedAt = completedAt
            rec.agentEditedFilesJson = editedFilesJson
            try rec.update(database)
        }
    }

    /// Get action items with active (non-terminal) agent sessions for restore on startup
    func getActiveAgentSessions() async throws -> [ActionItemRecord] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try ActionItemRecord
                .filter(Column("agentStatus") != nil)
                .filter(!(["completed", "failed"].contains(Column("agentStatus"))))
                .fetchAll(database)
        }
    }

    /// Clear all agent fields for a task (when user stops/removes session)
    func clearAgentState(taskId: String) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            var record: ActionItemRecord?
            if taskId.hasPrefix("local_"), let localId = Int64(taskId.dropFirst(6)) {
                record = try ActionItemRecord.fetchOne(database, key: localId)
            } else {
                record = try ActionItemRecord
                    .filter(Column("backendId") == taskId)
                    .fetchOne(database)
            }

            guard var rec = record else { return }

            rec.agentStatus = nil
            rec.agentSessionName = nil
            rec.agentPrompt = nil
            rec.agentPlan = nil
            rec.agentStartedAt = nil
            rec.agentCompletedAt = nil
            rec.agentEditedFilesJson = nil
            try rec.update(database)
        }
    }

    // MARK: - Chat Session

    /// Update chat session ID for a task
    func updateChatSessionId(taskId: String, sessionId: String?) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            var record: ActionItemRecord?
            if taskId.hasPrefix("local_"), let localId = Int64(taskId.dropFirst(6)) {
                record = try ActionItemRecord.fetchOne(database, key: localId)
            } else {
                record = try ActionItemRecord
                    .filter(Column("backendId") == taskId)
                    .fetchOne(database)
            }

            guard var rec = record else {
                log("ActionItemStorage: updateChatSessionId - record not found for taskId \(taskId)")
                return
            }

            rec.chatSessionId = sessionId
            try rec.update(database)
        }
    }

    // MARK: - Recurring Tasks

    /// Get incomplete recurring tasks that are due (dueAt <= now)
    func getDueRecurringTasks() async throws -> [TaskActionItem] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            let records = try ActionItemRecord
                .filter(Column("completed") == false)
                .filter(Column("deleted") == false)
                .filter(Column("recurrenceRule") != nil && Column("recurrenceRule") != "")
                .filter(Column("dueAt") != nil && Column("dueAt") <= Date())
                .fetchAll(database)
            return records.map { $0.toTaskActionItem() }
        }
    }

    // MARK: - Stats

    /// Get action item storage statistics
    func getStats() async throws -> (total: Int, completed: Int, pending: Int, unsynced: Int) {
        let db = try await ensureInitialized()

        return try await db.read { database in
            let total = try ActionItemRecord
                .filter(Column("deleted") == false)
                .fetchCount(database)

            let completed = try ActionItemRecord
                .filter(Column("deleted") == false)
                .filter(Column("completed") == true)
                .fetchCount(database)

            let pending = try ActionItemRecord
                .filter(Column("deleted") == false)
                .filter(Column("completed") == false)
                .fetchCount(database)

            let unsynced = try ActionItemRecord
                .filter(Column("deleted") == false)
                .filter(Column("backendSynced") == false)
                .fetchCount(database)

            return (total, completed, pending, unsynced)
        }
    }
}
