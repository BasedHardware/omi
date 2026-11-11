import Foundation
import GRDB
import XCTest

@testable import ContextCore

/// Who each queued session is owed to, and what happens to one that never said.
///
/// The queue scopes work to the signed-in account, which is right: an un-uploaded backlog captured
/// while one person was signed in must never land in the next person's account. But the column that
/// records the account was only ever written by `markPending`. `reconcile` — the path that exists
/// precisely to rescue sessions nothing else enqueued — inserted rows without it, and `pending`
/// filters on it, so every session reconciliation "rescued" became invisible to the only query the
/// drain takes work from. On the machine this was found on that was 22 sessions and 2,043 transcript
/// lines, `attempts = 0`, never once tried.
///
/// It was silent because the two numbers disagreed about what the queue held: `pendingCount` counted
/// every queued row and the drain read only the owner's, so the UI reported "22 conversations waiting
/// to upload" forever while nothing could ever pick one up, and `lastError` stayed nil because
/// nothing ever failed. So these tests assert both halves — that the work is reachable, *and* that
/// the count is the same set the drain would act on. A queue that lies about its size can hide this
/// bug again.
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

    private var store: ContextStore { fixture.store }

    private let owner = "owner-a"
    private let otherOwner = "owner-b"

    // MARK: - Helpers

    /// A closed session, which is the only kind either enqueue path considers.
    @discardableResult
    private func closedSession(at startedAt: Double) throws -> Int64 {
        let id = try store.openSession(at: startedAt, appHint: nil)
        try store.closeSession(id, at: startedAt + 60)
        return id
    }

    /// Arms reconciliation to look at everything. The watermark is set to "now" on first run so that
    /// installing the app never uploads a month of history, and a test that skipped this step would
    /// pass against a queue that simply examined nothing.
    private func armReconcile(from: Double) throws {
        try UploadQueue.setTimestamp(store, .reconcileWatermark, from)
    }

    // MARK: - Reconciliation

    /// The regression. A session reconciliation finds on disk has to be work the drain can see —
    /// being in the `uploads` table is not the same as being uploadable, and the gap between those
    /// two is where 2,043 lines sat.
    func testReconciledSessionIsDrainableByTheSignedInOwner() throws {
        let sessionId = try closedSession(at: Fixture.base)
        try armReconcile(from: Fixture.base - 1)

        XCTAssertEqual(try UploadQueue.reconcile(store, ownerId: owner), 1)

        let due = try UploadQueue.pending(store, ownerId: owner, dueAt: Fixture.base + 3600)
        XCTAssertEqual(due.map(\.sessionId), [sessionId])
        XCTAssertEqual(try UploadQueue.pendingCount(store, ownerId: owner), 1)
    }

    /// Reconciling while signed out is not a mistake — capture keeps happening and the queue is
    /// meant to outlive being signed in. What must not happen is the row silently belonging to
    /// whoever the last query asked about.
    func testReconciledWhileSignedOutIsNotSomebodyElsesWork() throws {
        try closedSession(at: Fixture.base)
        try armReconcile(from: Fixture.base - 1)

        XCTAssertEqual(try UploadQueue.reconcile(store, ownerId: nil), 1)

        XCTAssertEqual(try UploadQueue.pending(store, ownerId: owner, dueAt: Fixture.base + 3600), [])
        XCTAssertEqual(try UploadQueue.pendingCount(store, ownerId: owner), 0)
        // Still real work, and still counted while nobody is signed in — a backlog the user cannot
        // see is how this bug hid for two weeks.
        XCTAssertEqual(try UploadQueue.pendingCount(store, ownerId: nil), 1)
    }

    /// Signing out must not make an account's own backlog disappear from the menu bar. With no
    /// account in the app, everything queued is waiting on the same thing — a sign-in — so that is
    /// what the count reports.
    func testSignedOutCountsEverythingStillWaitingOnASignIn() throws {
        let theirs = try closedSession(at: Fixture.base)
        let unattributed = try closedSession(at: Fixture.base + 3600)
        try UploadQueue.markPending(store, sessionId: theirs, ownerId: otherOwner)
        try UploadQueue.markPending(store, sessionId: unattributed, ownerId: nil)

        XCTAssertEqual(try UploadQueue.pendingCount(store, ownerId: nil), 2)
    }

    // MARK: - Isolation

    /// The property the owner column was added for. Another account's backlog is not this account's
    /// work, and — the half that was missing — it is not this account's *number* either.
    func testAnotherOwnersQueueYieldsNoWorkAndNoCount() throws {
        let sessionId = try closedSession(at: Fixture.base)
        try UploadQueue.markPending(store, sessionId: sessionId, ownerId: otherOwner)

        XCTAssertEqual(try UploadQueue.pending(store, ownerId: owner, dueAt: Fixture.base + 3600), [])
        XCTAssertEqual(try UploadQueue.pendingCount(store, ownerId: owner), 0)
        XCTAssertNil(try UploadQueue.nextDueAt(store, ownerId: owner))
        // And it is still owed to the account that captured it.
        XCTAssertEqual(try UploadQueue.pendingCount(store, ownerId: otherOwner), 1)
    }

    // MARK: - Claiming

    /// Sessions captured before signing in are parked, not dropped — and on a Mac that has only ever
    /// worked for one account there is no second account for them to leak to, so signing in claims
    /// them.
    func testSigningInClaimsWorkQueuedWithNoOwner() throws {
        let signedOut = try closedSession(at: Fixture.base)
        let signedIn = try closedSession(at: Fixture.base + 3600)
        try UploadQueue.markPending(store, sessionId: signedOut, ownerId: nil)
        try UploadQueue.markPending(store, sessionId: signedIn, ownerId: owner)

        XCTAssertEqual(try UploadQueue.claimOrphans(store, ownerId: owner), .claimed(1))

        let due = try UploadQueue.pending(store, ownerId: owner, dueAt: Fixture.base + 7200)
        XCTAssertEqual(Set(due.map(\.sessionId)), [signedOut, signedIn])
        XCTAssertEqual(try UploadQueue.pendingCount(store, ownerId: owner), 2)
    }

    /// The case worth being slow about. Once this Mac has worked for two accounts, an unattributed
    /// row could have been captured by either, and nothing in the schema records which — `sessions`
    /// holds a start, an end and an app hint, and no owner. Refusing costs an upload; guessing would
    /// put one person's conversations in another person's account.
    func testClaimingIsRefusedOnceASecondAccountHasUsedThisMac() throws {
        let unattributed = try closedSession(at: Fixture.base)
        let theirs = try closedSession(at: Fixture.base + 3600)
        try UploadQueue.markPending(store, sessionId: unattributed, ownerId: nil)
        try UploadQueue.markPending(store, sessionId: theirs, ownerId: otherOwner)

        XCTAssertEqual(try UploadQueue.claimOrphans(store, ownerId: owner), .refusedForeignOwner)

        XCTAssertEqual(try UploadQueue.pending(store, ownerId: owner, dueAt: Fixture.base + 7200), [])
        XCTAssertEqual(try UploadQueue.pendingCount(store, ownerId: owner), 0)
    }

    /// Claiming settles who owes what; it does not reopen anything. A session already in the account
    /// must not become work again just because a row beside it was unattributed.
    func testClaimingLeavesFinishedSessionsAlone() throws {
        let done = try closedSession(at: Fixture.base)
        let queued = try closedSession(at: Fixture.base + 3600)
        try UploadQueue.markPending(store, sessionId: done, ownerId: nil)
        try UploadQueue.markUploaded(store, sessionId: done, conversationIds: ["conv-1"])
        try UploadQueue.markPending(store, sessionId: queued, ownerId: nil)

        XCTAssertEqual(try UploadQueue.claimOrphans(store, ownerId: owner), .claimed(1))

        XCTAssertEqual(try UploadQueue.entry(store, sessionId: done)?.state, .uploaded)
        XCTAssertEqual(
            try UploadQueue.pending(store, ownerId: owner, dueAt: Fixture.base + 7200).map(\.sessionId),
            [queued])
    }

    // MARK: - What the spine reads

    /// The read the Activity panel composes from, and it answers two questions at once: which
    /// account conversation a session became, and — the half that was missing — whether a session
    /// with no conversation yet is still *owed* to an account.
    ///
    /// Without the second half the panel could not tell a session waiting on an upload from a
    /// session nobody is ever going to upload, so it drew both as `Untitled conversation`. A blocked
    /// queue then buried the day's real titles under placeholders for conversations the account was
    /// about to name.
    func testConversationLinksSeparatesLinkedFromStillOwedFromLocal() throws {
        let linked = try closedSession(at: Fixture.base)
        let owed = try closedSession(at: Fixture.base + 3600)
        let parked = try closedSession(at: Fixture.base + 7200)
        let nothingToUpload = try closedSession(at: Fixture.base + 10800)
        let neverQueued = try closedSession(at: Fixture.base + 14400)

        try UploadQueue.markPending(store, sessionId: linked, ownerId: owner)
        try UploadQueue.markUploaded(store, sessionId: linked, conversationIds: ["c1", "c2"])
        try UploadQueue.markPending(store, sessionId: owed, ownerId: owner)
        // Captured while signed out: parked rather than owed to anybody, so nothing is coming for it
        // until a sign-in claims it.
        try UploadQueue.markPending(store, sessionId: parked, ownerId: nil)
        try UploadQueue.markPending(store, sessionId: nothingToUpload, ownerId: owner)
        try UploadQueue.markSkipped(store, sessionId: nothingToUpload, reason: "no transcript")

        let links = try UploadQueue.conversationLinks(store)

        XCTAssertEqual(links[linked], ["c1", "c2"], "the ids the backend handed back, in order")
        XCTAssertEqual(links[owed], [], "held for an account, nothing back yet")
        XCTAssertNil(links[parked], "nobody is going to upload this one")
        XCTAssertNil(links[nothingToUpload], "terminal with nothing in the account to point at")
        XCTAssertNil(links[neverQueued], "the queue has never heard of it")
    }

    /// A session that reached the account and was then given up on is still the same talk as the
    /// conversation it became — the link outlives the entry's state, or the panel draws that
    /// conversation twice.
    func testConversationLinksKeepsTheLinkOfASkippedSessionThatAlreadyUploadedAPart() throws {
        let sessionId = try closedSession(at: Fixture.base)
        try UploadQueue.markPending(store, sessionId: sessionId, ownerId: owner)
        try UploadQueue.markPartUploaded(
            store, sessionId: sessionId, partsDone: 1, conversationId: "c1")
        try UploadQueue.markSkipped(store, sessionId: sessionId, reason: "rest rejected")

        XCTAssertEqual(try UploadQueue.conversationLinks(store)[sessionId], ["c1"])
    }

    // MARK: - The count and the drain

    /// The invariant that makes the next bug of this shape visible instead of silent: whatever
    /// `pendingCount` reports, the drain has to be able to reach it. Here the queue holds one entry
    /// per owner plus one nobody claimed, and each owner is told only about their own.
    func testCountIsTheSameSetTheDrainWouldAct() throws {
        let mine = try closedSession(at: Fixture.base)
        let theirs = try closedSession(at: Fixture.base + 3600)
        let unattributed = try closedSession(at: Fixture.base + 7200)
        try UploadQueue.markPending(store, sessionId: mine, ownerId: owner)
        try UploadQueue.markPending(store, sessionId: theirs, ownerId: otherOwner)
        try UploadQueue.markPending(store, sessionId: unattributed, ownerId: nil)

        for candidate in [owner, otherOwner] {
            let drainable = try UploadQueue.pending(store, ownerId: candidate, dueAt: Fixture.base + 10800)
            XCTAssertEqual(
                drainable.count, try UploadQueue.pendingCount(store, ownerId: candidate),
                "\(candidate) is told about work it cannot drain")
        }
    }
}
