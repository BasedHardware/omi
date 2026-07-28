import Foundation
import GRDB

/// Everything Earshot has ever captured, in one SQLite file.
///
/// Two processes reach this database: the app writes, and `earshot-mcp` reads. WAL is what makes
/// that safe — a reader opened with `readOnly: true` sees a consistent snapshot and never blocks
/// the capture pipeline, so a Claude query can never drop a transcript line.
///
/// `@unchecked Sendable` is honest here because the only stored state is GRDB's pool, which
/// serializes its own writer and hands out reader connections per access.
public final class EarshotStore: @unchecked Sendable {
    private let pool: DatabasePool

    /// Where this store lives. `StatusInfo` reports it so Claude can tell the user which file to
    /// delete when they want their history gone.
    public let databaseURL: URL

    /// True for the `earshot-mcp` reader. Every mutating helper refuses when this is set.
    public let isReadOnly: Bool

    /// Opens (creating if needed) the database at `url` and runs migrations.
    /// `readOnly` opens a WAL reader that never blocks the writer — this is what `earshot-mcp` uses.
    ///
    /// A read-only open of a database that does not exist is not an error worth crashing on: the
    /// user simply has not started capturing yet, so it surfaces as `.notInitialized` for the
    /// caller to explain. Creating the file here would leave an empty database behind that the app
    /// would then have to migrate from a foreign process.
    public init(url: URL = EarshotPaths.databaseURL, readOnly: Bool = false) throws {
        self.databaseURL = url
        self.isReadOnly = readOnly

        if readOnly {
            guard FileManager.default.fileExists(atPath: url.path) else {
                throw EarshotStoreError.notInitialized
            }
            pool = try DatabasePool(path: url.path, configuration: Self.makeConfiguration(readOnly: true))
        } else {
            try FileManager.default.createDirectory(
                at: url.deletingLastPathComponent(),
                withIntermediateDirectories: true)
            pool = try DatabasePool(path: url.path, configuration: Self.makeConfiguration(readOnly: false))
            try Self.makeMigrator().migrate(pool)
        }
    }

    // MARK: - Access

    /// Runs `body` against a reader connection. Safe from any thread, and safe while the app writes.
    public func read<T>(_ body: (Database) throws -> T) throws -> T {
        try pool.read(body)
    }

    /// Runs `body` inside a write transaction. Throws `EarshotStoreError.readOnly` in the MCP reader
    /// rather than letting SQLite fail deep inside a statement with an opaque code.
    public func write<T>(_ body: (Database) throws -> T) throws -> T {
        guard !isReadOnly else { throw EarshotStoreError.readOnly }
        return try pool.write(body)
    }

    // MARK: - Writes

    /// Starts a session and returns its id. `appHint` is the frontmost app, captured at the moment
    /// speech begins — that is what later makes a session recognisable as "the Zoom call".
    @discardableResult
    public func openSession(at startedAt: Double, appHint: String?) throws -> Int64 {
        try write { db in
            var session = Session(startedAt: startedAt, appHint: appHint)
            try session.insert(db)
            return session.id ?? db.lastInsertedRowID
        }
    }

    /// Stamps the end of a session. Idempotent: closing an unknown or already-closed id is a no-op,
    /// because the engine may close a session it never managed to open (a source died mid-write).
    public func closeSession(_ id: Int64, at endedAt: Double) throws {
        try write { db in
            try db.execute(
                sql: "UPDATE sessions SET endedAt = ? WHERE id = ?",
                arguments: [endedAt, id])
        }
    }

    /// Stores one transcript line and returns its id. The FTS index updates via trigger.
    @discardableResult
    public func insertSegment(_ segment: Segment) throws -> Int64 {
        try write { db in
            var record = segment
            try record.insert(db)
            return record.id ?? db.lastInsertedRowID
        }
    }

    /// Stores one screen observation and returns its id. The FTS index updates via trigger.
    @discardableResult
    public func insertFrame(_ frame: Frame) throws -> Int64 {
        try write { db in
            var record = frame
            try record.insert(db)
            return record.id ?? db.lastInsertedRowID
        }
    }

    /// Deletes frames (and their JPEGs) older than `days`. Transcripts are never pruned.
    ///
    /// Screenshots are the only thing here that grows without bound; text costs almost nothing, and
    /// a transcript the user cannot recall a year later is exactly the thing this app exists for.
    /// Returns the number of rows removed.
    @discardableResult
    public func pruneFrames(olderThanDays days: Int) throws -> Int {
        let cutoff = EarshotTime.now - Double(days) * 86_400

        let (deleted, imagePaths) = try write { db -> (Int, [String]) in
            // Collect paths before the delete; afterwards the rows are gone and the JPEGs would leak.
            let paths = try String.fetchAll(
                db,
                sql: "SELECT imagePath FROM frames WHERE capturedAt < ? AND imagePath IS NOT NULL",
                arguments: [cutoff])
            try db.execute(sql: "DELETE FROM frames WHERE capturedAt < ?", arguments: [cutoff])
            return (db.changesCount, paths)
        }

        // Unlink outside the transaction: thousands of file removals must not hold the single writer
        // connection while capture is running.
        let fileManager = FileManager.default
        for path in imagePaths {
            try? fileManager.removeItem(atPath: path)
        }
        Self.removeEmptyDayDirectories()

        return deleted
    }

    // MARK: - Setup

    /// PRAGMAs both processes depend on. WAL and `synchronous` are writer-only settings — issuing
    /// them on a read-only connection fails, and a failed `prepareDatabase` aborts the open.
    private static func makeConfiguration(readOnly: Bool) -> Configuration {
        var config = Configuration()
        config.readonly = readOnly
        config.prepareDatabase { db in
            if !readOnly {
                try db.execute(sql: "PRAGMA journal_mode = WAL")
                try db.execute(sql: "PRAGMA synchronous = NORMAL")
            }
            try db.execute(sql: "PRAGMA foreign_keys = ON")
            try db.execute(sql: "PRAGMA busy_timeout = 5000")
        }
        return config
    }

    /// The schema. Built fresh per call rather than held in a static so nothing non-Sendable becomes
    /// shared global state.
    private static func makeMigrator() -> DatabaseMigrator {
        var migrator = DatabaseMigrator()

        migrator.registerMigration("v1") { db in
            try db.create(table: "sessions") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("startedAt", .double).notNull()
                t.column("endedAt", .double)
                t.column("appHint", .text)
            }
            try db.create(index: "idx_sessions_startedAt", on: "sessions", columns: ["startedAt"])

            try db.create(table: "segments") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("sessionId", .integer).notNull()
                    .references("sessions", onDelete: .cascade)
                t.column("startedAt", .double).notNull()
                t.column("endedAt", .double).notNull()
                t.column("source", .text).notNull()
                t.column("speaker", .text).notNull()
                t.column("text", .text).notNull()
            }
            try db.create(index: "idx_segments_startedAt", on: "segments", columns: ["startedAt"])
            // Composite so a transcript fetch is one ordered index scan, not a sort.
            try db.create(index: "idx_segments_sessionId", on: "segments", columns: ["sessionId", "startedAt"])

            try db.create(table: "frames") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("capturedAt", .double).notNull()
                t.column("appName", .text)
                t.column("windowTitle", .text)
                t.column("ocrText", .text)
                t.column("imagePath", .text)
            }
            try db.create(index: "idx_frames_capturedAt", on: "frames", columns: ["capturedAt"])
            try db.create(index: "idx_frames_app", on: "frames", columns: ["appName", "capturedAt"])

            // External-content FTS: the base tables stay the single source of truth and the index
            // holds no duplicate copy of the text. `synchronize(withTable:)` emits the three
            // standard `ai`/`ad`/`au` triggers and back-fills the index.
            // Porter stemming so "decided" finds "decide" — people recall the gist, not the wording.
            try db.create(virtualTable: "segments_fts", using: FTS5()) { t in
                t.synchronize(withTable: "segments")
                t.tokenizer = .porter(wrapping: .unicode61())
                t.column("text")
            }

            try db.create(virtualTable: "frames_fts", using: FTS5()) { t in
                t.synchronize(withTable: "frames")
                t.tokenizer = .porter(wrapping: .unicode61())
                t.column("ocrText")
                t.column("windowTitle")
                t.column("appName")
            }
        }

        return migrator
    }

    /// Sweeps day directories left behind by a prune. Only removes a directory that is genuinely
    /// empty, so a stray file never takes surviving screenshots down with it.
    private static func removeEmptyDayDirectories() {
        let fileManager = FileManager.default
        let root = EarshotPaths.framesDirectory
        guard let days = try? fileManager.contentsOfDirectory(
            at: root,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        ) else { return }

        for day in days {
            let isDirectory = (try? day.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) ?? false
            guard isDirectory else { continue }
            let contents = (try? fileManager.contentsOfDirectory(atPath: day.path)) ?? []
            if contents.isEmpty {
                try? fileManager.removeItem(at: day)
            }
        }
    }
}

public enum EarshotStoreError: Error {
    /// A write was attempted on the `earshot-mcp` reader.
    case readOnly
    /// The database file does not exist yet — the app has never captured anything.
    case notInitialized
}
