import XCTest

@testable import Omi_Computer

final class ActionItemStorageVisibilityReconciliationTests: XCTestCase {
    private var testUserId: String!
    private var userDir: URL!

    override func setUp() async throws {
        try await super.setUp()

        testUserId = "visibility-reconcile-test-\(UUID().uuidString)"
        try await RewindDatabase.shared.switchUser(to: testUserId)
        await ActionItemStorage.shared.invalidateCache()

        let appSupport = FileManager.default
            .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        userDir = appSupport
            .appendingPathComponent("Omi", isDirectory: true)
            .appendingPathComponent("users", isDirectory: true)
            .appendingPathComponent(testUserId, isDirectory: true)
    }

    override func tearDown() async throws {
        await ActionItemStorage.shared.invalidateCache()
        await RewindDatabase.shared.close()
        if let userDir { try? FileManager.default.removeItem(at: userDir) }
        RewindDatabase.currentUserId = nil
        try await super.tearDown()
    }

    func testVisibilityReconciliationBypassesRecentLocalChangeGuardWithoutOverwritingDescriptionOrDueDateEdit() async throws {
        let originalDueAt = Date(timeIntervalSince1970: 1_750_000_000)
        let serverDueAt = Date(timeIntervalSince1970: 1_750_086_400)
        let createdAt = Date(timeIntervalSince1970: 1_749_900_000)
        let staleServerUpdatedAt = Date(timeIntervalSince1970: 1_749_950_000)

        try await ActionItemStorage.shared.syncTaskActionItems([
            task(
                id: "backend-task-1",
                description: "local description must survive",
                completed: false,
                deleted: false,
                createdAt: createdAt,
                updatedAt: staleServerUpdatedAt,
                dueAt: originalDueAt
            )
        ])

        // Local optimistic field updates mutate updatedAt to now, putting the row
        // inside the existing 60s optimistic-update protection window. A normal
        // sync with older server timestamps must not update the record.
        try await ActionItemStorage.shared.updateActionItemFields(
            backendId: "backend-task-1",
            description: "local description must survive",
            dueAt: originalDueAt
        )

        let authoritativeServerItem = task(
            id: "backend-task-1",
            description: "server description must not overwrite local text",
            completed: true,
            deleted: true,
            createdAt: createdAt,
            updatedAt: staleServerUpdatedAt,
            dueAt: serverDueAt
        )
        try await ActionItemStorage.shared.syncTaskActionItems([authoritativeServerItem])
        let afterNormalSyncItem = try await ActionItemStorage.shared.getLocalActionItem(
            byBackendId: "backend-task-1"
        )
        let afterNormalSync = try XCTUnwrap(afterNormalSyncItem)
        XCTAssertFalse(afterNormalSync.completed, "precondition: normal sync is still guarded")
        XCTAssertEqual(afterNormalSync.dueAt, originalDueAt, "precondition: due date is still guarded")

        let reconciled = try await ActionItemStorage.shared.reconcileDashboardVisibilityFields([
            authoritativeServerItem
        ])

        XCTAssertEqual(reconciled, 1)
        let refreshedItem = try await ActionItemStorage.shared.getLocalActionItem(
            byBackendId: "backend-task-1"
        )
        let refreshed = try XCTUnwrap(refreshedItem)
        XCTAssertTrue(refreshed.completed)
        XCTAssertEqual(refreshed.deleted, true)
        XCTAssertEqual(refreshed.dueAt, originalDueAt)
        XCTAssertEqual(refreshed.description, "local description must survive")
    }

    private func task(
        id: String,
        description: String,
        completed: Bool,
        deleted: Bool,
        createdAt: Date,
        updatedAt: Date,
        dueAt: Date?
    ) -> TaskActionItem {
        TaskActionItem(
            id: id,
            description: description,
            completed: completed,
            createdAt: createdAt,
            updatedAt: updatedAt,
            dueAt: dueAt,
            deleted: deleted
        )
    }
}
