import XCTest
@testable import Omi_Computer

final class MemoryReconciliationScopeTests: XCTestCase {
    private var testUserId: String!
    private var userDir: URL!

    override func setUp() async throws {
        try await super.setUp()
        let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memory-reconcile-scope")
        testUserId = fixture.testUserId
        userDir = fixture.userDir
    }

    override func tearDown() async throws {
        await RewindStorageTestIsolation.tearDown(userDir: userDir)
        try await super.tearDown()
    }

    func testDefaultScopeReconcilePreservesArchiveRows() async throws {
        let short = makeMemory(id: "short-1", tier: .shortTerm)
        let long = makeMemory(id: "long-1", tier: .longTerm)
        let archive = makeMemory(id: "archive-1", tier: .archive)

        try await MemoryStorage.shared.syncServerMemories([short, long, archive])

        let removed = try await MemoryStorage.shared.softDeleteSyncedOrphans(
            keepingBackendIds: ["short-1", "long-1"],
            within: .defaultAccess
        )

        XCTAssertEqual(removed, 0)
        let archiveRecord = try await MemoryStorage.shared.getMemoryByBackendId("archive-1")
        XCTAssertEqual(archiveRecord?.deleted, false)
    }

    func testDefaultScopeReconcileDeletesOnlyAbsentDefaultScopeRows() async throws {
        let shortKept = makeMemory(id: "short-kept", tier: .shortTerm)
        let longDeleted = makeMemory(id: "long-deleted", tier: .longTerm)
        let archivePreserved = makeMemory(id: "archive-preserved", tier: .archive)

        try await MemoryStorage.shared.syncServerMemories([shortKept, longDeleted, archivePreserved])

        let removed = try await MemoryStorage.shared.softDeleteSyncedOrphans(
            keepingBackendIds: ["short-kept"],
            within: .defaultAccess
        )

        XCTAssertEqual(removed, 1)
        let shortRecord = try await MemoryStorage.shared.getMemoryByBackendId("short-kept")
        let longRecord = try await MemoryStorage.shared.getMemoryByBackendId("long-deleted")
        let archiveRecord = try await MemoryStorage.shared.getMemoryByBackendId("archive-preserved")
        XCTAssertEqual(shortRecord?.deleted, false)
        XCTAssertEqual(longRecord?.deleted, true)
        XCTAssertEqual(archiveRecord?.deleted, false)
    }

    func testArchiveScopeReconcileDeletesOnlyAbsentArchiveRows() async throws {
        let short = makeMemory(id: "short-1", tier: .longTerm)
        let long = makeMemory(id: "long-1", tier: .longTerm)
        let archiveDeleted = makeMemory(id: "archive-deleted", tier: .archive)
        let archiveKept = makeMemory(id: "archive-kept", tier: .archive)

        try await MemoryStorage.shared.syncServerMemories([short, long, archiveDeleted, archiveKept])

        let removed = try await MemoryStorage.shared.softDeleteSyncedOrphans(
            keepingBackendIds: ["archive-kept"],
            within: .archiveOnly
        )

        XCTAssertEqual(removed, 1)
        let shortRecord = try await MemoryStorage.shared.getMemoryByBackendId("short-1")
        let longRecord = try await MemoryStorage.shared.getMemoryByBackendId("long-1")
        let archiveDeletedRecord = try await MemoryStorage.shared.getMemoryByBackendId("archive-deleted")
        let archiveKeptRecord = try await MemoryStorage.shared.getMemoryByBackendId("archive-kept")
        XCTAssertEqual(shortRecord?.deleted, false)
        XCTAssertEqual(longRecord?.deleted, false)
        XCTAssertEqual(archiveDeletedRecord?.deleted, true)
        XCTAssertEqual(archiveKeptRecord?.deleted, false)
    }

    func testSyncAndPruneAbsentRemovesPromotedOrphanWithoutConversationId() async throws {
        // Promoted memory: server projection dropped conversation_id, but local row lingers
        // after the source conversation is cascade-deleted server-side.
        let promotedOrphan = makeMemory(id: "promoted-orphan", tier: .longTerm, conversationId: nil)
        let kept = makeMemory(id: "kept-memory", tier: .longTerm, conversationId: nil)

        try await MemoryStorage.shared.syncServerMemories([promotedOrphan, kept])

        let pruned = try await MemoryStorage.shared.syncServerMemoriesAndPruneAbsent(
            [kept],
            within: .defaultAccess
        )

        XCTAssertEqual(pruned, 1)
        let orphanRecord = try await MemoryStorage.shared.getMemoryByBackendId("promoted-orphan")
        let keptRecord = try await MemoryStorage.shared.getMemoryByBackendId("kept-memory")
        XCTAssertEqual(orphanRecord?.deleted, true)
        XCTAssertEqual(keptRecord?.deleted, false)
    }

    private func makeMemory(id: String, tier: MemoryLayer, conversationId: String? = nil) -> ServerMemory {
        ServerMemory(
            id: id,
            content: "Memory \(id)",
            category: .system,
            tier: tier,
            createdAt: Date(timeIntervalSince1970: 1),
            updatedAt: Date(timeIntervalSince1970: 2),
            conversationId: conversationId,
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
