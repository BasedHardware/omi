import Foundation
import GRDB
import XCTest
@testable import ContextCore

final class OmiMemoryStoreTests: XCTestCase {
    func testDatabasePoolFollowsTheCurrentOwner() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("omi-memory-store-tests-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let first = root.appendingPathComponent("first.db")
        let second = root.appendingPathComponent("second.db")
        try makeDatabase(at: first, content: "account-a")
        try makeDatabase(at: second, content: "account-b")

        var current: URL? = first
        let store = OmiMemoryStore(databaseURLProvider: { current })

        XCTAssertEqual(store.searchMemories(query: "account", limit: 10).map(\.content), ["account-a"])
        current = second
        XCTAssertEqual(store.searchMemories(query: "account", limit: 10).map(\.content), ["account-b"])
        current = nil
        XCTAssertFalse(store.isAvailable)
        XCTAssertTrue(store.searchMemories(query: "account", limit: 10).isEmpty)
    }

    private func makeDatabase(at url: URL, content: String) throws {
        let queue = try DatabaseQueue(path: url.path)
        try queue.write { db in
            try db.execute(sql: """
                CREATE TABLE memories (
                    id INTEGER PRIMARY KEY,
                    backendId TEXT,
                    content TEXT NOT NULL,
                    category TEXT,
                    deleted INTEGER NOT NULL,
                    isDismissed INTEGER NOT NULL,
                    createdAt REAL NOT NULL
                )
                """)
            try db.execute(
                sql: """
                INSERT INTO memories (backendId, content, category, deleted, isDismissed, createdAt)
                VALUES (?, ?, ?, 0, 0, ?)
                """,
                arguments: [nil, content, "test", 1.0])
        }
    }
}
