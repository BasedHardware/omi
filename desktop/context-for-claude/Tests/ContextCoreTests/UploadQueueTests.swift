import ContextCore
import XCTest

final class UploadQueueTests: XCTestCase {
    private var fixture: Fixture!

    override func setUpWithError() throws {
        fixture = try Fixture(seeded: false)
        try UploadQueue.prepare(fixture.store)
    }

    override func tearDownWithError() throws {
        fixture?.tearDown()
        fixture = nil
    }

    func testReconcileClaimsSignedOutQueueForSignedInOwner() throws {
        let sessionId = try fixture.store.openSession(at: Fixture.base, appHint: nil)
        try fixture.store.closeSession(sessionId, at: Fixture.base + 10)
        try UploadQueue.markPending(fixture.store, sessionId: sessionId)

        XCTAssertTrue(try UploadQueue.pending(fixture.store, ownerId: "user-a").isEmpty)
        XCTAssertEqual(try UploadQueue.reconcile(fixture.store, ownerId: "user-a"), 0)
        XCTAssertEqual(try UploadQueue.pending(fixture.store, ownerId: "user-a").map(\.sessionId), [sessionId])
    }

    func testQueueCountsAndWakeupsAreOwnerScoped() throws {
        let first = try fixture.store.openSession(at: Fixture.base, appHint: nil)
        let second = try fixture.store.openSession(at: Fixture.base + 20, appHint: nil)
        try fixture.store.closeSession(first, at: Fixture.base + 10)
        try fixture.store.closeSession(second, at: Fixture.base + 30)
        try UploadQueue.markPending(fixture.store, sessionId: first, ownerId: "user-a")
        try UploadQueue.markPending(fixture.store, sessionId: second, ownerId: "user-b")

        XCTAssertEqual(try UploadQueue.pendingCount(fixture.store, ownerId: "user-a"), 1)
        XCTAssertEqual(try UploadQueue.pendingCount(fixture.store, ownerId: "user-b"), 1)
        XCTAssertEqual(try UploadQueue.nextDueAt(fixture.store, ownerId: "user-a"), 0)
        XCTAssertNil(try UploadQueue.nextDueAt(fixture.store, ownerId: nil))
    }
}
