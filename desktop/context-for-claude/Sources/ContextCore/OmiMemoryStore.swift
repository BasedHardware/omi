import Foundation
import GRDB

/// A memory read from the main Omi desktop app's local database.
///
/// Mirrors the subset of `MemoryRecord` columns that Context for Claude renders.
/// `id` is the backend ID when synced, or `local_<rowid>` when the memory has
/// not reached the server yet — the same convention the main app uses.
public struct LocalMemory: Sendable, Equatable {
    public let id: String
    public let content: String
    public let category: String?
    /// When the main app recorded it, in Unix epoch seconds — `nil` when the row's `createdAt` could
    /// not be read.
    ///
    /// Stored in that database as a `DATETIME` holding `"2026-08-14 13:04:58.787"` — space
    /// separated, sub-second, **and with no zone designator**. It is UTC (verified against the live
    /// file: the newest row read 13:04 UTC while the machine's clock said 09:04 EDT), and GRDB
    /// decodes exactly that format as UTC, which is why this is a `Date` decode and not a hand-rolled
    /// parse. It matters because the Activity spine files a memory on the *day* it happened; read as
    /// local time, an evening memory lands four hours out and on the wrong side of midnight.
    public let createdAt: Double?
    /// The backend conversation this fact was extracted from, when the main app recorded one.
    ///
    /// A backend UUID and not a local row id — confirmed against the live database, where these
    /// match the ids `GET /v1/conversations` serves — which is what makes it usable for filing a
    /// memory under the conversation it came out of. `nil` for a memory the user wrote themselves,
    /// and for the ~91% of rows the main app has no conversation recorded for.
    public let conversationId: String?

    public init(
        id: String,
        content: String,
        category: String?,
        createdAt: Double? = nil,
        conversationId: String? = nil
    ) {
        self.id = id
        self.content = content
        self.category = category
        self.createdAt = createdAt
        self.conversationId = conversationId
    }
}

/// Read-only access to the main Omi desktop app's `memories` table.
///
/// Opens `omi.db` with a read-only WAL connection — the same safe pattern
/// `ContextStore` uses for `context.db`. A reader never blocks the main app's
/// writer, so a Claude query can run while Omi is capturing.
///
/// `@unchecked Sendable` is honest: the only stored state is GRDB's pool, which
/// serializes its own connections.
public final class OmiMemoryStore: @unchecked Sendable {
    public static let shared = OmiMemoryStore()

    private let pool: DatabasePool?

    /// Opens the main app's database, or nothing. `init(url:)` exists so a test can point this at a
    /// database it made itself — **nothing in this package may write to the real one**, which is the
    /// user's only copy of their memories and belongs to a different app entirely.
    public convenience init() {
        self.init(url: ContextPaths.omiDatabaseURL)
    }

    public init(url: URL?) {
        guard let url else {
            pool = nil
            return
        }
        pool = try? DatabasePool(
            path: url.path,
            configuration: ContextStore.makeConfiguration(readOnly: true))
    }

    /// Rows one call may return, whatever the caller asks for. The main app's table is six and a half
    /// thousand rows deep on the machine this was measured on and grows for the life of the install,
    /// so an unbounded read is a read whose cost is the user's history.
    public static let maximumRows = 500

    /// True when the main Omi app's database was found and opened.
    public var isAvailable: Bool { pool != nil }

    /// Searches memories by substring, matching the main app's `content LIKE` pattern.
    ///
    /// `LIKE` wildcards in the query are escaped so user text is treated literally.
    /// Only non-deleted, non-dismissed memories are returned, newest first.
    public func searchMemories(query: String, limit: Int) -> [LocalMemory] {
        guard let pool else { return [] }
        let escaped = query
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "%", with: "\\%")
            .replacingOccurrences(of: "_", with: "\\_")
        let pattern = "%\(escaped)%"
        let clamped = max(1, min(limit, 50))
        return (try? pool.read { db in
            try LocalMemoryRow.fetchAll(
                db,
                sql: """
                SELECT \(LocalMemoryRow.columns)
                FROM memories
                WHERE deleted = 0 AND isDismissed = 0
                  AND content LIKE ? ESCAPE '\\'
                ORDER BY createdAt DESC
                LIMIT ?
                """,
                arguments: [pattern, clamped]
            )
        })?.compactMap { $0.toMemory() } ?? []
    }

    /// The newest memories the main app is holding, newest first.
    ///
    /// **The same predicate `searchMemories` uses, deliberately and not by coincidence.** It is also
    /// the predicate the main app's own `MemoriesPage` renders by, and a second surface in a second
    /// process showing a set of memories the first one considers deleted or dismissed is a
    /// disagreement the user has no way to resolve. Two readers of one table, one rule.
    ///
    /// Ordered on `createdAt`, which is indexed (`idx_memories_created`), so a bounded read of the
    /// newest page is an index walk rather than a sort over six thousand rows.
    public func recentMemories(limit: Int) -> [LocalMemory] {
        guard let pool else { return [] }
        let clamped = max(1, min(limit, Self.maximumRows))
        return (try? pool.read { db in
            try LocalMemoryRow.fetchAll(
                db,
                sql: """
                SELECT \(LocalMemoryRow.columns)
                FROM memories
                WHERE deleted = 0 AND isDismissed = 0
                ORDER BY createdAt DESC
                LIMIT ?
                """,
                arguments: [clamped]
            )
        })?.compactMap { $0.toMemory() } ?? []
    }
}

/// One row of the main app's `memories` table, in the subset this package renders.
///
/// Every column is read optionally even where that table declares `NOT NULL`, for the reason the
/// backend wire shapes give: this schema belongs to **another application**, which migrates it on
/// its own release schedule and has already renamed and added columns several times. A row that has
/// stopped decoding is a row that vanishes; a whole read that throws is a memory column that goes
/// blank, and blank is the exact failure this feature exists to fix.
private struct LocalMemoryRow: FetchableRecord {
    /// The column list, written once so the two queries above cannot drift into selecting different
    /// things and decoding the same struct out of them.
    static let columns = "id, backendId, content, category, createdAt, conversationId"

    let id: Int64?
    let backendId: String?
    let content: String
    let category: String?
    let createdAt: Date?
    let conversationId: String?

    enum Columns: String, ColumnExpression {
        case id, backendId, content, category, createdAt, conversationId
    }

    init(row: Row) {
        id = row[Columns.id]
        backendId = row[Columns.backendId]
        content = row[Columns.content] ?? ""
        category = row[Columns.category]
        // GRDB reads `"YYYY-MM-DD HH:MM:SS.SSS"` as UTC, which is how that app writes it. A row whose
        // stamp will not decode keeps the memory and loses only its place in time — the caller
        // decides what to do with a nil, and dropping a fact because its clock is unreadable would
        // be the worse trade.
        createdAt = row[Columns.createdAt]
        conversationId = row[Columns.conversationId]
    }

    func toMemory() -> LocalMemory? {
        guard !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        // `backendId` first: once a memory has synced, that is the id the account knows it by, and it
        // is what lets a caller reconcile these rows against `GET /v3/memories` instead of showing
        // the same fact twice. A row that has not synced has no such id and gets the main app's own
        // `local_<rowid>` convention, which is stable for as long as the row is.
        let memoryId = backendId ?? (id.map { "local_\($0)" } ?? "")
        guard !memoryId.isEmpty else { return nil }
        return LocalMemory(
            id: memoryId,
            content: content,
            category: category,
            createdAt: createdAt?.timeIntervalSince1970,
            conversationId: conversationId.flatMap { $0.isEmpty ? nil : $0 })
    }
}
