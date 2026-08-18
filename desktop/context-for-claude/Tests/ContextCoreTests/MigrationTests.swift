import Foundation
import GRDB
import XCTest

@testable import ContextCore

/// Opening a database that is *already partly migrated*, which is the one case every other test in
/// this suite skips by starting from an empty file.
///
/// A real Mac could not open its database at launch:
///
/// ```
/// Could not open the database: SQLite error 1: index idx_frames_showable already exists
///   - while executing `CREATE INDEX "idx_frames_showable" ON "frames"("capturedAt") …`
/// ```
///
/// The cause is that this process opens **two writable stores on the same file** — `EngineStore`
/// for capture and the upload queue's lazy open — and each runs the migrator on its own
/// `DatabasePool`, i.e. its own SQLite connection. `DatabaseMigrator.runMigrations` reads the
/// applied-identifier ledger *outside* any transaction and only then runs each migration inside
/// one, so two connections that open at the same moment both compute the same list of unapplied
/// migrations. One wins the write lock and commits; the loser runs `CREATE INDEX` against a
/// database that already has the index, throws, and takes the whole `ContextStore.init` with it.
///
/// The bookkeeping itself is sound: GRDB writes the schema change and the ledger row in one
/// `IMMEDIATE` transaction, so a migration is never half-recorded. The failure is a lost race, not
/// a torn write — which is why the winner's database ends up correct and the retry 30 s later
/// opened fine.
final class MigrationTests: XCTestCase {
    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("ambient-migrations-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: root)
        root = nil
    }

    private var databaseURL: URL { root.appendingPathComponent("context.db") }

    /// The reported failure, reproduced as the state the losing connection actually meets: the
    /// schema change is on disk and the ledger does not name it.
    ///
    /// Rehearsed by migrating a store fully and then deleting the three newest ledger rows, which
    /// is byte-for-byte the database the failing open saw. Re-opening has to succeed — every one of
    /// the three migrations is expected to survive being run a second time.
    func testOpeningADatabaseWhoseSchemaIsAheadOfItsLedgerSucceeds() throws {
        _ = try ContextStore(url: databaseURL)

        try forgetMigrations(["v8-frame-showable-index", "v9-frame-bundle-by-app-index", "v10-ax-node-last-seen"])
        XCTAssertTrue(try indexExists("idx_frames_showable"), "the fixture failed to leave the index in place")
        XCTAssertTrue(try indexExists("idx_frames_bundle_by_app"))
        XCTAssertTrue(try columnExists("lastSeenAt", in: "ax_nodes"))

        // The assertion. Before the fix this threw `index idx_frames_showable already exists`.
        _ = try ContextStore(url: databaseURL)

        // And it is genuinely migrated afterwards, not merely open: a swallowed failure that left
        // the ledger short would make the MCP reader refuse the database forever.
        XCTAssertFalse(ContextStore.needsAppUpgrade(at: databaseURL))
        XCTAssertTrue(try indexExists("idx_frames_showable"))
        XCTAssertTrue(try indexExists("idx_frames_bundle_by_app"))
        XCTAssertTrue(try columnExists("lastSeenAt", in: "ax_nodes"))
    }

    /// The other direction, and the one a blanket `IF NOT EXISTS` could quietly break: a database
    /// that has *not* run these migrations still gets them. A migration made idempotent by skipping
    /// its own work would pass the test above and leave every real upgrade without an index.
    func testAFreshDatabaseStillGetsEveryMigration() throws {
        _ = try ContextStore(url: databaseURL)

        XCTAssertTrue(try indexExists("idx_frames_showable"))
        XCTAssertTrue(try indexExists("idx_frames_bundle_by_app"))
        XCTAssertTrue(try columnExists("lastSeenAt", in: "ax_nodes"))
        XCTAssertTrue(try ledger().isSuperset(of: [
            "v8-frame-showable-index", "v9-frame-bundle-by-app-index", "v10-ax-node-last-seen",
        ]))
    }

    /// The cause itself: two writable stores opened on one file at the same moment, exactly as
    /// `EngineStore.open()` and the upload queue's lazy open do during launch. Every one of them
    /// has to come back with a usable store.
    func testConcurrentOpensOfOneDatabaseAllSucceed() throws {
        let opens = 8
        let started = DispatchSemaphore(value: 0)
        let finished = expectation(description: "every open returned")
        finished.expectedFulfillmentCount = opens

        let failures = Failures()
        for _ in 0..<opens {
            DispatchQueue.global().async {
                // Every thread waits on the same gate, so the opens genuinely overlap rather than
                // queueing behind each other's setup.
                started.wait()
                do { _ = try ContextStore(url: self.databaseURL) } catch { failures.record(error) }
                finished.fulfill()
            }
        }
        for _ in 0..<opens { started.signal() }
        wait(for: [finished], timeout: 30)

        XCTAssertEqual(failures.messages, [], "a concurrent open failed to migrate")
    }

    /// **The MCP server must never be one of the racers, and this is what keeps it out.**
    ///
    /// Claude Desktop spawns `context-for-claude-mcp` repeatedly and keeps several alive at once, so
    /// a reader that migrated would put four or five extra migrators against the app on the first
    /// launch after any release that adds one — turning a rare collision into a near-certainty for
    /// the whole audience. It does not: `ContextMCP/main.swift` opens with `readOnly: true`, and
    /// that branch of `ContextStore.init` runs no migrator at all. It waits for the schema it
    /// expects instead, reporting `.awaitingAppUpgrade` when the app has not caught up.
    ///
    /// Asserted rather than trusted, because "open it writable, it is simpler" is a one-word change
    /// that nothing else in the suite would notice: a read-only open of a database missing this
    /// binary's migrations must refuse, and must leave the schema exactly as it found it.
    func testTheReadOnlyStoreRefusesAnOldSchemaInsteadOfMigratingIt() throws {
        _ = try ContextStore(url: databaseURL)
        try forgetMigrations(["v10-ax-node-last-seen"])
        try dropColumn("lastSeenAt", from: "ax_nodes")

        XCTAssertThrowsError(try ContextStore(url: databaseURL, readOnly: true)) { error in
            XCTAssertStoreError(error, .awaitingAppUpgrade)
        }
        XCTAssertFalse(try columnExists("lastSeenAt", in: "ax_nodes"), "the reader migrated the database")
        XCTAssertFalse(try ledger().contains("v10-ax-node-last-seen"), "the reader wrote to the ledger")

        // And the app still repairs it, so refusing is a wait rather than a dead end.
        _ = try ContextStore(url: databaseURL)
        XCTAssertTrue(try columnExists("lastSeenAt", in: "ax_nodes"))
    }

    /// The gate that makes the fix a repair rather than a retry: a second holder does not proceed
    /// until the first lets go.
    ///
    /// **This is what carries the cross-process claim.** The test above runs two `DatabasePool`s in
    /// one process, which is a real racer — the app opens exactly that pair — but it is not two
    /// processes, and spawning one from a unit test would need a helper executable. `flock` is what
    /// closes that gap, and its exclusion is a property of the *open file description*, not of the
    /// process: two descriptors contend identically whether they were opened by one process or two.
    /// Asserting it across two descriptors here therefore asserts the same kernel behaviour a second
    /// copy of the app meets.
    func testTheMigrationGateExcludesASecondHolderUntilReleased() throws {
        let first = MigrationGate(besideDatabaseAt: databaseURL)

        let acquired = DispatchSemaphore(value: 0)
        let secondIsWaiting = DispatchSemaphore(value: 0)
        DispatchQueue.global().async {
            secondIsWaiting.signal()
            let second = MigrationGate(besideDatabaseAt: self.databaseURL)
            acquired.signal()
            second.release()
        }

        secondIsWaiting.wait()
        // Not a claim about how long the wait lasts — that would be a flake. The claim is only that
        // the gate has *not* been taken while the first holder still has it, which is true however
        // slow the machine is.
        XCTAssertEqual(acquired.wait(timeout: .now() + 0.5), .timedOut,
                       "a second holder took the gate while the first still held it")

        first.release()
        XCTAssertEqual(acquired.wait(timeout: .now() + 5), .success,
                       "releasing the gate did not let the waiting holder through")
    }

    /// Collects what the racing threads threw. A plain array would be the data race the test is
    /// about.
    private final class Failures: @unchecked Sendable {
        private let lock = NSLock()
        private var stored: [String] = []

        func record(_ error: Error) {
            lock.lock()
            defer { lock.unlock() }
            stored.append("\(error)")
        }

        var messages: [String] {
            lock.lock()
            defer { lock.unlock() }
            return stored
        }
    }

    // MARK: - Reaching past the store

    /// Deletes ledger rows on a connection of its own, so the store under test is untouched.
    private func forgetMigrations(_ identifiers: [String]) throws {
        let queue = try DatabaseQueue(path: databaseURL.path)
        try queue.write { db in
            for identifier in identifiers {
                try db.execute(
                    sql: "DELETE FROM grdb_migrations WHERE identifier = ?", arguments: [identifier])
            }
        }
    }

    /// Puts the schema genuinely behind this binary, so the reader has something real to refuse.
    private func dropColumn(_ column: String, from table: String) throws {
        let queue = try DatabaseQueue(path: databaseURL.path)
        try queue.write { db in
            try db.execute(sql: "ALTER TABLE \(table) DROP COLUMN \(column)")
        }
    }

    private func ledger() throws -> Set<String> {
        let queue = try DatabaseQueue(path: databaseURL.path)
        return try queue.read { db in
            Set(try String.fetchAll(db, sql: "SELECT identifier FROM grdb_migrations"))
        }
    }

    private func indexExists(_ name: String) throws -> Bool {
        let queue = try DatabaseQueue(path: databaseURL.path)
        return try queue.read { db in
            try Int.fetchOne(
                db,
                sql: "SELECT COUNT(*) FROM sqlite_master WHERE type = 'index' AND name = ?",
                arguments: [name]) == 1
        }
    }

    private func columnExists(_ column: String, in table: String) throws -> Bool {
        let queue = try DatabaseQueue(path: databaseURL.path)
        return try queue.read { db in
            try db.columns(in: table).contains { $0.name == column }
        }
    }
}
