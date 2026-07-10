import AppKit
import XCTest
@testable import Omi_Computer

/// Tests for `MemoriesViewModel` auto-refresh observer wiring (#6500).
///
/// After replacing the 30-second `Timer.publish` with `didBecomeActive` +
/// `.refreshAllData` subscribers, the view model must still refresh when
/// those notifications fire. Because `MemoriesViewModel` is not a singleton,
/// each test constructs a fresh instance (triggering `init()` which registers
/// the two subscribers into its private `cancellables`) and asserts that
/// posting each notification advances `refreshInvocations` by one.
@MainActor
final class MemoriesViewModelObserverTests: XCTestCase {
    private var testUserId: String!
    private var userDir: URL!
    private var authSnapshot: RewindStorageTestIsolation.AuthSnapshot!

    override func setUp() async throws {
        try await super.setUp()
        authSnapshot = RewindStorageTestIsolation.captureAuthSnapshot()
        let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memories-vm-observer")
        testUserId = fixture.testUserId
        userDir = fixture.userDir
        RewindStorageTestIsolation.signInForTests(userId: testUserId)
    }

    override func tearDown() async throws {
        RewindStorageTestIsolation.restoreAuthSnapshot(authSnapshot)
        await RewindStorageTestIsolation.tearDown(userDir: userDir)
        try await super.tearDown()
    }

    func testDidBecomeActiveNotificationTriggersRefresh() async {
        let viewModel = MemoriesViewModel()
        XCTAssertEqual(viewModel.refreshInvocations, 0, "Fresh instance must start at zero")

        NotificationCenter.default.post(
            name: NSApplication.didBecomeActiveNotification, object: nil
        )
        await Task.yield()
        try? await Task.sleep(nanoseconds: 50_000_000)

        XCTAssertEqual(
            viewModel.refreshInvocations, 1,
            "didBecomeActive must route to refreshMemoriesIfNeeded() via the activation subscriber"
        )
    }

    func testRefreshAllDataNotificationTriggersRefresh() async {
        let viewModel = MemoriesViewModel()

        NotificationCenter.default.post(name: .refreshAllData, object: nil)
        await Task.yield()
        try? await Task.sleep(nanoseconds: 50_000_000)

        XCTAssertEqual(
            viewModel.refreshInvocations, 1,
            ".refreshAllData (Cmd+R) must route to refreshMemoriesIfNeeded() via the refresh subscriber"
        )
    }

    func testConversationDeletedNotificationTriggersCascadeHandler() async throws {
        let conversationId = "conv-cascade-test"
        let linkedMemory = makeMemory(id: "mem-linked", conversationId: conversationId)
        let otherMemory = makeMemory(id: "mem-other", conversationId: "conv-keep")

        try await MemoryStorage.shared.syncServerMemories([linkedMemory, otherMemory])

        let viewModel = MemoriesViewModel()
        let cached = try await MemoryStorage.shared.getLocalMemories(limit: 50, offset: 0)
        viewModel.memories = cached
        XCTAssertTrue(viewModel.memories.contains { $0.conversationId == conversationId })

        NotificationCenter.default.post(
            name: .conversationDeleted,
            object: nil,
            userInfo: ["conversationId": conversationId]
        )
        await Task.yield()
        try? await Task.sleep(nanoseconds: 200_000_000)

        XCTAssertEqual(
            viewModel.conversationDeleteInvocations, 1,
            ".conversationDeleted must route to handleConversationDeleted() via the cascade subscriber"
        )
        XCTAssertFalse(
            viewModel.memories.contains { $0.conversationId == conversationId },
            "In-memory cache must drop memories for the deleted conversation"
        )
        XCTAssertTrue(
            viewModel.memories.contains { $0.id == otherMemory.id },
            "Unrelated memories must remain after cascade"
        )

        let linkedRecord = try await MemoryStorage.shared.getMemoryByBackendId(linkedMemory.id)
        XCTAssertEqual(linkedRecord?.deleted, true, "SQLite must soft-delete conversation-linked rows")
        let otherRecord = try await MemoryStorage.shared.getMemoryByBackendId(otherMemory.id)
        XCTAssertEqual(otherRecord?.deleted, false, "Unrelated SQLite rows must stay active")
    }

    func testDeallocatedViewModelDoesNotLeakObservers() async {
        // Ensures the `[weak self]` capture in the Combine sinks lets the
        // view model deallocate cleanly — no crash when the notifications
        // fire after the instance is gone.
        do {
            let viewModel = MemoriesViewModel()
            XCTAssertEqual(viewModel.refreshInvocations, 0)
        }
        // viewModel is out of scope and should be deallocated.
        NotificationCenter.default.post(
            name: NSApplication.didBecomeActiveNotification, object: nil
        )
        NotificationCenter.default.post(name: .refreshAllData, object: nil)
        await Task.yield()
        try? await Task.sleep(nanoseconds: 50_000_000)
        // If the weak capture misbehaved we'd crash above; reaching here is the assertion.
    }

    private func makeMemory(id: String, conversationId: String?) -> ServerMemory {
        ServerMemory(
            id: id,
            content: "Memory \(id)",
            category: .system,
            tier: .shortTerm,
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
