import GRDB
import XCTest
@testable import Omi_Computer

final class MemoryAuthoritativeTierSyncTests: XCTestCase {
    private var testUserId: String!
    private var userDir: URL!

    override func setUp() async throws {
        try await super.setUp()
        testUserId = "memory-tier-sync-\(UUID().uuidString)"
        RewindDatabase.currentUserId = testUserId
        await MemoryStorage.shared.invalidateCache()
        try await RewindDatabase.shared.initialize()

        let appSupport = FileManager.default
            .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        userDir = appSupport
            .appendingPathComponent("Omi", isDirectory: true)
            .appendingPathComponent("users", isDirectory: true)
            .appendingPathComponent(testUserId, isDirectory: true)
    }

    override func tearDown() async throws {
        await MemoryStorage.shared.invalidateCache()
        if let userDir { try? FileManager.default.removeItem(at: userDir) }
        RewindDatabase.currentUserId = nil
        try await super.tearDown()
    }

    func testSyncMergesAuthoritativeTierWhenLocalUpdatedAtIsNewer() async throws {
        let backendId = "tier-sync-explicit-\(UUID().uuidString)"
        let serverUpdatedAt = Date(timeIntervalSince1970: 1_000)
        let localUpdatedAt = Date(timeIntervalSince1970: 2_000)

        let serverMemory = makeMemory(
            id: backendId,
            tier: .shortTerm,
            tierIsExplicit: true,
            updatedAt: serverUpdatedAt
        )
        try await MemoryStorage.shared.syncServerMemories([serverMemory])

        try await corruptLocalTier(
            backendId: backendId,
            tier: MemoryLayer.longTerm.rawValue,
            tierIsExplicit: false,
            updatedAt: localUpdatedAt
        )

        try await MemoryStorage.shared.syncServerMemories([serverMemory])

        let record = try await MemoryStorage.shared.getMemoryByBackendId(backendId)
        XCTAssertEqual(record?.tier, MemoryLayer.shortTerm.rawValue)
        XCTAssertEqual(record?.tierIsExplicit, true)
        XCTAssertEqual(record?.content, serverMemory.content, "Newer local row must keep its content")
        XCTAssertEqual(record?.updatedAt, localUpdatedAt, "Tier merge must not bump updatedAt")
    }

    func testSyncLeavesLegacyUntieredLocalRecordBadgeLess() async throws {
        let backendId = "tier-sync-legacy-\(UUID().uuidString)"
        let serverUpdatedAt = Date(timeIntervalSince1970: 1_000)
        let localUpdatedAt = Date(timeIntervalSince1970: 2_000)

        let legacyServerMemory = makeMemory(
            id: backendId,
            tier: .longTerm,
            tierIsExplicit: false,
            updatedAt: serverUpdatedAt
        )
        try await MemoryStorage.shared.syncServerMemories([legacyServerMemory])

        try await corruptLocalTier(
            backendId: backendId,
            tier: MemoryLayer.shortTerm.rawValue,
            tierIsExplicit: false,
            updatedAt: localUpdatedAt
        )

        try await MemoryStorage.shared.syncServerMemories([legacyServerMemory])

        let record = try await MemoryStorage.shared.getMemoryByBackendId(backendId)
        XCTAssertEqual(record?.tier, MemoryLayer.shortTerm.rawValue, "Local tier value is preserved")
        XCTAssertEqual(record?.tierIsExplicit, false, "Legacy server rows must not force a badge")
    }

    func testMarkSyncedDoesNotBumpUpdatedAt() async throws {
        let backendId = "tier-sync-mark-\(UUID().uuidString)"
        let createdAt = Date(timeIntervalSince1970: 500)
        let updatedAt = Date(timeIntervalSince1970: 600)

        let local = MemoryRecord(
            backendSynced: false,
            content: "Local-first memory",
            createdAt: createdAt,
            updatedAt: updatedAt
        )
        let inserted = try await MemoryStorage.shared.insertLocalMemory(local)
        guard let recordId = inserted.id else {
            XCTFail("Expected inserted local memory id")
            return
        }

        try await MemoryStorage.shared.markSynced(id: recordId, backendId: backendId)

        let record = try await MemoryStorage.shared.getMemoryByBackendId(backendId)
        XCTAssertEqual(record?.updatedAt, updatedAt)
        XCTAssertEqual(record?.tierIsExplicit, false)
    }

    private func corruptLocalTier(
        backendId: String,
        tier: String,
        tierIsExplicit: Bool,
        updatedAt: Date
    ) async throws {
        guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
            XCTFail("Database queue unavailable")
            return
        }

        try await dbQueue.write { database in
            guard var record = try MemoryRecord
                .filter(Column("backendId") == backendId)
                .fetchOne(database) else {
                XCTFail("Expected memory row for backendId \(backendId)")
                return
            }
            record.tier = tier
            record.tierIsExplicit = tierIsExplicit
            record.updatedAt = updatedAt
            try record.update(database)
        }
    }

    private func makeMemory(
        id: String,
        tier: MemoryLayer,
        tierIsExplicit: Bool,
        updatedAt: Date
    ) -> ServerMemory {
        ServerMemory(
            id: id,
            content: "Memory \(id)",
            category: .system,
            tier: tier,
            tierIsExplicit: tierIsExplicit,
            createdAt: Date(timeIntervalSince1970: 1),
            updatedAt: updatedAt,
            conversationId: nil,
            reviewed: false,
            userReview: nil,
            visibility: "private",
            manuallyAdded: false,
            scoring: nil,
            source: "desktop",
            confidence: nil,
            sourceApp: nil,
            contextSummary: nil,
            isRead: false,
            isDismissed: false,
            tags: [],
            reasoning: nil,
            currentActivity: nil,
            inputDeviceName: nil,
            windowTitle: nil,
            headline: nil
        )
    }
}
