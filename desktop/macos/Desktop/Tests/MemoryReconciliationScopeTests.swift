import XCTest
@testable import Omi_Computer

final class MemoryReconciliationScopeTests: XCTestCase {
    private var testUserId: String!
    private var userDir: URL!

    override func setUp() async throws {
        try await super.setUp()
        testUserId = "memory-reconcile-scope-\(UUID().uuidString)"
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
        let short = makeMemory(id: "short-1", tier: .shortTerm)
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

    private func makeMemory(id: String, tier: MemoryTier) -> ServerMemory {
        ServerMemory(
            id: id,
            content: "Memory \(id)",
            category: .system,
            tier: tier,
            createdAt: Date(timeIntervalSince1970: 1),
            updatedAt: Date(timeIntervalSince1970: 2),
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
