import Foundation
import GRDB

/// One cached account row, as the database holds it.
public struct CachedAccountRow: Sendable, Equatable {
    /// Which of the spine's three account sources this belongs to. A free string rather than an enum
    /// for the same reason `payload` is a blob: the set of sources is the app target's business.
    public let source: String
    /// The account's own id for the row. Half the primary key, so re-caching cannot duplicate.
    public let id: String
    /// The row's own instant, Unix epoch seconds. Only ever used to decide which rows survive the
    /// trim — the app re-reads whatever instant it cares about out of `payload`.
    public let at: Double
    /// Whatever the app encoded. JSON in practice; nothing here parses it.
    public let payload: String

    public init(source: String, id: String, at: Double, payload: String) {
        self.source = source
        self.id = id
        self.at = at
        self.payload = payload
    }
}

/// The last thing the account said, kept on disk so a cold launch can paint before the network does.
///
/// **This table is a copy and never an authority.** Every row in it came from the account and is
/// replaced by the account the moment a read lands; nothing writes a row here that did not arrive
/// over the wire, and nothing reads from here once a real answer exists. That is the whole of the
/// contract, and it is what makes a stale row harmless: a conversation deleted on the phone survives
/// here only until the next read of its source, which rewrites that source wholesale.
///
/// **Why it exists.** The Activity spine's account half was network-only, so a cold launch drew the
/// local sessions it had — every one of them titled `Untitled conversation`, because a title is
/// written by the backend when a transcript is uploaded — and sat there until three HTTP round trips
/// came back. The shipping Omi app has never looked like that for the same data: its conversation
/// list is cache-first by construction (`ConversationRepository.load` reads SQLite, emits, *then*
/// fetches), so it paints real titles in milliseconds. This is that arrangement, in this app's store.
///
/// **Opaque payloads on purpose.** `ContextCore` knows nothing about the spine's row shapes and must
/// not: the seam types live in the app target, and teaching the database about them would put a
/// presentation decision under a migration. A row here is an identity, an instant and a blob the app
/// wrote, so this schema is stable across every change to what a row draws.
public enum AccountCacheQueries {

    /// The newest cached rows of one source, newest first.
    ///
    /// Ordered and limited in SQL rather than in the caller: the trim below keeps the table small,
    /// but "small" is per source, and a caller wanting fifty would otherwise decode six hundred to
    /// throw most of them away — on the launch path this exists to shorten.
    ///
    /// **`id` breaks ties, and ties are ordinary here.** `at` is not unique: a date-only task is
    /// stamped at 11:59 PM like every other date-only task, and a batch of memories backfilled
    /// together shares an instant. Without a second key SQLite may pick any subset for the bounded
    /// page and any order within it — so the page a launch paints could differ from the page the
    /// trim below decided to keep, and the same corpus could draw in a different order each time.
    public static func recent(
        _ store: ContextStore, source: String, limit: Int
    ) throws -> [CachedAccountRow] {
        guard limit > 0 else { return [] }
        return try store.read { db in
            try Row.fetchAll(
                db,
                sql: """
                    SELECT source, id, at, payload FROM account_rows
                    WHERE source = ? ORDER BY at DESC, id DESC LIMIT ?
                    """,
                arguments: [source, limit]
            ).map {
                CachedAccountRow(
                    source: $0["source"], id: $0["id"], at: $0["at"], payload: $0["payload"])
            }
        }
    }

    /// Replaces one source's rows, and trims what is left to the newest `keeping`.
    ///
    /// **Scoped to the one source, and total within it.** The two halves of that are both
    /// load-bearing and they pull in opposite directions:
    ///
    /// - *Scoped*, because the three sources fail independently — this is an account that served
    ///   conversations while `/v3/memories` answered 503 for eight hours — so a write that cleared
    ///   the whole table would turn one source's outage into the loss of a cache serving the other
    ///   two perfectly well. A source nobody passes here keeps whatever it had.
    /// - *Total*, because within a source the caller is handing over the account's own answer, and
    ///   a row the account no longer lists is a row that no longer exists. Upserting instead would
    ///   leave a conversation deleted on the phone in the cache indefinitely — it is never
    ///   overwritten, and the trim cannot reach it while its timestamp keeps it in the newest page.
    ///   That is a deletion the user made, coming back to their screen on every launch.
    ///
    /// The trim is what bounds the file. Without it the table becomes the account's whole history,
    /// one hydration walk at a time, inside a database whose reason for existing is screen capture.
    public static func replace(
        _ store: ContextStore, source: String, rows: [CachedAccountRow], keeping limit: Int
    ) throws {
        try store.write { db in
            try db.execute(sql: "DELETE FROM account_rows WHERE source = ?", arguments: [source])
            for row in rows {
                try db.execute(
                    sql: """
                        INSERT INTO account_rows (source, id, at, payload) VALUES (?, ?, ?, ?)
                        ON CONFLICT(source, id) DO UPDATE SET at = excluded.at, payload = excluded.payload
                        """,
                    arguments: [source, row.id, row.at, row.payload])
            }
            // The table is `WITHOUT ROWID`, so the trim names the key it actually has.
            try db.execute(
                sql: """
                    DELETE FROM account_rows WHERE source = ? AND id NOT IN (
                      SELECT id FROM account_rows WHERE source = ? ORDER BY at DESC, id DESC LIMIT ?
                    )
                    """,
                arguments: [source, source, max(limit, 0)])
        }
    }

    /// Empties the cache. Signing out is the caller: one account's rows must never be the first
    /// thing the next account sees.
    public static func clear(_ store: ContextStore) throws {
        try store.write { db in
            try db.execute(sql: "DELETE FROM account_rows")
        }
    }

    /// How many rows one source is holding. Tests and one launch log line; nothing on a hot path.
    public static func count(_ store: ContextStore, source: String) throws -> Int {
        try store.read { db in
            try Int.fetchOne(
                db, sql: "SELECT COUNT(*) FROM account_rows WHERE source = ?", arguments: [source]) ?? 0
        }
    }
}
