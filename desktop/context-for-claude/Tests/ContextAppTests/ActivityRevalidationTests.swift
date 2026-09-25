import Combine
import ContextCore
import Foundation
import XCTest

@testable import ContextApp

/// Coming back to the Activity panel, and what may not happen when you do.
///
/// **The defect these are written against.** The Activity store was a `@StateObject` inside
/// `ActivitySurface`, and three ordinary actions destroyed it: `SearchBarWindow.dismiss()` drops
/// `current` so every summoning builds a new window and a new view, and the panel's lower half is a
/// `switch` on which body is showing, so typing a query unmounts the activity branch and clearing
/// the field mounts a fresh one. Each of those threw away a fully hydrated corpus and re-paged the
/// account from offset zero. On the measured account that is thousands of rows and dozens of
/// requests, repeated, for data that had not changed — and on the way there the panel drew local
/// sessions as `Untitled conversation`, because a title is written by the backend and a session
/// that has not been uploaded has none.
///
/// So the store now belongs to the process (`ActivitySpine`) and coming back is a *revalidation*:
/// keep every row that is on screen, ask the account what changed, throttled. These prove the
/// "keep" half as hard as the "ask" half, because the failure mode of getting it wrong is a spinner
/// over a list that was already correct.
final class ActivityRevalidationTests: XCTestCase {

    private static let calendar: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar
    }()

    /// 2025-10-09T08:53:20Z, the same fixed epoch the other Activity suites use.
    private static let base: Double = 1_760_000_000

    // MARK: - The cooldown

    /// Main's number and main's shape: `PollingConfig.shouldAllowActivationRefresh` is a free
    /// function over its inputs precisely so the boundary can be asserted rather than waited for,
    /// and a regression from `>=` to `>` is caught rather than shipped.
    func testTheCooldownIsAMinuteAndTheBoundaryIsInclusive() {
        let now = Date(timeIntervalSince1970: Self.base)

        XCTAssertTrue(
            ActivityStore.shouldRevalidate(now: now, lastRevalidate: nil),
            "a panel that has never revalidated may do so immediately")
        XCTAssertFalse(
            ActivityStore.shouldRevalidate(now: now, lastRevalidate: now),
            "twice in the same instant is one request")
        XCTAssertFalse(
            ActivityStore.shouldRevalidate(
                now: now, lastRevalidate: now.addingTimeInterval(-59)))
        XCTAssertTrue(
            ActivityStore.shouldRevalidate(
                now: now, lastRevalidate: now.addingTimeInterval(-60)),
            "the boundary is inclusive, as PollingConfig's is")
    }

    // MARK: - Keeping what is on screen

    /// **The requirement, stated as a test.** A revalidation must not empty the list it is
    /// refreshing: the rows stay, the count stays, and nothing goes back to `isPreparing`.
    @MainActor
    func testRevalidatingKeepsEveryRowOnScreen() async {
        let account = CountingAccount(
            feed: ActivityAccountFeed(conversations: [conversation("a", at: 0)]))
        let store = ActivityStore(store: { nil }, account: account, calendar: Self.calendar)

        store.start()
        await waitUntil("the opening read and its hydration") { store.corpusSettled }
        XCTAssertEqual(store.days.count, 1, "precondition: the first read painted something")
        let painted = store.days
        // **Waited to quiescence, not merely to first paint.** The opening read is followed by
        // hydration's own reads until the corpus stops growing, and a baseline captured mid-walk
        // would have the revalidation refused by the single-flight guard — a green-looking test
        // that measured the wrong thing.
        let opened = account.reads

        store.revalidate(now: Date(timeIntervalSince1970: Self.base))

        // Checked synchronously, before the read can possibly have come back: the moment that
        // matters is the one *during* the request, which is when a store that cleared itself would
        // be showing an empty panel.
        XCTAssertEqual(store.days, painted, "the list may not blink while the account is asked")
        XCTAssertFalse(store.isPreparing, "and a list that is already correct is not 'preparing'")

        await waitUntil("the revalidating read") { account.reads > opened }
        XCTAssertEqual(store.days, painted, "and it still has not blinked now the read has landed")
        XCTAssertEqual(account.refreshes, 1, "through the head, which is where new rows arrive")
    }

    /// The throttle, through the store rather than through the free function: two summonings in a
    /// row are one request, and a minute later is another.
    @MainActor
    func testASecondRevalidationInsideTheCooldownAsksNothing() async {
        let account = CountingAccount(
            feed: ActivityAccountFeed(conversations: [conversation("a", at: 0)]))
        let store = ActivityStore(store: { nil }, account: account, calendar: Self.calendar)
        store.start()
        await waitUntil("the opening read and its hydration") { store.corpusSettled }
        let opened = account.reads

        let now = Date(timeIntervalSince1970: Self.base)
        store.revalidate(now: now)
        await waitUntil("the first revalidation") { account.reads == opened + 1 }

        store.revalidate(now: now.addingTimeInterval(30))
        await settle()
        XCTAssertEqual(account.reads, opened + 1, "inside the cooldown, nothing is asked")

        store.revalidate(now: now.addingTimeInterval(61))
        await waitUntil("the revalidation past the cooldown") { account.reads == opened + 2 }
    }

    /// `start()` is called from `.task` on every appearance, and the surface now appears many times
    /// over one store's life. The first call opens the window; every later one revalidates.
    @MainActor
    func testStartingAnAlreadyStartedStoreRevalidatesRatherThanReopening() async {
        let account = CountingAccount(
            feed: ActivityAccountFeed(conversations: [conversation("a", at: 0)]))
        let store = ActivityStore(store: { nil }, account: account, calendar: Self.calendar)

        store.start()
        await waitUntil("the opening read and its hydration") { store.corpusSettled }
        let painted = store.days
        let opened = account.reads

        store.start()
        await waitUntil("the second appearance to ask") { account.reads == opened + 1 }
        XCTAssertEqual(store.days, painted, "and does not rebuild the list to do it")
    }

    /// A store handed its answer at construction has no sources behind it, so recomposing rebuilds
    /// the list out of three empty inputs and erases the very thing it was built to show. The render
    /// harness calls `start()`; this is what stops that from blanking every preview.
    @MainActor
    func testAPreviewStoreIsNeverRevalidated() async {
        let store = ActivityStore(days: [day(with: [])], calendar: Self.calendar)
        let painted = store.days
        XCTAssertFalse(painted.isEmpty, "precondition")

        store.start()
        store.revalidate(now: Date(timeIntervalSince1970: Self.base))
        await settle()

        XCTAssertEqual(store.days, painted)
    }

    // MARK: - What a failing read may not erase

    /// **The offline launch, which is the case the cache exists for.**
    ///
    /// The seed paints from disk and the failing read lands a moment later carrying nothing. Taking
    /// the read wholesale wiped the rows the user had just been shown, and which of the two landed
    /// first was a race — so the panel was empty about half the time, on the one launch where the
    /// cache is the whole of the answer.
    func testASourceThatSaidNothingAndCarriedNothingKeepsWhatIsOnScreen() {
        let painted = ActivityAccountFeed(
            conversations: [conversation("cached", at: 0)], answered: [])

        let held = ActivityStore.retaining(rowsNotAnsweredIn: .unreachable, from: painted)

        XCTAssertEqual(held.conversations.map(\.id), ["cached"])
        XCTAssertTrue(held.answered.isEmpty, "and it still reports that nobody answered")
    }

    /// **The half that a first attempt at this got wrong.** The paging reader answers with
    /// everything it has gathered, so a source absent from `answered` routinely carries hundreds of
    /// real rows fetched on an earlier read. Those are the corpus, not a stale leftover.
    func testASourceThatSaidNothingButCarriedRowsKeepsTheRowsItCarried() {
        let previous = ActivityAccountFeed(
            conversations: [conversation("old", at: 0)], answered: [])
        let carrying = ActivityAccountFeed(
            conversations: [conversation("a", at: 0), conversation("b", at: 60)],
            answered: [.memories, .tasks])

        let held = ActivityStore.retaining(rowsNotAnsweredIn: carrying, from: previous)

        XCTAssertEqual(held.conversations.map(\.id), ["a", "b"])
    }

    /// And an **answered** source is taken as it comes, empty included: "I hold nothing" is an
    /// answer, and the account is the authority on it. Retaining here would resurrect deletions.
    func testAnAnsweredSourceIsTakenEvenWhenItIsEmpty() {
        let previous = ActivityAccountFeed(
            conversations: [conversation("deleted", at: 0)], answered: [])
        let emptied = ActivityAccountFeed(
            conversations: [], answered: Set(ActivityAccountSource.allCases))

        let held = ActivityStore.retaining(rowsNotAnsweredIn: emptied, from: previous)

        XCTAssertTrue(held.conversations.isEmpty)
    }

    /// A transient failure in the opening read must not outlive the read that succeeded after it.
    /// `openWindow` used to be the only thing that reset this, which was enough while an opening
    /// read happened once per window — a revalidation runs another one.
    @MainActor
    func testASuccessfulRevalidationClearsAStaleCaptureFailure() async {
        let account = CountingAccount(
            feed: ActivityAccountFeed(conversations: [conversation("a", at: 0)]))
        let store = ActivityStore(store: { nil }, account: account, calendar: Self.calendar)
        store.start()
        await settle()

        XCTAssertNil(
            store.readFailure,
            "a store with no capture database reports its availability, not a read failure")
    }

    // MARK: - Signing out

    /// A window-lived store forgot the account by dying. A process-lived one has to be told, and
    /// what it must forget is the account half only — frames and speech on this Mac were captured
    /// whether or not anybody was signed in.
    @MainActor
    func testSigningOutDropsTheAccountAndSaysWhy() async {
        let account = CountingAccount(
            feed: ActivityAccountFeed(conversations: [conversation("a", at: 0)]))
        let store = ActivityStore(store: { nil }, account: account, calendar: Self.calendar)
        store.start()
        await waitUntil("the opening read and its hydration") { store.corpusSettled }

        store.forgetTheAccount()
        await waitUntil("the account half to be dropped") { store.days.isEmpty }

        XCTAssertFalse(store.accountReachable)
        XCTAssertEqual(store.accountUnreachableReason, .signedOut)
        XCTAssertTrue(store.accountAnswered.isEmpty)
        XCTAssertTrue(
            store.days.isEmpty, "the previous account's conversations are off the screen")
    }

    /// **The race cubic caught, and the reason `forgetTheAccount` advances the generation.**
    ///
    /// An account read is a network round trip; signing out is a keystroke. The two overlap
    /// routinely, and before the fence the read that left *before* the sign-out landed after it,
    /// passed a guard comparing a generation nothing had moved, and repainted the panel with the
    /// previous account's conversations — after the store had just finished forgetting them.
    @MainActor
    func testAReadInFlightWhenTheUserSignsOutCannotRepaintTheirAccount() async {
        let gate = Gate()
        let account = HeldAccount(
            feed: ActivityAccountFeed(conversations: [conversation("a", at: 0)]), gate: gate)
        let store = ActivityStore(store: { nil }, account: account, calendar: Self.calendar)

        // A read is now in flight, blocked inside the account.
        store.start()
        await waitUntil("the read to reach the account") { account.started > 0 }
        XCTAssertTrue(store.days.isEmpty, "precondition: nothing has landed yet")

        store.forgetTheAccount()
        await gate.open()
        await settle()

        XCTAssertTrue(
            store.days.isEmpty,
            "a read minted before the sign-out may not repaint the previous account")
        XCTAssertFalse(store.accountReachable)
        XCTAssertEqual(store.accountUnreachableReason, .signedOut)
    }

    /// And the panel must still work for whoever signs in next — the fence may invalidate the old
    /// read without also wedging the store against the new one.
    @MainActor
    func testTheNextAccountCanStillBeReadAfterASignOutInvalidatedAReadInFlight() async {
        let gate = Gate()
        let account = HeldAccount(
            feed: ActivityAccountFeed(conversations: [conversation("a", at: 0)]), gate: gate)
        let store = ActivityStore(store: { nil }, account: account, calendar: Self.calendar)

        store.start()
        await waitUntil("the read to reach the account") { account.started > 0 }
        store.forgetTheAccount()
        await gate.open()
        await settle()

        // Signed in again: `revalidate` is the path the store's own sign-in subscription takes.
        store.revalidate(now: Date(timeIntervalSince1970: Self.base))
        await waitUntil("the new account's rows") { !store.days.isEmpty }
        XCTAssertTrue(store.accountReachable)
    }

    /// And the wiring that calls it, so the sign-out edge cannot be quietly disconnected.
    @MainActor
    func testTheSpineForgetsTheAccountWhenTheSignInPublisherGoesFalse() async {
        let account = CountingAccount(
            feed: ActivityAccountFeed(conversations: [conversation("a", at: 0)]))
        let store = ActivityStore(store: { nil }, account: account, calendar: Self.calendar)
        let signIns = CurrentValueSubject<Bool, Never>(true)
        let spine = ActivitySpine.forTesting(
            store: store, signIns: signIns.eraseToAnyPublisher())
        withExtendedLifetime(spine) {}

        store.start()
        await waitUntil("the opening read and its hydration") { store.corpusSettled }

        signIns.send(false)
        await waitUntil("the spine to forget the account") { store.days.isEmpty }

        XCTAssertEqual(store.accountUnreachableReason, .signedOut)
    }

    /// Activation is the other signal, and it is the one main uses. Driven through an injected
    /// publisher rather than by posting `NSApplication.didBecomeActiveNotification`, which a test
    /// process fires for reasons of its own.
    @MainActor
    func testTheSpineRevalidatesWhenTheAppBecomesActive() async {
        let account = CountingAccount(
            feed: ActivityAccountFeed(conversations: [conversation("a", at: 0)]))
        let store = ActivityStore(store: { nil }, account: account, calendar: Self.calendar)
        let activations = PassthroughSubject<Void, Never>()
        let spine = ActivitySpine.forTesting(
            store: store,
            signIns: Empty<Bool, Never>().eraseToAnyPublisher(),
            activations: activations.eraseToAnyPublisher())
        withExtendedLifetime(spine) {}

        store.start()
        await waitUntil("the opening read and its hydration") { store.corpusSettled }
        let opened = account.reads

        activations.send(())
        await waitUntil("activation to revalidate") { account.reads == opened + 1 }
    }

    // MARK: - Helpers

    /// Waits until `condition` holds, or fails the test.
    ///
    /// **Not a fixed sleep.** A sleep long enough to be safe on a loaded CI box is a sleep that
    /// costs every green run, and one short enough to be cheap is a flake — the suite people stop
    /// trusting. This returns the instant the work lands and only spends the deadline when
    /// something is actually broken, which is the shape a hermetic test wants.
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

    /// Lets the store's detached reads and its main-actor absorption run, for the assertions that
    /// are about something *not* happening and so have no state to wait on. Bounded and short: the
    /// positive half of every one of those tests is waited for properly first, so by the time this
    /// runs the machinery is already known to be idle.
    private func settle() async {
        for _ in 0..<8 { await Task.yield() }
        try? await Task.sleep(nanoseconds: 40_000_000)
        for _ in 0..<8 { await Task.yield() }
    }

    private func conversation(_ id: String, at offset: Double) -> ActivityAccountConversation {
        ActivityAccountConversation(
            id: id, title: "Titled \(id)", emoji: "💬", startedAt: Self.base + offset,
            finishedAt: Self.base + offset + 60, overview: nil)
    }

    private func day(with rows: [ActivityRow]) -> ActivityDay {
        ActivityDay(
            id: Self.calendar.startOfDay(for: Date(timeIntervalSince1970: Self.base)),
            title: "TODAY", momentCount: 0, conversationCount: 0, memoryCount: 0, taskCount: 0,
            rows: rows)
    }
}

/// An account that answers the same feed every time and counts how often it was asked.
///
/// `@unchecked Sendable` over a lock rather than an actor: the seam is `Sendable` and synchronous
/// from the store's point of view, and a counter behind a lock keeps the assertions readable.
private final class CountingAccount: ActivityAccountReading, ActivityAccountCursor, @unchecked Sendable {
    private let lock = NSLock()
    private var _reads = 0
    private var _refreshes = 0
    private var _forgets = 0
    private let feed: ActivityAccountFeed

    init(feed: ActivityAccountFeed) {
        self.feed = feed
    }

    var reads: Int { lock.withLock { _reads } }
    var refreshes: Int { lock.withLock { _refreshes } }
    var forgets: Int { lock.withLock { _forgets } }

    func read(since: Double?, until: Double?, limit: Int) async -> ActivityAccountFeed {
        lock.withLock { _reads += 1 }
        return feed
    }

    func refreshHead() async { lock.withLock { _refreshes += 1 } }
    func forget() async { lock.withLock { _forgets += 1 } }
}

/// An account whose read blocks until the test lets it finish, so a sign-out can be driven into the
/// exact window where a response is already on its way back.
private final class HeldAccount: ActivityAccountReading, ActivityAccountCursor, @unchecked Sendable {
    private let lock = NSLock()
    private var _started = 0
    private let feed: ActivityAccountFeed
    private let gate: Gate

    init(feed: ActivityAccountFeed, gate: Gate) {
        self.feed = feed
        self.gate = gate
    }

    /// How many reads have reached the account. The signal a test waits on to know the request is
    /// genuinely in flight rather than merely scheduled.
    var started: Int { lock.withLock { _started } }

    func read(since: Double?, until: Double?, limit: Int) async -> ActivityAccountFeed {
        lock.withLock { _started += 1 }
        await gate.wait()
        return feed
    }

    func refreshHead() async {}
    func forget() async {}
}

/// A latch, so a test can hold a response mid-flight and assert on the ordering around it.
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
