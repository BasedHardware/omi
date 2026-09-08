import Foundation
import GRDB
import XCTest

@testable import ContextCore

/// Reading the Omi desktop app's own `memories` table.
///
/// **Every database below is one this test built.** The real one —
/// `~/Library/Application Support/Omi/users/<uid>/omi.db` — belongs to another application and holds
/// the user's only copy of thousands of memories; nothing in this package may write to it, and no
/// test may depend on its contents. What *is* taken from the real file is its **schema and its value
/// shapes**, read read-only and reproduced verbatim in `makeDatabase` below, because the risk this
/// covers is entirely about decoding a foreign table correctly.
final class OmiMemoryStoreTests: XCTestCase {

    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("omi-memory-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: root)
        root = nil
    }

    /// The columns and declared types the shipping app actually uses, copied from the live file. The
    /// twenty-odd columns this package never reads are left out; what matters is that the six it does
    /// read carry the declared types they carry there — `DATETIME` holding text, `BOOLEAN` holding
    /// 0/1, and a nullable `backendId`.
    private func makeDatabase(named name: String = "omi.db") throws -> URL {
        let url = root.appendingPathComponent(name)
        let queue = try DatabaseQueue(path: url.path)
        try queue.write { db in
            try db.execute(
                sql: """
                CREATE TABLE "memories" (
                    "id" INTEGER PRIMARY KEY AUTOINCREMENT,
                    "backendId" TEXT UNIQUE,
                    "backendSynced" BOOLEAN NOT NULL DEFAULT 0,
                    "content" TEXT NOT NULL,
                    "category" TEXT NOT NULL,
                    "conversationId" TEXT,
                    "isDismissed" BOOLEAN NOT NULL DEFAULT 0,
                    "deleted" BOOLEAN NOT NULL DEFAULT 0,
                    "createdAt" DATETIME NOT NULL,
                    "updatedAt" DATETIME NOT NULL
                )
                """)
        }
        return url
    }

    private func insert(
        _ url: URL,
        backendId: String?,
        content: String,
        category: String = "system",
        conversationId: String? = nil,
        createdAt: String,
        deleted: Int = 0,
        isDismissed: Int = 0
    ) throws {
        let queue = try DatabaseQueue(path: url.path)
        try queue.write { db in
            try db.execute(
                sql: """
                INSERT INTO memories
                    (backendId, content, category, conversationId, isDismissed, deleted, createdAt, updatedAt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                arguments: [
                    backendId, content, category, conversationId, isDismissed, deleted, createdAt,
                    createdAt,
                ])
        }
    }

    // MARK: - Reading

    /// Newest first, and only the memories the main app itself would render. The predicate is shared
    /// with `searchMemories` on purpose: two readers of one table disagreeing about what is deleted
    /// is a disagreement the user cannot resolve.
    func testRecentMemoriesAreNewestFirstAndExcludeDeletedAndDismissed() throws {
        let url = try makeDatabase()
        try insert(url, backendId: "b-old", content: "Oldest", createdAt: "2026-08-10 10:00:00.000")
        try insert(url, backendId: "b-new", content: "Newest", createdAt: "2026-08-12 10:00:00.000")
        try insert(url, backendId: "b-del", content: "Deleted", createdAt: "2026-08-13 10:00:00.000", deleted: 1)
        try insert(
            url, backendId: "b-dis", content: "Dismissed", createdAt: "2026-08-14 10:00:00.000",
            isDismissed: 1)

        let rows = OmiMemoryStore(url: url).recentMemories(limit: 10)

        XCTAssertEqual(rows.map(\.id), ["b-new", "b-old"])
    }

    /// **The claim the day a memory is filed under depends on.**
    ///
    /// That column is a `DATETIME` holding `"2026-08-14 13:04:58.787"` — space separated, sub-second,
    /// and with **no zone designator at all**. Verified against the live database: its newest row
    /// read `13:04` UTC while this machine's clock said `09:04` EDT, so the text is UTC and GRDB's
    /// decoding of that format as UTC is the correct reading. Read as *local* time instead, an
    /// evening memory lands hours out and routinely on the wrong side of midnight — which on this
    /// surface means the wrong day header.
    func testCreatedAtIsReadAsUTC() throws {
        let url = try makeDatabase()
        try insert(url, backendId: "b-1", content: "Anything", createdAt: "2026-08-14 13:04:58.787")

        let row = try XCTUnwrap(OmiMemoryStore(url: url).recentMemories(limit: 1).first)

        // 2026-08-14T13:04:58.787Z, computed independently of the parser under test.
        var components = DateComponents()
        components.year = 2026
        components.month = 8
        components.day = 14
        components.hour = 13
        components.minute = 4
        components.second = 58
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        let expected = try XCTUnwrap(calendar.date(from: components)).timeIntervalSince1970

        XCTAssertEqual(try XCTUnwrap(row.createdAt), expected + 0.787, accuracy: 0.01)
    }

    /// A synced row is known by the id the account knows it by; an unsynced one gets the main app's
    /// own `local_<rowid>` convention. This is what lets a caller reconcile these rows against
    /// `GET /v3/memories` instead of showing the same fact twice.
    func testSyncedRowsCarryTheBackendIdAndUnsyncedOnesGetALocalId() throws {
        let url = try makeDatabase()
        try insert(url, backendId: "cbe4a6de-0000-4000-8000-000000000001", content: "Synced",
            createdAt: "2026-08-12 10:00:00.000")
        try insert(url, backendId: nil, content: "Not yet synced", createdAt: "2026-08-11 10:00:00.000")

        let rows = OmiMemoryStore(url: url).recentMemories(limit: 10)

        XCTAssertEqual(rows.map(\.id), ["cbe4a6de-0000-4000-8000-000000000001", "local_2"])
    }

    /// The conversation link is a backend UUID in that table — confirmed against the live file, where
    /// these match the ids `GET /v1/conversations` serves — so it is carried through rather than
    /// dropped. An empty string is the same claim as absent and is normalised to nil, or the composer
    /// would look up a key it can never find.
    func testTheConversationLinkIsCarriedThroughAndEmptyBecomesNil() throws {
        let url = try makeDatabase()
        try insert(
            url, backendId: "b-1", content: "From a conversation",
            conversationId: "b67cbdee-b07b-40fb-9d62-26b2a0806ed4", createdAt: "2026-08-12 10:00:00.000")
        try insert(
            url, backendId: "b-2", content: "Written down", conversationId: "",
            createdAt: "2026-08-11 10:00:00.000")

        let rows = OmiMemoryStore(url: url).recentMemories(limit: 10)

        XCTAssertEqual(rows.first?.conversationId, "b67cbdee-b07b-40fb-9d62-26b2a0806ed4")
        XCTAssertNil(rows.last?.conversationId)
    }

    /// Bounded whatever the caller asks. That table is six and a half thousand rows deep on the
    /// machine this was measured on and grows for the life of the install.
    func testTheReadIsBoundedByItsOwnCeiling() throws {
        let url = try makeDatabase()
        for index in 0..<5 {
            try insert(
                url, backendId: "b-\(index)", content: "Memory \(index)",
                createdAt: "2026-08-1\(index) 10:00:00.000")
        }

        XCTAssertEqual(OmiMemoryStore(url: url).recentMemories(limit: 2).count, 2)
        XCTAssertLessThanOrEqual(
            OmiMemoryStore(url: url).recentMemories(limit: 100_000).count,
            OmiMemoryStore.maximumRows)
    }

    /// No Omi install is an ordinary state, not an error: a Mac running Context for Claude on its own
    /// simply has no local memories, and the reader must say so rather than throw on a path the
    /// panel waits behind.
    func testNoDatabaseIsAnOrdinaryEmptyAnswer() {
        let store = OmiMemoryStore(url: nil)

        XCTAssertFalse(store.isAvailable)
        XCTAssertEqual(store.recentMemories(limit: 10).count, 0)
        XCTAssertEqual(store.searchMemories(query: "anything", limit: 10).count, 0)
    }

    // MARK: - Which database wins

    /// **The defect this scan shipped with.**
    ///
    /// The rule used to be "sort the directory names and take the first candidate that exists", which
    /// assumes the users directory holds users. On the machine this was found on it held **1,554
    /// subdirectories**, all but a handful of them scaffolding from the Omi desktop app's own test
    /// harness — `cancelled-status-reconcile-test-…`, `memories-vm-observer-…` — each with an empty
    /// 4 KB database inside it. The alphabetical rule resolved to the first of those, a file with no
    /// `memories` table at all, while the signed-in user's real database sat hundreds of entries
    /// later holding 6,598 memories in 58 MB. Everything downstream read the empty file and reported
    /// confidently that the user had no memories — including the MCP tools, which advertise local
    /// memories to Claude as always available.
    func testTheLargestDatabaseWinsRatherThanTheFirstNameInTheAlphabet() throws {
        let base = root.appendingPathComponent("Application Support", isDirectory: true)
        let users = base.appendingPathComponent("Omi", isDirectory: true)
            .appendingPathComponent("users", isDirectory: true)

        // Alphabetically first, and empty — the shape every one of those 1,554 fixtures has.
        try write(users, user: "cancelled-status-reconcile-test-049BFE18", bytes: 4_096)
        try write(users, user: "memories-vm-observer-031C666D", bytes: 8_192)
        // The real one, hundreds of entries later in the alphabet.
        try write(users, user: "zP5DfPuJr9Y43rjS8qDAtSFOrQf2", bytes: 512_000)

        let resolved = try XCTUnwrap(ContextPaths.omiDatabaseURL(inApplicationSupport: base))

        XCTAssertEqual(resolved.deletingLastPathComponent().lastPathComponent, "zP5DfPuJr9Y43rjS8qDAtSFOrQf2")
    }

    /// `anonymous` is the signed-out fallback, so a signed-in user's database is the better answer
    /// whenever the two are otherwise indistinguishable — the one part of the old rule worth keeping.
    func testAnonymousLosesEveryTie() throws {
        let base = root.appendingPathComponent("Application Support", isDirectory: true)
        let users = base.appendingPathComponent("Omi", isDirectory: true)
            .appendingPathComponent("users", isDirectory: true)
        try write(users, user: "anonymous", bytes: 4_096)
        try write(users, user: "zP5DfPuJr9Y43rjS8qDAtSFOrQf2", bytes: 4_096)

        let resolved = try XCTUnwrap(ContextPaths.omiDatabaseURL(inApplicationSupport: base))

        XCTAssertEqual(resolved.deletingLastPathComponent().lastPathComponent, "zP5DfPuJr9Y43rjS8qDAtSFOrQf2")
    }

    /// `Omi Beta` is a fallback and never a competitor: a stable install that exists at all wins,
    /// however small it is, because that is the one the user is running.
    func testTheBetaRootIsOnlyReachedWhenTheStableOneHasNothing() throws {
        let base = root.appendingPathComponent("Application Support", isDirectory: true)
        try write(
            base.appendingPathComponent("Omi Beta", isDirectory: true)
                .appendingPathComponent("users", isDirectory: true),
            user: "beta-user", bytes: 512_000)

        let betaOnly = try XCTUnwrap(ContextPaths.omiDatabaseURL(inApplicationSupport: base))
        XCTAssertEqual(betaOnly.deletingLastPathComponent().lastPathComponent, "beta-user")

        try write(
            base.appendingPathComponent("Omi", isDirectory: true)
                .appendingPathComponent("users", isDirectory: true),
            user: "stable-user", bytes: 4_096)

        let resolved = try XCTUnwrap(ContextPaths.omiDatabaseURL(inApplicationSupport: base))
        XCTAssertEqual(resolved.deletingLastPathComponent().lastPathComponent, "stable-user")
    }

    func testNoOmiInstallResolvesToNothing() throws {
        let base = root.appendingPathComponent("Application Support", isDirectory: true)
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)

        XCTAssertNil(ContextPaths.omiDatabaseURL(inApplicationSupport: base))
    }

    /// A file of a stated size, which is the only property the resolution reads.
    private func write(_ users: URL, user: String, bytes: Int) throws {
        let directory = users.appendingPathComponent(user, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try Data(count: bytes).write(to: directory.appendingPathComponent("omi.db"))
    }
}
