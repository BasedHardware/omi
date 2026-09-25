import ContextCore
import Foundation
import XCTest

@testable import ContextApp

/// The paint before the network, and the one thing it is never allowed to do.
///
/// **What this is a regression test for.** The Activity spine's account half was network-only, so a
/// cold launch composed the local sessions `context.db` holds and nothing else — every one drawn as
/// `ActivityConversation.untitled`, because a title is written by the backend when a transcript is
/// uploaded. The user watched a column of `Untitled conversation` become real titles a second or
/// two later, every launch. The shipping Omi app does not look like that over the same data because
/// `ConversationRepository.load` reads SQLite, emits, and *then* fetches.
///
/// The danger in copying that arrangement is not staleness — a stale row is replaced by the next
/// read and nobody is harmed. It is a cache that starts *speaking for the account*: claiming a
/// source answered, claiming the account is reachable, settling a corpus. Every one of those is a
/// sentence the panel says out loud, and none of them may be said on the strength of a copy. Most of
/// what follows is that boundary.
final class ActivityAccountCacheTests: XCTestCase {

    private var root: URL!
    private var store: ContextStore!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("activity-cache-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        store = try ContextStore(url: root.appendingPathComponent("context.db"))
        let store = self.store!
        cache = ActivityAccountCache(store: { store })
    }

    override func tearDown() {
        cache = nil
        store = nil
        try? FileManager.default.removeItem(at: root)
        root = nil
    }

    /// One actor per test, held rather than rebuilt on each access: the epoch that fences writes
    /// against a sign-out lives *in* the actor, so a computed property handing out a fresh instance
    /// every time would make every test quietly epoch-0 and the fence untestable.
    private var cache: ActivityAccountCache!

    /// The epoch a write must quote to be accepted. Zero until something clears.
    private func epoch() async -> Int { await cache.currentEpoch() }

    private static let base: Double = 1_760_000_000

    private func conversation(
        _ id: String, title: String = "Design review", at offset: Double = 0
    ) -> ActivityAccountConversation {
        ActivityAccountConversation(
            id: id, title: title, emoji: "🎙️", startedAt: Self.base + offset,
            finishedAt: Self.base + offset + 60, overview: "what we decided")
    }

    // MARK: - The round trip

    /// The title is the entire point: a cached row that came back without one would leave the panel
    /// exactly where it started.
    func testEveryFieldARowDrawsSurvivesTheRoundTrip() async {
        let written = ActivityAccountFeed(
            conversations: [conversation("c1")],
            memories: [
                ActivityAccountMemory(
                    id: "m1", content: "Ships on Friday", at: Self.base, conversationID: "c1")
            ],
            tasks: [
                ActivityAccountTask(id: "t1", text: "Send the deck", completed: false, at: Self.base)
            ],
            answered: Set(ActivityAccountSource.allCases))

        await cache.save(written, epoch: await epoch())
        let read = await cache.load()

        XCTAssertEqual(read.conversations, written.conversations)
        XCTAssertEqual(read.memories, written.memories)
        XCTAssertEqual(read.tasks, written.tasks)
    }

    func testAnEmptyCacheIsAnEmptyAnswerRatherThanAFailure() async {
        let read = await cache.load()
        XCTAssertTrue(read.conversations.isEmpty)
        XCTAssertTrue(read.memories.isEmpty)
        XCTAssertTrue(read.tasks.isEmpty)
    }

    // MARK: - What may be written

    /// **A source that did not answer is not written.** The feed carries whatever the reader has
    /// gathered, including rows from a source that has since started failing; rewriting the cache
    /// from those would be a copy of a copy, ageing without limit while the endpoint stays down.
    func testASourceThatDidNotAnswerIsNotCached() async {
        await cache.save(
            ActivityAccountFeed(
                conversations: [conversation("c1")],
                memories: [ActivityAccountMemory(id: "m1", content: "Ships Friday", at: Self.base)],
                answered: [.conversations]), epoch: await epoch())

        let read = await cache.load()
        XCTAssertEqual(read.conversations.count, 1)
        XCTAssertTrue(
            read.memories.isEmpty,
            "memories did not answer this read, so nothing about them was learned")
    }

    /// **And a locally-sourced one is not written either.** `ActivityLocalMemories` merges the Omi
    /// app's own database into the memory column; caching those would be a second copy of somebody
    /// else's table, and a later launch would read them back as *the account's* answer — a claim
    /// this app has no business making on their behalf.
    func testLocallySourcedRowsAreNeverCachedAsTheAccountsOwn() async {
        await cache.save(
            ActivityAccountFeed(
                memories: [ActivityAccountMemory(id: "m1", content: "Ships Friday", at: Self.base)],
                answered: [.memories],
                locallySourced: [.memories]), epoch: await epoch())

        let read = await cache.load()
        XCTAssertTrue(read.memories.isEmpty)
    }

    /// A source that answers again rewrites its own rows, so a conversation deleted on the phone
    /// survives one paint and no longer — the same bargain main makes.
    func testAnAnsweringSourceReplacesWhatItSaidBefore() async {
        await cache.save(
            ActivityAccountFeed(
                conversations: [conversation("c1"), conversation("c2", at: 60)],
                answered: [.conversations]), epoch: await epoch())
        await cache.save(
            ActivityAccountFeed(conversations: [conversation("c1")], answered: [.conversations]),
            epoch: await epoch())

        let read = await cache.load()
        XCTAssertEqual(
            read.conversations.map(\.id), ["c1"],
            "the account no longer lists c2, so neither does its copy")
    }

    /// One page, which is the page a first paint draws from. Above that the table becomes the
    /// account's whole history inside a database whose reason for existing is screen capture.
    func testTheCacheIsBoundedToOnePagePerSource() async {
        let many = (0..<(ActivityAccountCache.ceiling + 40)).map {
            conversation("c\($0)", at: Double($0))
        }
        await cache.save(
            ActivityAccountFeed(conversations: many, answered: [.conversations]), epoch: await epoch())

        let read = await cache.load()
        XCTAssertEqual(read.conversations.count, ActivityAccountCache.ceiling)
        XCTAssertEqual(
            read.conversations.first?.id, "c\(ActivityAccountCache.ceiling + 39)",
            "and it is the newest page that is kept, not the oldest")
    }

    /// Signing out. One account's conversations must never be the first thing the next sees.
    func testClearingLeavesNothingToPaint() async {
        await cache.save(
            ActivityAccountFeed(conversations: [conversation("c1")], answered: [.conversations]),
            epoch: await epoch())
        await cache.clear()

        let read = await cache.load()
        XCTAssertTrue(read.conversations.isEmpty)
    }

    /// **The second race cubic caught.** A save is spawned detached off a read that has already
    /// been absorbed, so at sign-out there can be one in flight carrying the previous account's
    /// rows. Serialising through the actor makes the two orderable but does not decide the order —
    /// the save can simply arrive second and be perfectly serialised, and still be wrong. The epoch
    /// is what makes "which account is this" the question rather than "which ran last".
    func testASaveMintedBeforeSignOutCannotRepopulateTheClearedCache() async {
        let minted = await epoch()
        await cache.save(
            ActivityAccountFeed(conversations: [conversation("c1")], answered: [.conversations]),
            epoch: minted)
        let seeded = await cache.load()
        XCTAssertFalse(seeded.conversations.isEmpty, "precondition")

        // Sign-out.
        await cache.clear()
        // …and the write that was already on its way, quoting the epoch it was minted under.
        await cache.save(
            ActivityAccountFeed(conversations: [conversation("c2")], answered: [.conversations]),
            epoch: minted)

        let afterSignOut = await cache.load()
        XCTAssertTrue(
            afterSignOut.conversations.isEmpty,
            "the next account's first paint must not be the previous account's conversations")
    }

    /// **The reentrancy hole, which the first version of the fence did not close.**
    ///
    /// `await store()` is a suspension point *inside* the actor, and actors are reentrant — so a
    /// `clear()` arriving while a save is parked there runs to completion, and the save then resumes
    /// past an epoch check it had already passed. Checking the epoch before acquiring the store
    /// reads as the careful order and is exactly the bug.
    func testASaveSuspendedWhenSignOutLandsIsStillDropped() async {
        let gate = FirstCallerGate()
        let store = self.store!
        let reentrant = ActivityAccountCache(store: {
            await gate.holdTheFirstCaller()
            return store
        })
        let minted = await reentrant.currentEpoch()

        // A save that will park inside the provider.
        async let saving: Void = reentrant.save(
            ActivityAccountFeed(conversations: [conversation("c1")], answered: [.conversations]),
            epoch: minted)
        await gate.waitUntilHeld()

        // Sign-out, reentering the actor while that save is suspended.
        await reentrant.clear()
        await gate.release()
        await saving

        let read = await reentrant.load()
        XCTAssertTrue(
            read.conversations.isEmpty,
            "a save parked across a sign-out may not resume into the next account's cache")
    }

    /// The epoch invalidates writes even when the delete itself could not run — a clear that failed
    /// to reach the database must still stop the saves behind it, or a failed delete becomes the
    /// previous account's rows written back a moment later.
    func testAClearThatCannotReachTheDatabaseStillInvalidatesWritesBehindIt() async {
        let absent = ActivityAccountCache(store: { nil })
        let minted = await absent.currentEpoch()
        await absent.clear()
        let after = await absent.currentEpoch()
        XCTAssertNotEqual(
            after, minted, "the fence advances on intent, not on the delete succeeding")
    }

    // MARK: - What a cached paint may claim

    /// **The load-bearing test of the whole feature.** A seeded store shows rows and claims nothing:
    /// the account has not answered, no source has answered, the corpus is not settled, and the
    /// reachability copy stays silent. Getting this wrong means the panel telling somebody their
    /// account is fine on the strength of a file written yesterday.
    @MainActor
    func testASeededStoreDrawsRowsAndClaimsNothingAboutTheAccount() async {
        await cache.save(
            ActivityAccountFeed(conversations: [conversation("c1")], answered: [.conversations]),
            epoch: await epoch())

        // An account that never answers, so the only thing on screen can be the cache.
        let store = ActivityStore(
            store: { nil }, account: SilentAccount(), cache: cache, calendar: Self.calendar)
        store.start()
        await waitUntil("the cached conversation to paint") { store.days.count == 1 }

        XCTAssertFalse(store.accountReachable, "and the account has still said nothing")
        XCTAssertTrue(store.accountAnswered.isEmpty, "no source answered — a copy is not an answer")
        XCTAssertFalse(
            store.corpusSettled, "a cache is never a finished count of what the account holds")
    }

    /// And the ordering rule underneath it: **an answer outranks a copy wherever it actually
    /// spoke.** A slow disk must not resurrect rows the account has just said are gone — including
    /// when what it said was "nothing", which is an answer and not an absence.
    ///
    /// Driven by making the *cache* slow rather than by reaching into the store: the store provider
    /// is `async`, so a gate inside it holds the seed behind the read through the real code path.
    @MainActor
    func testACachedPaintNeverOverwritesAnAnswerThatAlreadyLanded() async {
        await cache.save(
            ActivityAccountFeed(conversations: [conversation("stale")], answered: [.conversations]),
            epoch: await epoch())

        let gate = Gate()
        let store = self.store!
        let slow = ActivityAccountCache(store: {
            await gate.wait()
            return store
        })
        // The account answers, and what it says is that it holds nothing.
        let spine = ActivityStore(
            store: { nil },
            account: EmptyButAnsweringAccount(),
            cache: slow,
            calendar: Self.calendar)

        spine.start()
        await waitUntil("the account's own answer") { !spine.accountAnswered.isEmpty }
        XCTAssertTrue(spine.days.isEmpty, "the account answered, and it answered with nothing")

        await gate.open()
        await settle()

        XCTAssertTrue(
            spine.days.isEmpty,
            "a cache read that lands after the account must not put the row back")
    }

    /// The other side of the same rule, and the reason it is not simply "did a read come back".
    /// **An offline launch is where a cached paint is the whole of what the user gets**, and a read
    /// that failed comes back just as settled as one that succeeded.
    @MainActor
    func testAnUnreachableAccountStillGetsTheCachedPaint() async {
        await cache.save(
            ActivityAccountFeed(conversations: [conversation("c1")], answered: [.conversations]),
            epoch: await epoch())

        let store = ActivityStore(
            store: { nil }, account: SilentAccount(), cache: cache, calendar: Self.calendar)
        store.start()
        await waitUntil("the cached paint behind a failing read") { store.days.count == 1 }
        XCTAssertFalse(
            store.accountReachable,
            "and nobody answered — an offline launch showing the last answer is the whole point")
    }

    private static let calendar: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar
    }()

    /// Waits until `condition` holds, or fails.
    ///
    /// **Not a fixed sleep.** A sleep long enough to be safe on a loaded CI box costs every green
    /// run; one short enough to be cheap is a flake, and a suite people distrust is worse than a
    /// smaller one. This returns the instant the work lands and only spends the deadline when
    /// something is genuinely broken.
    private func waitUntil(
        _ description: String,
        timeout: TimeInterval = 5,
        file: StaticString = #filePath,
        line: UInt = #line,
        _ condition: @MainActor () -> Bool
    ) async {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if await MainActor.run(body: condition) { return }
            await Task.yield()
        }
        XCTFail("timed out waiting for \(description)", file: file, line: line)
    }

    /// For the one assertion that is about something *not* happening and so has no state to wait
    /// on. It waits on a positive signal first, so this only covers the last hop back.
    private func settle() async {
        for _ in 0..<8 { await Task.yield() }
        try? await Task.sleep(nanoseconds: 60_000_000)
        for _ in 0..<8 { await Task.yield() }
    }
}

/// An account that answers nothing, ever. The only way to be sure what is on screen came off disk.
private struct SilentAccount: ActivityAccountReading {
    func read(since: Double?, until: Double?, limit: Int) async -> ActivityAccountFeed {
        .unreachable
    }
}

/// An account that answers — and what it says is that it is empty. Distinct from `SilentAccount` in
/// exactly the way the seed guard is about: this one spoke.
private struct EmptyButAnsweringAccount: ActivityAccountReading {
    func read(since: Double?, until: Double?, limit: Int) async -> ActivityAccountFeed {
        ActivityAccountFeed(answered: Set(ActivityAccountSource.allCases))
    }
}

/// Holds the *first* caller only, so a test can park one actor method inside its suspension point
/// and let a second one reenter past it. A plain gate would deadlock: the reentering call goes
/// through the same provider.
private actor FirstCallerGate {
    private var held = false
    private var released = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func holdTheFirstCaller() async {
        guard !held else { return }
        held = true
        guard !released else { return }
        await withCheckedContinuation { waiters.append($0) }
    }

    func waitUntilHeld() async {
        while !held { await Task.yield() }
    }

    func release() {
        released = true
        for waiter in waiters { waiter.resume() }
        waiters = []
    }
}

/// A latch, so a test can hold the disk behind the network and assert on the order.
private actor Gate {
    private var isOpen = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func wait() async {
        guard !isOpen else { return }
        await withCheckedContinuation { waiters.append($0) }
    }

    func open() {
        isOpen = true
        for waiter in waiters { waiter.resume() }
        waiters = []
    }
}
