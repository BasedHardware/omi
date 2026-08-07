import Foundation
import GRDB
import OSLog

/// Everything Context for Claude has ever captured, in one SQLite file.
///
/// Two processes reach this database: the app writes, and `context-for-claude-mcp` reads. WAL is what makes
/// that safe — a reader opened with `readOnly: true` sees a consistent snapshot and never blocks
/// the capture pipeline, so a Claude query can never drop a transcript line.
///
/// `@unchecked Sendable` is honest here because the only stored state is GRDB's pool, which
/// serializes its own writer and hands out reader connections per access.
public final class ContextStore: @unchecked Sendable {
    private let pool: DatabasePool

    /// Where this store lives. `StatusInfo` reports it so Claude can tell the user which file to
    /// delete when they want their history gone.
    public let databaseURL: URL

    /// True for the `context-for-claude-mcp` reader. Every mutating helper refuses when this is set.
    public let isReadOnly: Bool

    // MARK: - Retention policy

    /// How old screenshots may get. The first of the two retention bounds.
    public static let defaultRetentionDays = 30

    /// How much screenshot storage may accumulate, regardless of age — the second bound, and the one
    /// that holds on a Mac that is never restarted.
    ///
    /// 4 GiB. Measured capture is ~8.9 MiB per wall-clock hour for an instance left running at login
    /// and ~31.6 MiB per hour while the screen is actually changing, so the cap buys roughly **460
    /// hours (19 days) of always-on coverage**, or ~130 hours of continuously active use. On a
    /// machine that captures hard the cap therefore bites before the 30-day rule does, which is the
    /// intent: the tighter bound is meant to win. On a normal machine the total never approaches it
    /// and age stays the only bound. Either way transcripts are untouched — what a heavy user loses
    /// is the picture of a day three weeks ago, never the words.
    ///
    /// Chosen to stay invisible rather than to maximise history: alongside the ~904 MB of on-device
    /// transcription weights the whole install stays under 5 GB, which is small enough on a 256 GB
    /// Mac that nobody has to be asked about it. That is exactly why this is a constant and not a
    /// setting — an ambient tool that opens a preferences window to argue about disk quotas has
    /// already failed at being ambient.
    public static let defaultFrameBytesCap: Int64 = 4 * 1024 * 1024 * 1024

    /// Ids per `DELETE ... IN (...)`. SQLite caps how many parameters one statement may bind, and a
    /// month of capture is tens of thousands of rows.
    private static let deleteChunkSize = 500

    /// `ContextCore` cannot reach `ContextLog` — it links into `context-for-claude-mcp`, which owns
    /// no app code — so retention logs straight to the unified log under the same subsystem and
    /// category the app uses, and the two interleave in one `log stream`. `os.Logger` never touches
    /// stdout, which in the MCP binary is the JSON-RPC channel and nothing else.
    private static let log = Logger(subsystem: ContextPaths.bundleIdentifier, category: "store")

    /// Opens (creating if needed) the database at `url` and runs migrations.
    /// `readOnly` opens a WAL reader that never blocks the writer — this is what `context-for-claude-mcp` uses.
    ///
    /// A read-only open of a database that does not exist is not an error worth crashing on: the
    /// user simply has not started capturing yet, so it surfaces as `.notInitialized` for the
    /// caller to explain. Creating the file here would leave an empty database behind that the app
    /// would then have to migrate from a foreign process.
    public init(url: URL = ContextPaths.databaseURL, readOnly: Bool = false) throws {
        self.databaseURL = url
        self.isReadOnly = readOnly

        if readOnly {
            guard FileManager.default.fileExists(atPath: url.path) else {
                throw ContextStoreError.notInitialized
            }
            pool = try DatabasePool(path: url.path, configuration: Self.makeConfiguration(readOnly: true))
            // Checked once, here, rather than met as `no such column: speakerLabel` from whichever
            // query happened to run first. A raw SQLite string does not reach a log in this binary
            // — it reaches the model as the *answer* to the user's question, and an answer that
            // reads like a database fault teaches it to stop asking rather than to relaunch the app.
            guard try pool.read({ try Self.isUpgraded($0) }) else {
                throw ContextStoreError.awaitingAppUpgrade
            }
        } else {
            try FileManager.default.createDirectory(
                at: url.deletingLastPathComponent(),
                withIntermediateDirectories: true)
            ContextPaths.setPermissions(url.deletingLastPathComponent(), mode: 0o700)
            pool = try DatabasePool(path: url.path, configuration: Self.makeConfiguration(readOnly: false))
            try Self.makeMigrator().migrate(pool)
            ContextPaths.setPermissions(url, mode: 0o600)
            ContextPaths.setPermissions(URL(fileURLWithPath: url.path + "-wal"), mode: 0o600)
            ContextPaths.setPermissions(URL(fileURLWithPath: url.path + "-shm"), mode: 0o600)
        }
    }

    /// Whether a database exists but is older than this binary's queries.
    ///
    /// Distinct from "no database": one says the app has never run, the other that it has not run
    /// *since the update*. They need different sentences, because only one of them is fixed by
    /// launching the app. A database that cannot be opened at all answers `false` — that is a
    /// different fault, and claiming an upgrade would send the user to the wrong remedy.
    public static func needsAppUpgrade(at url: URL = ContextPaths.databaseURL) -> Bool {
        guard FileManager.default.fileExists(atPath: url.path) else { return false }
        guard let pool = try? DatabasePool(path: url.path, configuration: makeConfiguration(readOnly: true)),
              let upgraded = try? pool.read({ try isUpgraded($0) })
        else { return false }
        return !upgraded
    }

    /// Whether `db` carries every migration this binary's queries assume.
    ///
    /// An **empty** ledger is not an old database — it is an empty or foreign file, and answering
    /// "launch the app to upgrade it" would send the user to a remedy that cannot work. Only a
    /// ledger that is populated *and* short is a database the app is behind on.
    private static func isUpgraded(_ db: Database) throws -> Bool {
        let migrator = makeMigrator()
        if try migrator.appliedIdentifiers(db).isEmpty { return true }
        return try migrator.hasCompletedMigrations(db)
    }

    // MARK: - Access

    /// Runs `body` against a reader connection. Safe from any thread, and safe while the app writes.
    public func read<T>(_ body: (Database) throws -> T) throws -> T {
        try pool.read(body)
    }

    /// Runs `body` inside a write transaction. Throws `ContextStoreError.readOnly` in the MCP reader
    /// rather than letting SQLite fail deep inside a statement with an opaque code.
    public func write<T>(_ body: (Database) throws -> T) throws -> T {
        guard !isReadOnly else { throw ContextStoreError.readOnly }
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

    /// Inserts a cloud segment or atomically replaces its previously stored backend revision.
    ///
    /// Text and timestamps are never identity: two people can say the same thing at once. Only the
    /// backend's conversation/segment pair permits a replacement claim.
    @discardableResult
    public func upsertCloudSegment(_ segment: Segment) throws -> Int64 {
        guard let conversationId = segment.backendConversationId,
              let segmentId = segment.backendSegmentId
        else { throw ContextStoreError.missingCloudSegmentIdentity }

        return try write { db in
            if let existingId = try Int64.fetchOne(
                db,
                sql: "SELECT id FROM segments WHERE backendConversationId = ? AND backendSegmentId = ?",
                arguments: [conversationId, segmentId])
            {
                var revision = segment
                revision.id = existingId
                try revision.update(db)
                return existingId
            }
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

    /// Stores the subtrees of one captured tree, skipping every one already held.
    ///
    /// `INSERT OR IGNORE` rather than a read-then-write: the whole point of a content address is that
    /// a colliding hash means identical contents, so losing the race is the correct outcome and
    /// checking first would only add a round trip. Returns how many rows were genuinely new, which is
    /// the number worth logging — it is the dedup rate, measured rather than assumed.
    @discardableResult
    public func insertAXNodes(_ records: [AXNodeRecord], firstSeenFrameId: Int64?) throws -> Int {
        guard !records.isEmpty else { return 0 }
        return try write { db in
            var inserted = 0
            for record in records {
                try db.execute(
                    sql: """
                    INSERT OR IGNORE INTO ax_nodes (hash, payload, firstSeenFrameId)
                    VALUES (?, ?, ?)
                    """,
                    arguments: [record.hash, record.payload, firstSeenFrameId])
                inserted += db.changesCount
            }
            return inserted
        }
    }

    /// Deletes frames (and their JPEGs) older than `days`. Transcripts are never pruned.
    ///
    /// Screenshots are the only thing here that grows without bound; text costs almost nothing, and
    /// a transcript the user cannot recall a year later is exactly the thing this app exists for.
    /// Returns the number of rows removed.
    @discardableResult
    public func pruneFrames(olderThanDays days: Int) throws -> Int {
        let cutoff = ContextTime.now - Double(days) * 86_400

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

    /// Deletes the oldest frames until the frames directory is at or under `bytes`, whatever their
    /// age. Returns how many rows went.
    ///
    /// The companion bound to `pruneFrames(olderThanDays:)`: that one caps how *old* screenshots may
    /// get, this one caps how *much* of them there may be, and on any given machine the tighter of
    /// the two decides. An age rule alone is unbounded in bytes — a Mac that captures three times the
    /// average simply stores three times as much — and this app is designed to sit at login for
    /// weeks, which is precisely the machine an age rule fails to protect.
    ///
    /// Deletion is strictly oldest-first, so what survives is always the most recent stretch of
    /// screen history rather than an arbitrary subset of it, and it stops the instant the total is
    /// under the cap: a frame that does not have to go does not go. Transcripts are never considered
    /// — they are small, and they are the half that cannot be recaptured.
    @discardableResult
    public func pruneFrames(toFitBytes bytes: Int64) throws -> Int {
        // Refuse up front rather than on the first write. Retention through the MCP reader is a
        // caller bug, and a silent "0 rows" would hide it on every machine that is under the cap.
        guard !isReadOnly else { throw ContextStoreError.readOnly }
        let cap = max(0, bytes)

        let frames = try frameFiles()
        let bytesBefore = frames.reduce(Int64(0)) { $0 + $1.bytes }
        guard bytesBefore > cap else { return 0 }

        var projected = bytesBefore
        var doomed: [FrameFile] = []
        for frame in frames {
            if projected <= cap { break }
            doomed.append(frame)
            projected -= frame.bytes
        }
        guard !doomed.isEmpty else { return 0 }

        let ids = doomed.map(\.id)
        let deleted = try write { db -> Int in
            var count = 0
            // One transaction across every chunk, so the rows and their FTS trigger updates commit
            // together — a partially applied sweep would leave search answering with frames whose
            // screenshots are already gone.
            for start in stride(from: 0, to: ids.count, by: Self.deleteChunkSize) {
                let chunk = Array(ids[start..<min(start + Self.deleteChunkSize, ids.count)])
                try db.execute(
                    sql: "DELETE FROM frames WHERE id IN (\(databaseQuestionMarks(count: chunk.count)))",
                    arguments: StatementArguments(chunk))
                count += db.changesCount
            }
            return count
        }

        // Unlink outside the transaction: thousands of file removals must not hold the single writer
        // connection while capture is running. Only paths read off the rows just deleted are touched,
        // so a screenshot written a millisecond ago — whose row is not in this set — is never at risk.
        let fileManager = FileManager.default
        var freed: Int64 = 0
        for frame in doomed {
            guard let path = frame.path else { continue }
            if (try? fileManager.removeItem(atPath: path)) != nil { freed += frame.bytes }
        }
        Self.removeEmptyDayDirectories()

        // A user who finds a gap in their screen history deserves to see that retention made it, not
        // guess at a fault. Bytes only: never a path, a window title, or a line of OCR.
        let summary = """
            Frame retention: over the \(Self.describe(cap)) cap, removed \(deleted) \
            \(deleted == 1 ? "frame" : "frames"), \
            \(Self.describe(bytesBefore)) → \(Self.describe(bytesBefore - freed)) on disk
            """
        Self.log.info("\(summary, privacy: .public)")

        return deleted
    }

    /// Applies both retention bounds and returns the total rows removed.
    ///
    /// Age first — one indexed delete that cheaply removes most of what has to go — then the byte cap
    /// over whatever survived it.
    @discardableResult
    public func enforceRetention(
        olderThanDays days: Int = ContextStore.defaultRetentionDays,
        toFitBytes bytes: Int64 = ContextStore.defaultFrameBytesCap
    ) throws -> Int {
        let byAge = try pruneFrames(olderThanDays: days)
        let byBytes = try pruneFrames(toFitBytes: bytes)
        return byAge + byBytes
    }

    /// Bytes of screen JPEGs on disk: the files the `frames` table still points at.
    ///
    /// Counted from the rows rather than by walking `Frames/`, because the rows are the only safe
    /// authority. `ScreenWatcher` writes a JPEG before it inserts the row that names it, so a file
    /// with no row may be a screenshot one millisecond old; anything that treated the directory as
    /// truth would eventually delete a frame out from under a live capture. The cost of that choice
    /// is that a JPEG orphaned by a crash between the delete and the unlink goes uncounted, which
    /// understates usage by a few files rather than risking the loss of a real one.
    public func framesBytesOnDisk() throws -> Int64 {
        try frameFiles().reduce(Int64(0)) { $0 + $1.bytes }
    }

    // MARK: - Frame accounting

    private struct FrameFile {
        let id: Int64
        /// Nil when OCR was captured but the JPEG was skipped: a row that costs no disk.
        let path: String?
        let bytes: Int64
    }

    /// Every frame, oldest first, with the size of its JPEG. One `stat` per frame — a few hundred
    /// milliseconds across a month of capture — and all of it outside the write transaction, so the
    /// writer is only held for the deletes themselves.
    private func frameFiles() throws -> [FrameFile] {
        let rows = try read { db in
            try Row.fetchAll(
                db,
                sql: "SELECT id, imagePath FROM frames ORDER BY capturedAt ASC, id ASC")
        }
        return rows.map { row in
            let id: Int64 = row["id"]
            let path: String? = row["imagePath"]
            return FrameFile(id: id, path: path, bytes: path.map { Self.fileBytes(at: $0) } ?? 0)
        }
    }

    /// Zero for anything that cannot be measured. A path that no longer resolves frees nothing when
    /// it is deleted, and counting it would make the sweep stop short of the cap.
    private static func fileBytes(at path: String) -> Int64 {
        guard let attributes = try? FileManager.default.attributesOfItem(atPath: path),
            let size = attributes[.size] as? NSNumber
        else { return 0 }
        return size.int64Value
    }

    /// Binary units, spelled out, down to whole bytes. `ByteCountFormatter` localises and switches to
    /// decimal GB, which makes a log line disagree with the cap it is reporting against — and a sweep
    /// that frees half a megabyte has to say so rather than round itself away to "0.0 MiB".
    private static func describe(_ bytes: Int64) -> String {
        let units: [(threshold: Double, suffix: String, places: Int)] = [
            (1_073_741_824, "GiB", 2), (1_048_576, "MiB", 1), (1_024, "KiB", 1),
        ]
        for unit in units where Double(bytes) >= unit.threshold {
            return String(format: "%.\(unit.places)f %@", Double(bytes) / unit.threshold, unit.suffix)
        }
        return "\(bytes) B"
    }

    // MARK: - Setup

    /// PRAGMAs both processes depend on. WAL and `synchronous` are writer-only settings — issuing
    /// them on a read-only connection fails, and a failed `prepareDatabase` aborts the open.
    static func makeConfiguration(readOnly: Bool) -> Configuration {
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

        // Per-line transcription confidence. The model scores every line it emits and the app used
        // to throw that away, so a line it was barely sure of — background music heard as the
        // user's own speech — was stored, searched and rendered exactly like one it was certain of.
        //
        // `"v3-"` rather than `"v2"`: `UploadQueue.migrationIdentifier` is `"v2-uploads"`, registered
        // outside this migrator and written into the same `grdb_migrations` ledger. GRDB skips any
        // identifier already in that ledger and ignores unregistered ones, so the two never collide
        // — but reusing the number would leave the schema history unreadable.
        //
        // Nullable and with no default, so every row captured before today keeps a NULL: an unknown
        // score has to stay distinguishable from a bad one all the way up to the reader. Nothing is
        // indexed on it — it is never a search key, it just rides along with rows already fetched —
        // and the FTS index covers `text` alone, so a new column leaves the sync triggers untouched.
        migrator.registerMigration("v3-segment-confidence") { db in
            try db.alter(table: "segments") { t in
                t.add(column: "confidence", .double)
            }
        }

        // Backend speaker attribution. Transcription moved to the Omi cloud precisely because the
        // server diarizes the stream and matches voices against the account's enrolled speech
        // profiles — and until this column existed there was nowhere to put either answer, so the
        // whole reason for the move died at this boundary and every line was still "mic is the user,
        // system tap is everyone else". Three people on a call came back as one indistinguishable
        // "them".
        //
        // `"v4-"` continues the numbering `v3-segment-confidence` established around
        // `UploadQueue.migrationIdentifier` (`"v2-uploads"`, registered outside this migrator into
        // the same `grdb_migrations` ledger): distinct names cannot collide, and GRDB only ever acts
        // on the intersection of registered and applied identifiers.
        //
        // Both nullable with no default, for the same reason `confidence` is. A local line, a line
        // no speech profile matched, and every line captured before today legitimately have neither
        // — and an absent attribution has to stay absent all the way to the reader rather than
        // collapsing into a claim about who was speaking. Neither column is indexed: `personId` is
        // read per session through `idx_segments_sessionId`, never searched across the corpus, and
        // the FTS index covers `text` alone, so adding columns beneath it leaves the sync triggers
        // untouched.
        migrator.registerMigration("v4-segment-speaker") { db in
            try db.alter(table: "segments") { t in
                t.add(column: "speakerLabel", .text)
                t.add(column: "personId", .text)
            }
        }

        // A cloud segment can arrive again with revised words or attribution. Keeping its identity
        // in the row makes replacement survive app restarts. SQLite permits multiple NULLs here, so
        // ordinary local transcription remains append-only.
        migrator.registerMigration("v5-cloud-segment-identity") { db in
            try db.alter(table: "segments") { t in
                t.add(column: "backendConversationId", .text)
                t.add(column: "backendSegmentId", .text)
            }
            try db.create(
                index: "idx_segments_backend_identity",
                on: "segments",
                columns: ["backendConversationId", "backendSegmentId"],
                unique: true)
        }

        // The accessibility tree, stored the only way that is affordable: content-addressed.
        //
        // A naive design puts one tree blob on every frame row, and it does not survive contact with
        // real capture — consecutive frames of the same window are almost identical, so nearly every
        // byte would duplicate the byte before it. Addressing each subtree by the hash of its
        // contents makes that repetition free: a window whose status line changed stores that label
        // and its ancestors, and references everything else.
        //
        // `axText` is denormalised onto the frame deliberately. The nodes carry the structure, but
        // search wants one flat string per frame, and reassembling it from the node graph on every
        // query would trade a cheap column for a recursive join. It gets its own FTS table rather
        // than a new column on `frames_fts`, because adding a column there means dropping and
        // rebuilding that whole index — this way the existing one is never touched.
        migrator.registerMigration("v6-accessibility-tree") { db in
            try db.alter(table: "frames") { t in
                t.add(column: "axText", .text)
                t.add(column: "axRootHash", .blob)
            }
            try db.create(table: "ax_nodes") { t in
                t.column("hash", .blob).primaryKey()
                t.column("payload", .blob).notNull()
                // Which frame first paid for this subtree. Diagnostic, not a foreign key: the node
                // outlives that frame by design, and a cascade would delete rows still referenced by
                // every later frame that shares them.
                t.column("firstSeenFrameId", .integer)
            }
            try db.create(virtualTable: "frames_ax_fts", using: FTS5()) { t in
                t.synchronize(withTable: "frames")
                t.tokenizer = .porter(wrapping: .unicode61())
                t.column("axText")
            }
        }

        // The owning application's bundle identifier, which capture already knew and discarded.
        //
        // `ScreenWatcher` reads `frontmostApplication.bundleIdentifier` on every tick and uses it
        // for exclusion decisions, then stores only the *display name*. That is the wrong half to
        // keep for anything that has to find the app again: resolving "Cursor" or "Preview" back to
        // an installed bundle means probing a list of directories for `<name>.app` and guessing at
        // bundle ids from the name, which is a heuristic that silently fails on renamed apps
        // (`System Preferences` → `System Settings`), on anything not in a standard directory, and
        // on every command-line tool that owns a window. The identifier is the actual key —
        // `NSWorkspace.urlForApplication(withBundleIdentifier:)` answers it exactly or not at all.
        //
        // Nullable with no default, like `confidence` and the speaker columns before it: every row
        // captured before today legitimately has no recorded identifier, and NULL has to keep
        // meaning "not recorded" rather than collapsing into a claim about which app it was.
        // `RewindQueries.bundleIdsByApp` is what makes that cheap — one new sighting of an app
        // teaches its whole back catalogue — so the historical NULLs need no backfill and get none.
        //
        // Additive and unindexed, and therefore safe for the two external-content FTS tables built
        // over `frames`: `frames_fts` covers (ocrText, windowTitle, appName) and `frames_ax_fts`
        // covers axText, and neither is touched by a column appearing beneath them. Adding a column
        // *to* an FTS table would mean dropping and rebuilding that index; adding one to the content
        // table does not, which is the same reasoning `v6-accessibility-tree` recorded. Existing
        // rows stay valid and readable throughout.
        migrator.registerMigration("v7-frame-bundle-id") { db in
            try db.alter(table: "frames") { t in
                t.add(column: "bundleId", .text)
            }
        }

        return migrator
    }

    /// Sweeps day directories left behind by a prune. Only removes a directory that is genuinely
    /// empty, so a stray file never takes surviving screenshots down with it.
    private static func removeEmptyDayDirectories() {
        let fileManager = FileManager.default
        let root = ContextPaths.framesDirectory
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

public enum ContextStoreError: Error {
    /// A write was attempted on the `context-for-claude-mcp` reader.
    case readOnly
    /// The database file does not exist yet — the app has never captured anything.
    case notInitialized
    /// The database predates this binary. The app owns migrations, so a reader that was updated
    /// while the app has not yet relaunched meets a schema older than its own queries.
    case awaitingAppUpgrade
    /// A cloud segment cannot be safely replaced without both backend identity components.
    case missingCloudSegmentIdentity
}
