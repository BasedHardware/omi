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

    /// Where *this* store's screenshots live: beside its own database, never at a globally derived
    /// path.
    ///
    /// The same reasoning as `ContextPaths.queryStampURL(besideDatabaseAt:)`. Retention deletes
    /// files that the rows in this database name, so the directory it sweeps has to be the one those
    /// rows were written into — a sweep that reads the installed app's directory while holding some
    /// other database is pointed at files it has no rows for, which is the one thing a delete may
    /// never be. In the app the two are the same location; in a test, or in any second store, they
    /// are not.
    public let framesRoot: URL

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

    /// How long something unreferenced is left alone before it is treated as garbage.
    ///
    /// Both sweeps below delete only what is **unreferenced *and* stale**, and this is the stale
    /// half. It exists because capture writes the thing before the row that names it — the image
    /// before the `frames` insert, the accessibility subtrees before the frame that points at them
    /// — so at every instant there is a window in which a perfectly live file or node has nothing
    /// pointing at it yet. That window is milliseconds wide: both writes are handed to one serial
    /// queue back to back, and the holding pen that can delay them is drained before a store exists
    /// for retention to be called on at all. An hour of headroom costs an hour of deferred
    /// reclamation and buys the one error neither sweep may ever make.
    public static let unreferencedGraceSeconds: Double = 3_600

    /// Ids per `DELETE ... IN (...)`. SQLite caps how many parameters one statement may bind, and a
    /// month of capture is tens of thousands of rows.
    private static let deleteChunkSize = 500

    /// Rows per batch while scanning `ax_nodes` for garbage, so the scan's memory is bounded by the
    /// batch rather than by the size of the table.
    private static let axNodeScanBatch = 5_000

    /// Nodes one sweep may delete. The sweep runs hourly beside live capture, so a machine carrying
    /// a large backlog — every install that predates the sweep carries one — reclaims it over a few
    /// passes instead of holding the single writer through one enormous transaction.
    public static let axNodeSweepLimit = 50_000

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
        self.framesRoot = url.deletingLastPathComponent()
            .appendingPathComponent("Frames", isDirectory: true)

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
    ///
    /// `seenAt` is what makes these rows collectable. See ``sweepAXNodes(graceSeconds:limit:now:)``.
    @discardableResult
    public func insertAXNodes(
        _ records: [AXNodeRecord],
        firstSeenFrameId: Int64?,
        seenAt: Double = ContextTime.now
    ) throws -> Int {
        guard !records.isEmpty else { return 0 }
        return try write { db in
            var inserted = 0
            for record in records {
                try db.execute(
                    sql: """
                    INSERT OR IGNORE INTO ax_nodes (hash, payload, firstSeenFrameId, lastSeenAt)
                    VALUES (?, ?, ?, ?)
                    """,
                    arguments: [record.hash, record.payload, firstSeenFrameId, seenAt])
                if db.changesCount > 0 {
                    inserted += 1
                    continue
                }
                // The dedup path — and the one the sweep leans on. A subtree that recurs is *in use
                // again*, and the row already holding it is the row the frame now being captured
                // will reference. Nothing re-inserts it, so without this touch a node whose every
                // frame has aged out could be collected in the gap between the tree that revived it
                // and the frame row that names it. The `lastSeenAt <` clause keeps a re-seen node
                // from dirtying a page for a timestamp it already carries.
                try db.execute(
                    sql: "UPDATE ax_nodes SET lastSeenAt = ? WHERE hash = ? AND lastSeenAt < ?",
                    arguments: [seenAt, record.hash, seenAt])
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
        removeEmptyDayDirectories()

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
        removeEmptyDayDirectories()

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

    // MARK: - Sweeps
    //
    // Retention deletes rows; these two collect what a row delete leaves behind. Both obey one rule
    // — **delete only what is unreferenced *and* stale** — because capture writes every artefact
    // before the row that names it, so "nothing points at this" is momentarily true of live data.
    // See ``unreferencedGraceSeconds``.

    /// Deletes screen images on disk that no `frames` row names. Returns how many files went.
    ///
    /// Both prune paths commit their row deletes and then unlink the files, which is deliberate — a
    /// thousand `unlink` calls must not hold the single writer while capture is running — and it
    /// means a crash, a full disk or a revoked permission in between leaves an image nothing can
    /// ever name again. Nothing reclaimed those, and ``framesBytesOnDisk()`` counts rows, so they
    /// were invisible to the byte cap as well: pure loss, growing with every interrupted sweep.
    ///
    /// **The inverse error is the dangerous one, so the file has to be stale on its own clock.**
    /// `ScreenWatcher` writes the image and only then hands the frame over to be inserted, so a file
    /// written moments ago legitimately has no row yet — and a directory listing that treated it as
    /// unreferenced would delete a screenshot out from under live capture. Three things stop that:
    ///
    /// - **The listing is taken before the rows.** A file that appears after the listing is not a
    ///   candidate at all, and one that appears before it has until the row read to be claimed.
    /// - **Modification time is capture time.** These files are written once, atomically, and never
    ///   touched again, so `mtime` dates the image itself rather than the sweep's view of it — which
    ///   makes the grace window a real bound on the write-then-insert gap and not an approximation
    ///   of one. It also means an image orphaned by an interrupted prune, whose `mtime` is as old as
    ///   the frame it belonged to, is reclaimed by the very next sweep rather than waiting out a
    ///   grace period it already served.
    /// - **Only the shapes capture writes.** Anything that is not a `.heic`, `.jpg` or `.jpeg` under
    ///   this store's own frames root is left exactly where it is — including the partial file
    ///   `Data.write(_:.atomic)` stages beside its destination, and any image a row names somewhere
    ///   else entirely, which never appears in the listing at all.
    @discardableResult
    public func sweepOrphanedFrameImages(
        graceSeconds: Double = ContextStore.unreferencedGraceSeconds,
        now: Double = ContextTime.now
    ) throws -> Int {
        guard !isReadOnly else { throw ContextStoreError.readOnly }

        // Order matters: see the doc comment. The listing is the older half of the two reads.
        let files = imageFilesOnDisk()
        guard !files.isEmpty else { return 0 }
        let referenced = try referencedImagePaths()

        let cutoff = now - graceSeconds
        let doomed = files.filter { file in
            file.modifiedAt < cutoff && !referenced.contains(file.url.path)
                && !referenced.contains(file.url.resolvingSymlinksInPath().path)
        }
        guard !doomed.isEmpty else { return 0 }

        let fileManager = FileManager.default
        var removed = 0
        var freed: Int64 = 0
        for file in doomed {
            guard (try? fileManager.removeItem(at: file.url)) != nil else { continue }
            removed += 1
            freed += file.bytes
        }
        removeEmptyDayDirectories()

        if removed > 0 {
            // Counts and bytes only: never a path, which is a window title and a date.
            Self.log.info(
                """
                Frame retention: reclaimed \(removed, privacy: .public) orphaned \
                \(removed == 1 ? "image" : "images"), \(Self.describe(freed), privacy: .public)
                """)
        }
        return removed
    }

    /// Deletes accessibility subtrees that no stored frame's tree can reach. Returns rows removed.
    ///
    /// `ax_nodes` is a **cache subordinate to `frames`**, and this is the sentence that makes that
    /// true rather than aspirational: a node lives exactly as long as some frame still needs it. It
    /// had no such bound before — nothing ever deleted from the table — so it grew forever while the
    /// frames whose trees it held were pruned at thirty days, measured at ~370 MB a year on this
    /// machine's capture shape.
    ///
    /// **Reachability, not a join.** A node's children are encoded inside its own opaque payload
    /// (``AccessibilityTree/childHashes(inPayload:)``), so there is no edge table and no `DELETE …
    /// WHERE NOT IN (SELECT …)` that could express this. The mark walks out from every
    /// `frames.axRootHash` and the sweep takes what the walk never reached. A subtree shared by a
    /// hundred frames is reached through any one of them, which is the whole point of storing it
    /// once.
    ///
    /// **Two independent reasons a node survives**, because the mark is a snapshot and capture is
    /// still running underneath it:
    ///
    /// - it is reachable from a frame that existed when the mark ran; or
    /// - the store was offered it inside the grace window — which every node of a tree being
    ///   captured right now was, including one that already existed and was therefore silently
    ///   *re-used* rather than re-inserted. That second case is the subtle one: a subtree whose last
    ///   frame aged out weeks ago can recur at any moment, and the recurrence writes no new row.
    ///
    /// The staleness test is re-evaluated **inside the delete itself**, not merely when the
    /// candidates were chosen. That is what closes the window: a node re-seen after the scan but
    /// before the delete no longer matches the statement, so it survives; a node re-seen after the
    /// delete finds its row gone and re-inserts it. Both writes are transactions on the one writer
    /// this database has, so there is no third ordering.
    ///
    /// Interruption is safe by construction: deleting garbage is idempotent, and whatever a crash
    /// leaves behind is simply collected by the next pass.
    @discardableResult
    public func sweepAXNodes(
        graceSeconds: Double = ContextStore.unreferencedGraceSeconds,
        limit: Int = ContextStore.axNodeSweepLimit,
        now: Double = ContextTime.now
    ) throws -> Int {
        guard !isReadOnly else { throw ContextStoreError.readOnly }
        let cutoff = now - graceSeconds

        // The mark runs on a reader connection: it visits every live tree, and holding the writer
        // for that would stall capture for as long as it takes.
        let reachable = try reachableAXNodeHashes()
        let doomed = try collectableAXNodeHashes(reachable: reachable, cutoff: cutoff, limit: limit)
        guard !doomed.isEmpty else { return 0 }

        let removed = try deleteAXNodes(doomed, stalerThan: cutoff)

        if removed > 0 {
            Self.log.info(
                """
                Accessibility retention: removed \(removed, privacy: .public) unreachable \
                \(removed == 1 ? "subtree" : "subtrees"), \
                \(reachable.count, privacy: .public) still in use
                """)
        }
        return removed
    }

    /// Deletes the named nodes, **re-testing staleness inside the statement**. Returns rows removed.
    ///
    /// The predicate is repeated here rather than trusted from the scan because that is the whole
    /// defence against the one interleaving that could orphan a live tree: a subtree re-used by a
    /// capture between the scan and this delete has had its `lastSeenAt` moved forward by
    /// ``insertAXNodes(_:firstSeenFrameId:seenAt:)``, and a row that no longer matches is a row this
    /// statement does not touch. Both are transactions on the single writer, so the two orderings
    /// are the only ones: refresh first and the node survives, delete first and the refresh's
    /// `INSERT OR IGNORE` puts it back.
    func deleteAXNodes(_ hashes: [Data], stalerThan cutoff: Double) throws -> Int {
        guard !hashes.isEmpty else { return 0 }
        return try write { db -> Int in
            var count = 0
            for start in stride(from: 0, to: hashes.count, by: Self.deleteChunkSize) {
                let chunk = Array(hashes[start..<min(start + Self.deleteChunkSize, hashes.count)])
                var arguments: [DatabaseValueConvertible] = [cutoff]
                arguments.append(contentsOf: chunk)
                try db.execute(
                    sql: """
                    DELETE FROM ax_nodes
                    WHERE lastSeenAt < ? AND hash IN (\(databaseQuestionMarks(count: chunk.count)))
                    """,
                    arguments: StatementArguments(arguments))
                count += db.changesCount
            }
            return count
        }
    }

    /// Every node address some stored frame's tree still needs, found by walking out from the roots.
    ///
    /// Internal rather than private, with ``collectableAXNodeHashes(reachable:cutoff:limit:)`` and
    /// ``deleteAXNodes(_:stalerThan:)``, because the ordering *between* the three is the property
    /// under test: the sweep is a read followed by a write, and the only interleaving that can lose
    /// data happens between them. A test that could only call the whole sweep could never place a
    /// capture in that gap.
    func reachableAXNodeHashes() throws -> Set<Data> {
        try read { db in
            var reachable = Set<Data>()
            var frontier = try Data.fetchAll(
                db,
                sql: "SELECT DISTINCT axRootHash FROM frames WHERE axRootHash IS NOT NULL")
            while let hash = frontier.popLast() {
                // A shared subtree is reached once. Without this the walk is exponential in the
                // sharing that made the table affordable in the first place.
                guard reachable.insert(hash).inserted else { continue }
                let statement = try db.cachedStatement(
                    sql: "SELECT payload FROM ax_nodes WHERE hash = ?")
                // A root whose rows never landed — an interrupted write, or a database restored
                // without them — simply has no children to follow. It is not an error and it is not
                // this sweep's business to repair.
                guard let payload = try Data.fetchOne(statement, arguments: [hash]) else { continue }
                frontier.append(contentsOf: AccessibilityTree.childHashes(inPayload: payload))
            }
            return reachable
        }
    }

    /// Up to `limit` node addresses that are both unreachable and stale, scanned in `rowid` order so
    /// the scan's memory is the batch rather than the table.
    func collectableAXNodeHashes(
        reachable: Set<Data>, cutoff: Double, limit: Int
    ) throws -> [Data] {
        try read { db in
            var doomed: [Data] = []
            var cursor: Int64 = 0
            while doomed.count < limit {
                let rows = try Row.fetchAll(
                    db,
                    sql: """
                    SELECT rowid AS rid, hash FROM ax_nodes
                    WHERE rid > ? AND lastSeenAt < ?
                    ORDER BY rid LIMIT ?
                    """,
                    arguments: [cursor, cutoff, Self.axNodeScanBatch])
                guard !rows.isEmpty else { break }
                for row in rows {
                    cursor = row["rid"]
                    let hash: Data = row["hash"]
                    if !reachable.contains(hash) { doomed.append(hash) }
                }
                if rows.count < Self.axNodeScanBatch { break }
            }
            return Array(doomed.prefix(limit))
        }
    }

    /// Applies both retention bounds and returns the total **frame rows** removed.
    ///
    /// Age first — one indexed delete that cheaply removes most of what has to go — then the byte cap
    /// over whatever survived it, and then the two sweeps that collect what those deletes orphaned.
    /// The sweeps are inside this call rather than on a schedule of their own because they exist to
    /// finish this job: an image whose row went and a subtree whose last frame went are both created
    /// by the lines above, and neither has any other owner.
    ///
    /// The count is frames, and only frames, so the caller's "removed *n* frames" stays true —
    /// reclaimed files and collected subtrees are the same frames counted again, and each sweep
    /// reports its own totals to the log.
    @discardableResult
    public func enforceRetention(
        olderThanDays days: Int = ContextStore.defaultRetentionDays,
        toFitBytes bytes: Int64 = ContextStore.defaultFrameBytesCap
    ) throws -> Int {
        let byAge = try pruneFrames(olderThanDays: days)
        let byBytes = try pruneFrames(toFitBytes: bytes)
        try sweepOrphanedFrameImages()
        try sweepAXNodes()
        return byAge + byBytes
    }

    /// Bytes of screen JPEGs on disk: the files the `frames` table still points at.
    ///
    /// Counted from the rows rather than by walking `Frames/`, because the rows are the only safe
    /// authority. `ScreenWatcher` writes a JPEG before it inserts the row that names it, so a file
    /// with no row may be a screenshot one millisecond old; anything that treated the directory as
    /// truth would eventually delete a frame out from under a live capture. An image orphaned by a
    /// crash between the delete and the unlink is therefore uncounted here — and is reclaimed by
    /// ``sweepOrphanedFrameImages(graceSeconds:now:)`` rather than left to make this number a lie
    /// forever.
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

    /// One image on disk, as the orphan sweep has to see it: where it is, how big, and when it was
    /// written.
    private struct ImageFile {
        let url: URL
        let bytes: Int64
        /// Capture time. These files are written once and never modified, so `mtime` dates the
        /// screenshot rather than anything that has since looked at it.
        let modifiedAt: Double
    }

    /// The extensions capture has ever written. Anything else in `Frames/` was not put there by this
    /// app and is not this sweep's to remove.
    private static let imageExtensions: Set<String> = ["heic", "jpg", "jpeg"]

    /// Every image under `Frames/`, day directories included. Failures are absences: an unreadable
    /// directory yields nothing to delete, which is the safe direction.
    private func imageFilesOnDisk() -> [ImageFile] {
        let fileManager = FileManager.default
        let keys: [URLResourceKey] = [.isRegularFileKey, .fileSizeKey, .contentModificationDateKey]
        guard let walker = fileManager.enumerator(
            at: framesRoot,
            includingPropertiesForKeys: keys,
            options: [.skipsHiddenFiles, .skipsPackageDescendants])
        else { return [] }

        var files: [ImageFile] = []
        for case let url as URL in walker {
            guard Self.imageExtensions.contains(url.pathExtension.lowercased()),
                let values = try? url.resourceValues(forKeys: Set(keys)),
                values.isRegularFile == true,
                let modified = values.contentModificationDate
            else { continue }
            files.append(
                ImageFile(
                    url: url,
                    bytes: Int64(values.fileSize ?? 0),
                    modifiedAt: modified.timeIntervalSince1970))
        }
        return files
    }

    /// Every path the `frames` table currently names, in both the form it was stored in and the form
    /// a directory walk produces. A superset is the safe shape here: an extra entry keeps a file, a
    /// missing one deletes it.
    private func referencedImagePaths() throws -> Set<String> {
        let paths = try read { db in
            try String.fetchAll(
                db, sql: "SELECT imagePath FROM frames WHERE imagePath IS NOT NULL")
        }
        var referenced = Set<String>(minimumCapacity: paths.count * 2)
        for path in paths {
            referenced.insert(path)
            referenced.insert(URL(fileURLWithPath: path).resolvingSymlinksInPath().path)
        }
        return referenced
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

        // The index behind every read that asks about *showable* frames.
        //
        // `idx_frames_capturedAt` covers time and nothing else, so every query that also says
        // `imagePath IS NOT NULL` had to check that column on the row — which, for a question about
        // the whole corpus rather than a range of it, means visiting every row in the table.
        // Measured against a synthetic year of capture (547,500 frames, 2.5 GiB, the shape the
        // default `.off` storage strategy actually produces):
        //
        // - `RewindQueries.coverage` planned `SCAN frames` and took 581 ms — on the main actor,
        //   every time the timeline window opens.
        // - The search panel's `total` for an empty or unindexable query planned `SCAN f` at 575 ms
        //   — once per keystroke that produces no FTS expression.
        //
        // A *partial* index rather than a two-column one: the predicate is always the same
        // `IS NOT NULL`, so the condition belongs in the index instead of in a second column that
        // every entry would repeat. It also costs nothing for the ~8.7% of rows that have no image —
        // they are simply not in it. Both reads now plan against this index (34.7 ms and 12.0 ms),
        // and `coverage` drops to a pair of O(1) seeks once it stops asking for MIN and MAX in one
        // statement, which is why that query was split alongside this migration.
        //
        // Every other showable read — `frames`, `frameCount`, `nearestCapture`, `newestFrames` —
        // already had `idx_frames_capturedAt` for its range and now gets a smaller index serving the
        // same order, so none of them regress.
        migrator.registerMigration("v8-frame-showable-index") { db in
            try db.create(
                index: "idx_frames_showable",
                on: "frames",
                columns: ["capturedAt"],
                condition: Column("imagePath") != nil)
        }

        // The index behind `RewindQueries.bundleIdsByApp`, which is how every app icon on the
        // timeline resolves.
        //
        // That query asks for the newest sighting of a bundle id per app name. `idx_frames_app` is
        // `(appName, capturedAt)` and carries no `bundleId`, so SQLite had to read the *row* behind
        // every index entry to test the predicate: `SCAN frames USING INDEX idx_frames_app` plus
        // half a million row lookups, measured at 779 ms across the synthetic year — and it runs on
        // the main actor in `RewindModel.loadInitial`, so that is the window sitting still.
        //
        // `(appName, id)` restricted to rows that actually recorded an identifier answers the whole
        // question out of the index: the group key, the `MAX(id)` within each group, and the
        // `IS NOT NULL` test are all in it, and the rows that predate `v7-frame-bundle-id` — every
        // one of which is permanently NULL and can never be the answer — are not in it at all. Same
        // plan shape, no row lookups: 148 ms.
        migrator.registerMigration("v9-frame-bundle-by-app-index") { db in
            try db.create(
                index: "idx_frames_bundle_by_app",
                on: "frames",
                columns: ["appName", "id"],
                condition: Column("bundleId") != nil)
        }

        // When each accessibility subtree was last offered to the store, which is what makes the
        // table collectable.
        //
        // `ax_nodes` had no bound at all: nothing in this package ever deleted from it, so a table
        // holding the trees *of frames* outlived every frame it described and grew for the life of
        // the install — ~370 MB a year at this machine's measured shape (3.40 nodes per frame, 104 B
        // of payload plus 46 B of index). Reachability from `frames.axRootHash` is what bounds it,
        // but reachability alone is not safe to act on: capture stores a tree's rows *before* the
        // frame that references them, and a subtree that already exists is re-used silently rather
        // than re-inserted, so there are instants in which a live node is reachable from nothing.
        // This column is the second, independent reason to keep a row, and
        // ``sweepAXNodes(graceSeconds:limit:now:)`` requires both.
        //
        // `NOT NULL DEFAULT 0` rather than nullable: every row captured before today was last seen
        // at some unrecorded moment in the past, and 0 says exactly that while keeping the sweep's
        // predicate a plain comparison. A nullable column would make `lastSeenAt < ?` skip the whole
        // existing backlog — which is the one population this migration exists to make collectable.
        // Unindexed, because the sweep scans the table in `rowid` order by design and an index over
        // a value rewritten on every capture would cost more than the scan it saves.
        migrator.registerMigration("v10-ax-node-last-seen") { db in
            try db.alter(table: "ax_nodes") { t in
                t.add(column: "lastSeenAt", .double).notNull().defaults(to: 0)
            }
        }

        return migrator
    }

    /// Sweeps day directories left behind by a prune. Only removes a directory that is genuinely
    /// empty, so a stray file never takes surviving screenshots down with it.
    private func removeEmptyDayDirectories() {
        let fileManager = FileManager.default
        let root = framesRoot
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
