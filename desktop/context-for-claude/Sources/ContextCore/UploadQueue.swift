import Foundation
import GRDB

/// Which finished local sessions have reached the user's Omi account, and which are still waiting.
///
/// This lives in `ContextCore` rather than in the app because the state belongs beside the sessions
/// it describes: same file, same transaction domain, so a queue row can never outlive, or disagree
/// with, the session it points at. Nothing here touches the network — `ConversationUploader` owns
/// that, and this owns the durable record of what it did.
///
/// The queue is what makes the upload path survive the two things that actually happen to a laptop:
/// it gets closed mid-upload, and it is used for a week before anyone signs in. Both are the same
/// problem — the intent to upload has to outlive the process — and both are answered by writing the
/// intent to disk before the first request rather than holding it in memory.
public enum UploadQueue {

    // MARK: - Types

    public enum State: String, Sendable, CaseIterable {
        /// Queued and waiting for its turn.
        case pending
        /// Every part reached the backend. Terminal.
        case uploaded
        /// The last attempt failed and will be retried after `nextAttemptAt`. Still queued.
        case failed
        /// Nothing uploadable in it, or the server rejected the content itself. Terminal — retrying
        /// identical content would fail identically and spend the hourly budget doing it.
        case skipped
    }

    public struct Entry: Sendable, Equatable {
        public let sessionId: Int64
        public let state: State
        /// Consecutive failures since the last progress. Drives the backoff.
        public let attempts: Int
        /// How many 500-segment parts of this session the backend has already accepted.
        public let partsDone: Int
        public let queuedAt: Double
        public let updatedAt: Double
        /// Epoch before which this entry must not be attempted again.
        public let nextAttemptAt: Double
        /// Omi conversation ids created so far, oldest part first.
        public let conversationIds: [String]
        public let lastError: String?

        public init(
            sessionId: Int64,
            state: State,
            attempts: Int,
            partsDone: Int,
            queuedAt: Double,
            updatedAt: Double,
            nextAttemptAt: Double,
            conversationIds: [String],
            lastError: String?
        ) {
            self.sessionId = sessionId
            self.state = state
            self.attempts = attempts
            self.partsDone = partsDone
            self.queuedAt = queuedAt
            self.updatedAt = updatedAt
            self.nextAttemptAt = nextAttemptAt
            self.conversationIds = conversationIds
            self.lastError = lastError
        }
    }

    /// One local session, in the shape an upload needs: the span it claims and the lines it holds.
    ///
    /// Times are unix epochs, exactly as stored. Converting them to the seconds-from-conversation-
    /// start the API wants is the uploader's job, because that conversion depends on how the
    /// session is split into requests.
    public struct SessionUpload: Sendable, Equatable {
        public struct Line: Sendable, Equatable {
            public let text: String
            /// True for the microphone: on this machine, the mic is the user and the system tap is
            /// everyone else.
            public let isUser: Bool
            public let startedAt: Double
            public let endedAt: Double
        }

        public let sessionId: Int64
        /// The session's own start. Stable for the life of the row, which is what makes it safe to
        /// bake into an idempotency key.
        public let startedAt: Double
        /// The session's end, or the last line's end while it is still open.
        public let endedAt: Double
        /// Nil while the session is still being written to.
        public let isClosed: Bool
        public let lines: [Line]
    }

    /// Small, uploader-owned scalars that have to survive a relaunch.
    public enum MetaKey: String, Sendable {
        /// When a request last left this Mac — successful or not. The throttle floor, persisted so
        /// that relaunching in a loop cannot spend the hourly budget.
        case lastPostAt = "lastPostAt"
        /// When a conversation was last accepted. Published to the UI.
        case lastUploadedAt = "lastUploadedAt"
        /// The newest session end that reconciliation has already considered.
        case reconcileWatermark = "reconcileWatermark"
    }

    // MARK: - Schema

    /// The identifier written into GRDB's own `grdb_migrations` ledger.
    ///
    /// Namespaced rather than a bare `"v2"` on purpose. This migration is registered here instead of
    /// in `Store.swift`'s migrator, so a plain `"v2"` would silently claim the next name the store
    /// itself will want: GRDB skips any migration whose identifier is already in the ledger, so the
    /// store's future `"v2"` would never run and the schema it assumed would simply not exist. A
    /// distinct name cannot collide, and GRDB tolerates unregistered identifiers in the ledger —
    /// `runMigrations` only ever looks at the intersection of registered and applied.
    public static let migrationIdentifier = "v2-uploads"

    /// Creates the queue tables if they are not there yet, and records the migration in the same
    /// ledger the store's own migrations use. Idempotent, and cheap enough to call on every launch.
    ///
    /// Must be called against an already-open writable store: `uploads.sessionId` references
    /// `sessions`, so `v1` has to be applied first, which opening the store guarantees.
    public static func prepare(_ store: ContextStore) throws {
        try store.write { db in
            try db.execute(
                sql: "CREATE TABLE IF NOT EXISTS grdb_migrations (identifier TEXT NOT NULL PRIMARY KEY)")
            let applied = try String.fetchOne(
                db,
                sql: "SELECT identifier FROM grdb_migrations WHERE identifier = ?",
                arguments: [migrationIdentifier])

            if applied == nil {
                // One row per local session, keyed by it: a session can be enqueued twice — by the
                // engine when it closes and by reconciliation afterwards — and the primary key is what
                // makes the second one a no-op instead of a duplicate conversation.
                try db.execute(
                    sql: """
                        CREATE TABLE IF NOT EXISTS uploads (
                          sessionId INTEGER PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
                          state TEXT NOT NULL,
                          attempts INTEGER NOT NULL DEFAULT 0,
                          partsDone INTEGER NOT NULL DEFAULT 0,
                          queuedAt DOUBLE NOT NULL,
                          updatedAt DOUBLE NOT NULL,
                          nextAttemptAt DOUBLE NOT NULL DEFAULT 0,
                          ownerId TEXT,
                          conversationIds TEXT,
                          lastError TEXT)
                        """)
                // The drain's only hot query is "oldest thing that is due now".
                try db.execute(
                    sql: """
                        CREATE INDEX IF NOT EXISTS idx_uploads_due
                        ON uploads(state, nextAttemptAt, queuedAt)
                        """)
                try db.execute(
                    sql: """
                        CREATE TABLE IF NOT EXISTS upload_meta (
                          key TEXT PRIMARY KEY,
                          value TEXT NOT NULL)
                        """)
            }

            let columnExists = try Int.fetchOne(
                db,
                sql: "SELECT COUNT(*) FROM pragma_table_info('uploads') WHERE name = ?",
                arguments: ["ownerId"]) ?? 0
            if columnExists == 0 {
                try db.execute(sql: "ALTER TABLE uploads ADD COLUMN ownerId TEXT")
            }
            try db.execute(
                sql: "INSERT OR IGNORE INTO grdb_migrations (identifier) VALUES (?)",
                arguments: [migrationIdentifier])
        }
    }

    // MARK: - Marking

    /// Queues a session, or revives one whose last attempt failed.
    ///
    /// Deliberately does nothing to a session that is already `uploaded` or `skipped`: the engine
    /// re-enqueueing a session it closed twice must never turn a finished upload back into work.
    ///
    /// `ownerId` is required rather than defaulted: every row the drain can act on has to name the
    /// account it is owed to, and a parameter that quietly defaults to "nobody" is how rows end up
    /// stranded — `pending` filters on the owner, so an unowned row is invisible to it forever. A
    /// nil here is still allowed, because capture genuinely happens while signed out, but it has to
    /// be a decision the caller made rather than one it forgot to make. `claimOrphans` is what turns
    /// those rows back into work once there is an account to attribute them to.
    public static func markPending(_ store: ContextStore, sessionId: Int64, ownerId: String?) throws {
        let now = ContextTime.now
        try store.write { db in
            try db.execute(
                sql: """
                    INSERT INTO uploads
                      (sessionId, state, attempts, partsDone, queuedAt, updatedAt, nextAttemptAt, ownerId)
                    VALUES (?, 'pending', 0, 0, ?, ?, 0, ?)
                    ON CONFLICT(sessionId) DO UPDATE SET
                      state = 'pending', nextAttemptAt = 0, updatedAt = excluded.updatedAt,
                      ownerId = COALESCE(excluded.ownerId, uploads.ownerId)
                    WHERE uploads.state = 'failed'
                    """,
                arguments: [sessionId, now, now, ownerId])
        }
    }

    /// Records that one part of a multi-part session was accepted. Progress resets the backoff:
    /// the next part is a fresh request, not a retry of a failed one.
    public static func markPartUploaded(
        _ store: ContextStore, sessionId: Int64, partsDone: Int, conversationId: String
    ) throws {
        let now = ContextTime.now
        try store.write { db in
            let existing = try String.fetchOne(
                db, sql: "SELECT conversationIds FROM uploads WHERE sessionId = ?",
                arguments: [sessionId])
            let ids = appended(conversationId, to: existing)
            try db.execute(
                sql: """
                    UPDATE uploads SET
                      state = 'pending', attempts = 0, partsDone = ?, conversationIds = ?,
                      lastError = NULL, updatedAt = ?, nextAttemptAt = 0
                    WHERE sessionId = ?
                    """,
                arguments: [partsDone, ids, now, sessionId])
        }
    }

    /// The session is fully in the account. Terminal.
    public static func markUploaded(
        _ store: ContextStore, sessionId: Int64, conversationIds: [String]
    ) throws {
        let now = ContextTime.now
        let joined = conversationIds.isEmpty ? nil : conversationIds.joined(separator: ",")
        try store.write { db in
            try db.execute(
                sql: """
                    UPDATE uploads SET
                      state = 'uploaded', attempts = 0, partsDone = ?, conversationIds = ?,
                      lastError = NULL, updatedAt = ?, nextAttemptAt = 0
                    WHERE sessionId = ?
                    """,
                arguments: [conversationIds.count, joined, now, sessionId])
        }
    }

    /// The attempt failed and is worth repeating after `retryAt`. Stays in the queue: the whole
    /// point of the table is that nothing is ever dropped on the floor.
    public static func markFailed(
        _ store: ContextStore, sessionId: Int64, error: String, retryAt: Double
    ) throws {
        let now = ContextTime.now
        try store.write { db in
            try db.execute(
                sql: """
                    UPDATE uploads SET
                      state = 'failed', attempts = attempts + 1, lastError = ?,
                      updatedAt = ?, nextAttemptAt = ?
                    WHERE sessionId = ?
                    """,
                arguments: [error, now, retryAt, sessionId])
        }
    }

    /// Holds a still-queued session back without counting it as a failure — used when the session
    /// is still being written to, or when there is nobody signed in to upload it for.
    public static func postpone(
        _ store: ContextStore, sessionId: Int64, until: Double, reason: String
    ) throws {
        let now = ContextTime.now
        try store.write { db in
            try db.execute(
                sql: """
                    UPDATE uploads SET state = 'pending', lastError = ?, updatedAt = ?, nextAttemptAt = ?
                    WHERE sessionId = ?
                    """,
                arguments: [reason, now, until, sessionId])
        }
    }

    /// Nothing here can ever be uploaded. Terminal, so the drain stops reconsidering it.
    public static func markSkipped(_ store: ContextStore, sessionId: Int64, reason: String) throws {
        let now = ContextTime.now
        try store.write { db in
            try db.execute(
                sql: """
                    UPDATE uploads SET state = 'skipped', lastError = ?, updatedAt = ?, nextAttemptAt = 0
                    WHERE sessionId = ?
                    """,
                arguments: [reason, now, sessionId])
        }
    }

    // MARK: - Reading

    /// Which queued rows are `ownerId`'s, as one SQL fragment that every reader shares.
    ///
    /// Sharing it is the point. `pendingCount` used to count every queued row while `pending` read
    /// only the signed-in account's, so rows no drain could ever pick up were still reported to the
    /// user as "waiting to upload" — a queue that looked busy and was completely inert, with nothing
    /// failing to say otherwise. Any future divergence of that shape has to be written here, in one
    /// place, rather than emerging from two queries that quietly drifted apart.
    ///
    /// A nil owner is "nobody is signed in", not a wildcard for a signed-in account. It matches
    /// everything still queued, because with no account in the app every row is equally waiting for
    /// the sign-in that will move it — the signed-out user's backlog is exactly what the menu bar
    /// should still be telling them about. Only `pendingCount` and `nextDueAt` can be asked this
    /// way; `pending` demands a real owner, so the drain can never reach the unfiltered set.
    private static func ownerClause(_ ownerId: String?) -> String {
        ownerId == nil ? "" : " AND ownerId = ?"
    }

    private static func ownerArguments(_ ownerId: String?) -> [any DatabaseValueConvertible] {
        ownerId.map { [$0] } ?? []
    }

    /// Everything still owed to `ownerId` and due by `dueAt`, oldest first.
    ///
    /// The owner is not optional: asking for work is asking for one account's work, and there is no
    /// answer to "what should I upload for nobody". A signed-in session with no user id has to stop
    /// at the caller rather than fall through to a query that would hand unattributed capture to an
    /// account it cannot name.
    public static func pending(
        _ store: ContextStore, ownerId: String, dueAt: Double = ContextTime.now, limit: Int = 50
    ) throws -> [Entry] {
        try store.read { db in
            guard try db.tableExists("uploads") else { return [] }
            let rows = try Row.fetchAll(
                db,
                sql: """
                    SELECT * FROM uploads
                    WHERE state IN ('pending', 'failed') AND nextAttemptAt <= ?\(ownerClause(ownerId))
                    ORDER BY queuedAt ASC, sessionId ASC
                    LIMIT ?
                    """,
                arguments: StatementArguments([dueAt] + ownerArguments(ownerId) + [limit]))
            return rows.map(entry(from:))
        }
    }

    /// How much is still owed to `ownerId`, due or not. This is the number the UI shows, and it is
    /// deliberately the same set `pending` drains — only without the due-time and limit bounds.
    public static func pendingCount(_ store: ContextStore, ownerId: String?) throws -> Int {
        try store.read { db in
            guard try db.tableExists("uploads") else { return 0 }
            return try Int.fetchOne(
                db,
                sql: """
                    SELECT COUNT(*) FROM uploads
                    WHERE state IN ('pending', 'failed')\(ownerClause(ownerId))
                    """,
                arguments: StatementArguments(ownerArguments(ownerId))) ?? 0
        }
    }

    /// When `ownerId`'s earliest still-waiting entry becomes due, or nil when nothing is queued for
    /// them. Lets the uploader sleep exactly as long as it must instead of polling.
    public static func nextDueAt(_ store: ContextStore, ownerId: String?) throws -> Double? {
        try store.read { db in
            guard try db.tableExists("uploads") else { return nil }
            return try Double.fetchOne(
                db,
                sql: """
                    SELECT MIN(nextAttemptAt) FROM uploads
                    WHERE state IN ('pending', 'failed')\(ownerClause(ownerId))
                    """,
                arguments: StatementArguments(ownerArguments(ownerId)))
        }
    }

    /// What the queue holds for each session it is still answerable for: the account conversations
    /// that session has become so far, **empty while it is still owed to an account**.
    ///
    /// **This is how the spine knows that a session and an account conversation are the same talk.**
    /// The Activity panel composes conversation rows from two sources the reference composes from
    /// one: the sessions this Mac heard, and the conversations the account holds. Without a link
    /// between them the same conversation draws twice — once under a title this app invented from
    /// the app that was frontmost, once under the title the account actually gave it.
    ///
    /// The alternative, matching on overlapping clocks, is a guess: an upload's `started_at` is the
    /// session's, but the account re-times, merges and splits, so two rows that are the same talk can
    /// disagree about when it happened, and two that merely overlap can look identical. This is not a
    /// guess — it is the id the backend handed back for that exact session.
    ///
    /// A list per session, not one id, because a session past the endpoint's segment ceiling is
    /// uploaded as consecutive conversations; every part names the session it came from.
    ///
    /// **The empty list is the second thing this read states, and it is a different fact from
    /// absence.** A session queued and owed to an account is not an untitled conversation — it is a
    /// conversation whose title has not been written yet, because the account writes titles and the
    /// upload has not landed. The spine needs to tell that apart from a session nobody is going to
    /// upload, and the queue is the only thing that knows. One query answers both halves: an entry
    /// with ids is linked, an entry with none is still owed, and no entry at all means the queue has
    /// nothing to say about that session (it was never enqueued, or it was `skipped` with nothing
    /// uploadable in it — either way the session is local and stays local).
    ///
    /// A row with no `ownerId` is deliberately *not* reported as owed. Capture that happened while
    /// signed out is parked rather than queued for anybody in particular (see `claimOrphans`), and
    /// nothing is going to turn it into an account conversation until a sign-in claims it.
    ///
    /// Otherwise owner-free, unlike everything else that reads this table. A conversation id is not
    /// a credential and this read spends nothing — it only answers "is this row already on screen
    /// under another name". Scoping it to the signed-in account would make a signed-out panel draw
    /// the duplicates instead.
    public static func conversationLinks(_ store: ContextStore) throws -> [Int64: [String]] {
        try store.read { db in
            guard try db.tableExists("uploads") else { return [:] }
            let rows = try Row.fetchAll(
                db,
                sql: """
                    SELECT sessionId, conversationIds FROM uploads
                    WHERE (conversationIds IS NOT NULL AND conversationIds <> '')
                       OR (state IN ('pending', 'failed') AND ownerId IS NOT NULL)
                    """)
            return rows.reduce(into: [Int64: [String]]()) { links, row in
                guard let sessionId = row["sessionId"] as Int64? else { return }
                // Split exactly as `entry(from:)` joins, so the two readings of this column can
                // never disagree about what it holds.
                let ids = (row["conversationIds"] as String? ?? "")
                    .split(separator: ",")
                    .map(String.init)
                    .filter { !$0.isEmpty }
                links[sessionId] = ids
            }
        }
    }

    public static func entry(_ store: ContextStore, sessionId: Int64) throws -> Entry? {
        try store.read { db in
            guard try db.tableExists("uploads") else { return nil }
            guard
                let row = try Row.fetchOne(
                    db, sql: "SELECT * FROM uploads WHERE sessionId = ?", arguments: [sessionId])
            else { return nil }
            return entry(from: row)
        }
    }

    /// The session and its transcript, or nil if the session is gone.
    ///
    /// Blank lines are dropped here rather than at the wire: the server rejects an empty `text` with
    /// a 422 that would fail the whole conversation, and a line of whitespace is not worth losing a
    /// conversation over.
    public static func content(_ store: ContextStore, sessionId: Int64) throws -> SessionUpload? {
        try store.read { db in
            guard
                let session = try Row.fetchOne(
                    db, sql: "SELECT * FROM sessions WHERE id = ?", arguments: [sessionId])
            else { return nil }

            let rows = try Row.fetchAll(
                db,
                sql: "SELECT source, startedAt, endedAt, text FROM segments WHERE sessionId = ? ORDER BY startedAt ASC, id ASC",
                arguments: [sessionId])

            let lines: [SessionUpload.Line] = rows.compactMap { row -> SessionUpload.Line? in
                let text = (row["text"] as String? ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                guard !text.isEmpty else { return nil }
                let source = SegmentSource(rawValue: row["source"] as String? ?? "") ?? .system
                return SessionUpload.Line(
                    text: text,
                    isUser: source == .mic,
                    startedAt: row["startedAt"] as Double? ?? 0,
                    endedAt: row["endedAt"] as Double? ?? 0)
            }

            let startedAt = session["startedAt"] as Double? ?? 0
            let storedEnd = session["endedAt"] as Double?
            let lastLineEnd = lines.map(\.endedAt).max()
            return SessionUpload(
                sessionId: sessionId,
                startedAt: startedAt,
                endedAt: storedEnd ?? lastLineEnd ?? startedAt,
                isClosed: storedEnd != nil,
                lines: lines)
        }
    }

    // MARK: - Reconciliation

    /// Queues sessions that closed without anyone enqueueing them — a crash between the session
    /// closing and the queue write, or an engine that never got to make the call.
    ///
    /// Bounded by a watermark that starts at "now" the first time this runs, so installing this
    /// build does not decide to upload a month of history the user never asked to sync. Returns how
    /// many sessions it added.
    ///
    /// `ownerId` is the account the rows are owed to, exactly as in `markPending`. Omitting it here
    /// is what stranded them: this insert named no owner, `pending` filters on one, and no other
    /// statement in the tree ever writes the column — so every session reconciliation rescued was
    /// rescued into a row the drain could not see, and stayed `pending` with zero attempts forever.
    @discardableResult
    public static func reconcile(_ store: ContextStore, ownerId: String?, limit: Int = 100) throws -> Int {
        let now = ContextTime.now
        guard let watermark = try timestamp(store, .reconcileWatermark) else {
            try setTimestamp(store, .reconcileWatermark, now)
            return 0
        }

        return try store.write { db in
            let rows = try Row.fetchAll(
                db,
                sql: """
                    SELECT s.id AS id, s.endedAt AS endedAt FROM sessions s
                    LEFT JOIN uploads u ON u.sessionId = s.id
                    WHERE s.endedAt IS NOT NULL AND s.endedAt > ? AND u.sessionId IS NULL
                    ORDER BY s.endedAt ASC
                    LIMIT ?
                    """,
                arguments: [watermark, limit])

            var highest = watermark
            for row in rows {
                let id = row["id"] as Int64? ?? 0
                let endedAt = row["endedAt"] as Double? ?? watermark
                try db.execute(
                    sql: """
                        INSERT OR IGNORE INTO uploads
                          (sessionId, state, attempts, partsDone, queuedAt, updatedAt, nextAttemptAt, ownerId)
                        VALUES (?, 'pending', 0, 0, ?, ?, 0, ?)
                        """,
                    arguments: [id, now, now, ownerId])
                highest = max(highest, endedAt)
            }
            // Only advance past what was actually examined: a full batch means there is more behind
            // it, and the next pass has to start where this one stopped.
            if highest > watermark {
                try db.execute(
                    sql: "INSERT OR REPLACE INTO upload_meta (key, value) VALUES (?, ?)",
                    arguments: [MetaKey.reconcileWatermark.rawValue, String(highest)])
            }
            return rows.count
        }
    }

    // MARK: - Ownership

    /// What `claimOrphans` decided, so the caller can say it out loud. A refusal is a real outcome
    /// and must never look like "there was nothing to do".
    public enum OrphanClaim: Sendable, Equatable {
        /// How many unattributed rows now belong to the signed-in account. Zero is normal.
        case claimed(Int)
        /// This database has already uploaded for a different account, so an unattributed row could
        /// have been captured by either of them and nothing on disk can tell us which.
        case refusedForeignOwner
    }

    /// Attributes rows that were queued before there was an account to attribute them to.
    ///
    /// Capture that happens while signed out is queued with no owner — that is deliberate, and the
    /// promise the uploader makes is that it is parked rather than dropped. Unparking it is this
    /// function, and it is the only thing standing between a row with no owner and the drain, so it
    /// is where the account-isolation question actually gets answered.
    ///
    /// **Nothing records who captured a session.** `sessions` holds a start, an end and an app hint;
    /// the queue's `ownerId` is the only attribution anywhere in the schema, and for these rows it is
    /// exactly what is missing. So the honest evidence available is one question: *has this database
    /// ever worked for anybody else?* If every attributed row names the account asking, then no other
    /// account has ever had capture on this Mac to lose, and claiming is provably safe. If any row
    /// names a different account, the Mac has served two people, an unattributed row could belong to
    /// either, and we refuse — the rows stay local, which costs an upload, where guessing wrong would
    /// put one person's conversations in another person's account.
    ///
    /// Terminal rows are left alone: `uploaded` and `skipped` are nobody's work any more, and
    /// rewriting them would only churn `updatedAt` on settled history.
    @discardableResult
    public static func claimOrphans(_ store: ContextStore, ownerId: String) throws -> OrphanClaim {
        let now = ContextTime.now
        return try store.write { db in
            guard try db.tableExists("uploads") else { return .claimed(0) }
            let foreign = try Int.fetchOne(
                db,
                sql: "SELECT COUNT(*) FROM uploads WHERE ownerId IS NOT NULL AND ownerId <> ?",
                arguments: [ownerId]) ?? 0
            guard foreign == 0 else { return .refusedForeignOwner }

            try db.execute(
                sql: """
                    UPDATE uploads SET ownerId = ?, updatedAt = ?
                    WHERE ownerId IS NULL AND state IN ('pending', 'failed')
                    """,
                arguments: [ownerId, now])
            return .claimed(db.changesCount)
        }
    }

    // MARK: - Meta

    public static func timestamp(_ store: ContextStore, _ key: MetaKey) throws -> Double? {
        try store.read { db in
            guard try db.tableExists("upload_meta") else { return nil }
            guard
                let raw = try String.fetchOne(
                    db, sql: "SELECT value FROM upload_meta WHERE key = ?", arguments: [key.rawValue])
            else { return nil }
            return Double(raw)
        }
    }

    public static func setTimestamp(_ store: ContextStore, _ key: MetaKey, _ value: Double) throws {
        try store.write { db in
            try db.execute(
                sql: "INSERT OR REPLACE INTO upload_meta (key, value) VALUES (?, ?)",
                arguments: [key.rawValue, String(value)])
        }
    }

    // MARK: - Row mapping

    private static func entry(from row: Row) -> Entry {
        let ids = (row["conversationIds"] as String? ?? "")
            .split(separator: ",")
            .map(String.init)
            .filter { !$0.isEmpty }
        return Entry(
            sessionId: row["sessionId"] as Int64? ?? 0,
            state: State(rawValue: row["state"] as String? ?? "") ?? .pending,
            attempts: row["attempts"] as Int? ?? 0,
            partsDone: row["partsDone"] as Int? ?? 0,
            queuedAt: row["queuedAt"] as Double? ?? 0,
            updatedAt: row["updatedAt"] as Double? ?? 0,
            nextAttemptAt: row["nextAttemptAt"] as Double? ?? 0,
            conversationIds: ids,
            lastError: row["lastError"] as String?)
    }

    private static func appended(_ conversationId: String, to existing: String?) -> String {
        var ids = (existing ?? "").split(separator: ",").map(String.init).filter { !$0.isEmpty }
        // Re-posting a part returns the same conversation id; recording it twice would make
        // `partsDone` and the id list disagree about how much is done.
        if !ids.contains(conversationId) { ids.append(conversationId) }
        return ids.joined(separator: ",")
    }
}
