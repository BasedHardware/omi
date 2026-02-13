import Foundation
import GRDB

/// Actor-based storage manager for live notes during recording sessions
/// Provides crash-safe persistence for notes generated during transcription
actor NoteStorage {
    static let shared = NoteStorage()

    private var _dbQueue: DatabaseQueue?
    private var isInitialized = false

    private init() {}

    /// Invalidate cached DB queue (called on user switch / sign-out)
    func invalidateCache() {
        _dbQueue = nil
        isInitialized = false
    }

    /// Ensure database is initialized before use
    private func ensureInitialized() async throws -> DatabaseQueue {
        if let db = _dbQueue {
            return db
        }

        // Initialize RewindDatabase which creates our tables via migrations
        do {
            try await RewindDatabase.shared.initialize()
        } catch {
            log("NoteStorage: Database initialization failed: \(error.localizedDescription)")
            throw error
        }

        guard let db = await RewindDatabase.shared.getDatabaseQueue() else {
            throw LiveNoteError.databaseNotInitialized
        }

        _dbQueue = db
        isInitialized = true
        return db
    }

    // MARK: - Note Operations

    /// Create a new note for a session
    @discardableResult
    func createNote(
        sessionId: Int64,
        text: String,
        timestamp: Date = Date(),
        isAiGenerated: Bool = true,
        segmentStartOrder: Int? = nil,
        segmentEndOrder: Int? = nil
    ) async throws -> LiveNoteRecord {
        let db = try await ensureInitialized()

        let note = LiveNoteRecord(
            sessionId: sessionId,
            text: text,
            timestamp: timestamp,
            isAiGenerated: isAiGenerated,
            segmentStartOrder: segmentStartOrder,
            segmentEndOrder: segmentEndOrder
        )

        let record = try await db.write { database in
            try note.inserted(database)
        }

        log("NoteStorage: Created note \(record.id ?? -1) for session \(sessionId) (AI: \(isAiGenerated))")
        return record
    }

    /// Update an existing note's text
    func updateNote(id: Int64, text: String) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            guard var record = try LiveNoteRecord.fetchOne(database, key: id) else {
                throw LiveNoteError.noteNotFound
            }

            record.text = text
            record.updatedAt = Date()
            try record.update(database)
        }

        log("NoteStorage: Updated note \(id)")
    }

    /// Delete a note
    func deleteNote(id: Int64) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "DELETE FROM live_notes WHERE id = ?",
                arguments: [id]
            )
        }

        log("NoteStorage: Deleted note \(id)")
    }

    /// Get a note by ID
    func getNote(id: Int64) async throws -> LiveNoteRecord? {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try LiveNoteRecord.fetchOne(database, key: id)
        }
    }

    /// Get all notes for a session ordered by timestamp
    func getNotes(sessionId: Int64) async throws -> [LiveNoteRecord] {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try LiveNoteRecord
                .filter(Column("sessionId") == sessionId)
                .order(Column("timestamp").asc)
                .fetchAll(database)
        }
    }

    /// Get note count for a session
    func getNoteCount(sessionId: Int64) async throws -> Int {
        let db = try await ensureInitialized()

        return try await db.read { database in
            try Int.fetchOne(
                database,
                sql: "SELECT COUNT(*) FROM live_notes WHERE sessionId = ?",
                arguments: [sessionId]
            ) ?? 0
        }
    }

    /// Delete all notes for a session
    func deleteNotesForSession(sessionId: Int64) async throws {
        let db = try await ensureInitialized()

        try await db.write { database in
            try database.execute(
                sql: "DELETE FROM live_notes WHERE sessionId = ?",
                arguments: [sessionId]
            )
        }

        log("NoteStorage: Deleted all notes for session \(sessionId)")
    }

    // MARK: - Batch Operations

    /// Get notes as LiveNote structs for UI
    func getLiveNotes(sessionId: Int64) async throws -> [LiveNote] {
        let records = try await getNotes(sessionId: sessionId)
        return records.compactMap { $0.toLiveNote() }
    }
}
