//
//  ActivityStore.swift — what the Activity list is made of, and when it is rebuilt.
//
//  The capture database and the account already own all of this and none of it is replaced here:
//  frames stay with `RewindQueries`, speech stays with `Queries`, and conversations, memories and
//  tasks stay with the account behind `ActivityAccountReading`. This is a projection over the three,
//  and it deliberately holds no authority — no writes, no second cache, no third opinion about what
//  was captured.
//
//  **The account is read a page at a time, and it is allowed to say nothing.** An unreachable
//  account is an ordinary state, not an error: the store keeps `accountReachable` so the empty copy
//  can tell "nobody answered" from "there was nothing", and the local half of the stream is composed
//  either way.
//
//  **One page is not a corpus.** The reader answers with everything it has gathered so far and
//  fetches one more page each time it is asked, so this reads again while the answer keeps growing
//  and stops when it does not — the reference's background hydrator, in the shape this seam allows.
//  The first page is what the panel paints; the rest of the account arrives underneath a list that
//  is already readable, and `corpusSettled` is what tells the corner whether the number it is
//  showing has stopped moving. See `absorb(account:reason:generation:)`.
//
//  **A read that failed is not a read that finished.** A failure for a reason that heals on its own
//  — a rate limit, a timeout, no route — would otherwise leave the panel empty until the user moves
//  the window, which is a surface that stays broken long after the thing that broke it has gone. So
//  those reasons, and only those, are re-read on a bounded schedule; see `scheduleAccountReread`.
//
//  **Days are read one at a time, newest first, and a few at a time.** A Mac with a year of capture
//  has a year of days, and reading them all before the first paint would put a spinner in front of
//  the day the user is actually looking at. So the opening read is cheap — the coverage span, the
//  session headers, the app→bundle map — and the frames of each day arrive behind it, with the
//  newest days first because that is where the list starts.
//
//  **`nil` and `0` are different claims about a day, and the rail depends on the difference.** A
//  day nobody has read yet has *no* moment count; a day whose read came back empty has a count of
//  zero. Collapsing the two is what makes a surface print a confident "0 screen moments" for a day
//  it never looked at, next to a five-figure account total. `momentCount(for:)` is where that
//  distinction is told.
//

import Combine
import ContextCore
import Foundation

// MARK: - Why an account did not answer

/// The reason behind `ActivityAccountFeed.reachable == false`.
///
/// `reachable` is a `Bool` because the spine only ever branches two ways on it — compose the account
/// rows, or do not. **The reader needs more than that**, and only in one place: an empty stream has
/// to say something true, and "I couldn't reach your account" is the wrong thing to tell someone
/// whose key expired (they can fix it) or who never signed in (nothing is wrong). So the reason
/// travels beside the feed rather than inside it, and only a reader that actually knows one reports
/// it.
enum ActivityAccountUnreachableReason: Sendable, Equatable {
    /// The user turned Airgap Mode on. Nothing was asked, and nothing is wrong.
    case airgapped
    /// No Omi account is signed in.
    case signedOut
    /// Signed in, but this Mac has no key to read the account with — one has never been provisioned,
    /// or minting one failed.
    case keyUnavailable
    /// This Mac had a key and the account refused it, and it could not be replaced.
    case keyRejected
    /// The account answered, and what it said was 429. Nothing is wrong with the key, the request or
    /// this Mac — the account is asking us to wait, so this is the one unreachable reason that
    /// repairs itself. `scheduleAccountReread` is what waits.
    case rateLimited
    /// Asked, and nothing answered: offline, an outage, a route that went away.
    case noAnswer
}

/// An account reader that can say *why* it came back unreachable.
///
/// Deliberately separate from `ActivityAccountReading`: a preview's account, a test's account and
/// `ActivityAccountAbsent` have no diagnosis to give and should not be made to invent one.
protocol ActivityAccountDiagnosing: Sendable {
    /// The reason behind the most recent read, or nil when the last read succeeded.
    func unreachableReason() async -> ActivityAccountUnreachableReason?
}

// MARK: - Whether this Mac's own half could be asked at all

/// Whether there is a capture database behind the local half of the spine.
///
/// **A third state, and it shipped as neither of the other two.** `readFailure` says a read ran and
/// threw; an empty stream says a read ran and found nothing. A store that never opened is neither:
/// nothing was asked, so nothing threw, and the surface fell through to reporting *the account's*
/// state instead. Observed on a real launch whose migration threw — a Mac holding 2,837 frames drew
/// "Sign in to Omi to see your account here", which is true, irrelevant, and the single most
/// misleading sentence available at that moment.
///
/// So the local half's availability travels beside the account's, and `ActivityEmptyCopy` reports it
/// first: a machine that could not be asked outranks an account that answered.
enum ActivityCaptureAvailability: Equatable, Sendable {
    /// There is a database, and everything the spine says about this Mac came out of it.
    case open
    /// There is not one yet, and the store is still waiting — see `ActivityStore.waitForTheStore`.
    case opening
    /// The wait ran out. This Mac's capture never opened, and this surface is not going to see it.
    case unavailable
}

@MainActor
final class ActivityStore: ObservableObject {

    /// What the list renders: composed, then narrowed by the chip, the query and the time window.
    @Published private(set) var days: [ActivityDay] = []
    /// True until the first day has been read. A day landing behind an already-populated list is
    /// not a spinner.
    @Published private(set) var isPreparing = true
    /// How many things survived the request — one count, computed once, so the chrome and the body
    /// can never quietly disagree about what is on screen.
    @Published private(set) var matchCount = 0
    /// How much this Mac and the account are holding between them, before any filter. `nil` until
    /// there is something to count, which the corner reads as "counting" rather than as a zero.
    @Published private(set) var corpusTotal: Int?
    /// Whether `corpusTotal` is a finished count. The day walk fills older days in behind an
    /// already-readable list, so the number climbs under the reader until the walk and the account
    /// read are both done — and a number that moves has to say why.
    @Published private(set) var corpusSettled = false
    /// Whether the account answered the last read. **Not the same as an empty account**, which is
    /// the whole reason `ActivityAccountFeed` carries `reachable`.
    @Published private(set) var accountReachable = false
    /// Why it did not answer, when the reader knows. `nil` for a reachable account and for a reader
    /// with no diagnosis to give — the empty copy falls back to the general sentence there.
    @Published private(set) var accountUnreachableReason: ActivityAccountUnreachableReason?
    /// Which account columns on screen were read from this Mac rather than from the account, and
    /// which the account answered for. Both are needed together and neither is derivable from the
    /// other: a column can be locally sourced *and* answered — the normal state, where a few
    /// not-yet-synced memories merge alongside the account's own — and the state worth a sentence is
    /// the one where it is locally sourced and the account said nothing. See
    /// `ActivityAccountLocalNote`, which is the only reason either is on the store.
    @Published private(set) var accountLocallySourced: Set<ActivityAccountSource> = []
    @Published private(set) var accountAnswered: Set<ActivityAccountSource> = []
    /// Set when a read threw. **Not the same as an empty day**, and the surface has to be able to
    /// say which: an empty list under a failed read is not an answer about the machine.
    @Published private(set) var readFailure: String?
    /// Whether this Mac's own half could be asked at all. See `ActivityCaptureAvailability` — the
    /// third state, and the one the empty copy used to fall through entirely.
    @Published private(set) var capture: ActivityCaptureAvailability = .open

    /// What the bar says when a read itself failed. One sentence, and deliberately not the
    /// underlying error — a GRDB error renders its failing statement and its bound arguments, one
    /// of which is built from what the user typed.
    nonisolated static let readFailureNote =
        "I couldn't read this Mac's capture just now, so this is not an empty answer — try again."

    /// Which kind the chips have soloed. Read by the stream to decide whether attached rows still
    /// indent.
    private(set) var kind: ActivityKind = .all

    /// Whether the corner is describing a narrowed stream or the whole corpus. One value, so the
    /// sentence and the list can never disagree about whether a filter is on.
    var isFiltering: Bool {
        kind != .all || !currentQuery.isEmpty || since != nil || until != nil
    }

    /// The one decoder every tile draws through. Owned here rather than per-tile for the reason
    /// `FrameLoader` documents: a second loading path is a second cache and a second set of bugs.
    let loader = FrameLoader()

    /// How many days may be read at once. Enough that the newest days land together, few enough
    /// that the database is never the reason a scroll stutters.
    static let maximumConcurrentDayLoads = 3

    /// How far back the day walk goes. A year of capture is already far past what any strip on this
    /// surface is read for, and it bounds the walk on a database whose oldest row is a decade old.
    nonisolated static let dayWalkCeiling = 400

    /// How many frames of one day reach the strips. A day's frames are split into runs by
    /// `ActivityComposer.clusters(of:)` and each run draws at most `momentsPerStrip`, so this is a
    /// ceiling on the *sample*, not on what the header counts.
    nonisolated static let sampleCeiling = 240

    /// How many session headers the opening read asks for. Sessions are one row each and the
    /// heaviest thing on this surface is the frames, so the whole span fits comfortably — but it is
    /// bounded rather than unbounded, because an unbounded read is a read whose cost is the user's
    /// history rather than the screen's.
    nonisolated static let sessionCeiling = 500

    /// How many of each kind one account read asks for. Bounded for the same reason
    /// `sessionCeiling` is, and more urgently: this one crosses a network, so an unbounded read is a
    /// request whose size is the user's whole history and whose cost is the first paint of the
    /// panel. Well past what any reader scrolls in one window, and far short of an account dump.
    ///
    /// **It is the reader's own per-source cap and not a number above it, which is what makes a
    /// truncated read detectable.** `OmiActivityFeed` clamps every source to `maxPerSource`, so any
    /// ceiling above that is a number nobody honours: this asked for 300, got exactly 200 back three
    /// times over, and had no way to tell one page of a long account from an account holding exactly
    /// two hundred. Asking for what the reader will actually give is the page size, and a page size
    /// the reader honours is what makes "this page was the last one" a sound claim rather than a
    /// clamp mistaken for an inventory.
    nonisolated static let accountCeiling = OmiActivityFeed.maxPerSource

    /// The coalescing window for recomposition.
    ///
    /// Composition's cost is the size of the corpus, not the size of the day that arrived, so
    /// rebuilding once per day landing would spend the whole walk recomposing behind a list the
    /// user may be scrolling. Long enough to absorb a few days, far too short to read as a delay on
    /// a list that is already on screen.
    private static let recomposeCoalescingWindow: Duration = .milliseconds(300)

    /// Asked for, never held. The main window is built at launch and the engine opens the store on
    /// its own queue some time after, so a store captured once here would be the `nil` of the first
    /// instant, kept forever — a surface that draws its empty state at every later moment because of
    /// where it was in the launch sequence. `SearchResultsModel` takes the same provider for the same
    /// reason; the two surfaces in this window must heal on the same terms.
    private let store: () -> ContextStore?
    /// The account half of the spine. Held rather than asked for: unlike `ContextStore` it is a
    /// value the host owns from the start, and `ActivityAccountAbsent` is a perfectly good one.
    private let account: ActivityAccountReading
    /// The last answer the account gave, on disk. See `ActivityAccountCache` — it is a copy with no
    /// standing, and `seed(cached:generation:)` is the only thing that reads it.
    private let cache: ActivityAccountCache?
    private let calendar: Calendar
    /// The healing schedule, injectable so a test can prove the ladder without spending it.
    private let accountRetryDelays: [Duration]
    /// True for a store handed its answer at construction — previews and the render harness.
    ///
    /// **It exists to stop `revalidate()` from reaching one.** That initialiser assigns `composed`
    /// directly and has no sources behind it, so any recomposition rebuilds the list out of three
    /// empty inputs and erases the very thing the preview was constructed to show. `didStart` used
    /// to be enough, back when the only thing it guarded was the opening read; a `start()` that now
    /// revalidates on every appearance is exactly the call a preview makes.
    private let holdsAFixedAnswer: Bool

    /// Composed, unfiltered. The filter pass reads this and never mutates it.
    private var composed: [ActivityDay] = []
    /// Per-day screen capture, keyed by the local start of the day.
    private var screen: [Date: ActivityDayScreen] = [:]
    private var sessions: [SessionSummary] = []
    /// Session id → the account conversations it was uploaded as. Empty until the opening read
    /// lands, which is the same state as "nothing has been uploaded yet" and composes the same way.
    private var uploadLinks: [Int64: [String]] = [:]
    /// What the account last answered, for the window currently open.
    private var accountFeed: ActivityAccountFeed = .unreachable
    /// Whether the account read for the current window has come back at all. Distinct from
    /// `accountReachable`, which is what it *said*.
    private var accountSettled = false

    /// Days whose frames have been read, so a scroll never re-queries a day it already has.
    private var loadedDays: Set<Date> = []
    /// Days waiting to be read, newest first, and the few being read right now.
    private var queue: [Date] = []
    private var queued: Set<Date> = []
    private var active = 0

    /// The term last applied, trimmed and case-folded. Readable because the empty state's copy
    /// depends on it: "nothing matches X" and "nothing captured yet" are different claims, and only
    /// the store knows which question was asked.
    private(set) var currentQuery = ""
    private var since: Double?
    private var until: Double?

    private var didStart = false
    private var recomposeTask: Task<Void, Never>?

    /// Which time window a landing read belongs to.
    ///
    /// The account read is a network round trip and the window can move under it — a chip press is
    /// instant and a request is not — so a feed that lands after the question changed would populate
    /// the spine with the answer to the previous one. The database reads are bounded by the same
    /// counter for the same reason, and it costs one comparison.
    private var generation = 0

    /// Cancelled with the store. Only ever holds the sign-in subscription below.
    private var cancellables: Set<AnyCancellable> = []

    init(
        store: @escaping () -> ContextStore?,
        account: ActivityAccountReading = ActivityAccountAbsent(),
        cache: ActivityAccountCache? = nil,
        calendar: Calendar = .current,
        accountRetryDelays: [Duration] = ActivityStore.accountRetryDelays,
        signIns: AnyPublisher<Bool, Never>? = nil
    ) {
        self.store = store
        self.account = account
        self.cache = cache
        self.calendar = calendar
        self.accountRetryDelays = accountRetryDelays
        self.holdsAFixedAnswer = false

        // **Signing in is the one repair the retry ladder must not wait for, and cannot find.**
        // `healsOnItsOwn` correctly refuses to re-poll a signed-out account — no amount of waiting
        // signs anybody in — so without this the panel is stuck on whatever it saw the first time it
        // asked, until the user moves the window. That is not a hypothetical: the panel opens at
        // launch and `OmiAuth.restore()` reads the Keychain off the main actor, so on a real launch
        // the account was read **40 ms before the session landed**. The reader saw a signed-out
        // account, said so honestly, and then never asked again while the app sat there signed in.
        //
        // So the repair is an event rather than a timer, the same one `ConversationUploader` already
        // subscribes to for the same reason. `removeDuplicates` because the publisher is a
        // `@Published` and republishes on every assignment; `filter` because signing *out* needs no
        // re-read — the next read would only confirm it, and the copy on screen is already right.
        (signIns ?? OmiAuth.shared.$isSignedIn.eraseToAnyPublisher())
            .removeDuplicates()
            .filter { $0 }
            .sink { [weak self] _ in
                guard let self, self.didStart else { return }
                ContextLog.info("Signed in; re-reading the account", "activity")
                self.readAccount(generation: self.generation)
            }
            .store(in: &cancellables)
    }

    /// A store with its answer already in it, for previews and tests. Takes no store and no account,
    /// so nothing it does can touch the user's database or the network.
    ///
    /// - Parameters:
    ///   - accountReachable: what the empty copy is entitled to say. A store handed days has by
    ///     definition read something, so the default is the reachable one.
    ///   - corpusSettled: whether the corner's number is a finished count. `false` renders the
    ///     "still counting" branch, which is otherwise only reachable mid-walk.
    init(
        days: [ActivityDay],
        accountReachable: Bool = true,
        accountUnreachableReason: ActivityAccountUnreachableReason? = nil,
        corpusSettled: Bool = true,
        calendar: Calendar = .current
    ) {
        self.store = { nil }
        self.account = ActivityAccountAbsent()
        self.cache = nil
        self.calendar = calendar
        self.accountRetryDelays = Self.accountRetryDelays
        self.holdsAFixedAnswer = true
        self.composed = days
        self.days = days
        self.matchCount = days.reduce(0) { $0 + $1.matchCount }
        self.corpusTotal = days.isEmpty ? nil : days.reduce(0) { $0 + $1.thingCount }
        self.corpusSettled = corpusSettled
        self.accountReachable = accountReachable
        self.accountUnreachableReason = accountReachable ? nil : accountUnreachableReason
        self.accountSettled = true
        self.isPreparing = false
        self.didStart = true
    }

    // MARK: - Input

    /// Begins the opening read, once — and revalidates on every appearance after that.
    ///
    /// **The second half is the whole of what the panel coming forward means.** This store outlives
    /// the window that draws it (see `ActivitySpine`), so a surface mounting for the twentieth time
    /// already holds a composed corpus and must not throw it away to fetch one it already has. What
    /// it should do is exactly what main does on `didBecomeActiveNotification`: keep every row on
    /// screen and ask the account what changed. `revalidate()` is that, and its cooldown is what
    /// keeps a burst of mounts from becoming a burst of requests.
    func start() {
        guard !didStart else {
            revalidate()
            return
        }
        didStart = true
        openWindow()
    }

    /// Ask the account what has changed, **without disturbing anything already on screen.**
    ///
    /// The distinction from `openWindow()` is the entire point and it is worth stating plainly:
    /// opening a window is a new question and throws away the answer to the old one; revalidating is
    /// the same question asked again. So nothing here clears `composed`, `accountFeed`, `screen` or
    /// `loadedDays`, nothing sets `isPreparing`, and the generation does **not** advance — a spinner
    /// over a list that is already correct is a worse answer than the list.
    ///
    /// Both halves are re-read, because both can have moved: the account has whatever was recorded
    /// on the phone since, and this Mac has whatever it captured while the panel was closed.
    ///
    /// - Parameter now: injected so the cooldown can be proved without waiting a minute for it.
    func revalidate(now: Date = Date()) {
        guard didStart, !holdsAFixedAnswer else { return }
        // **A read of this window is already out.** It will answer with whatever the account holds,
        // so a second one buys nothing — and reopening the head under it would spend the reopen on a
        // read that has already chosen its page. Deliberately *not* stamped: the next time the panel
        // comes forward is a fresh chance rather than one silently skipped.
        guard accountReadInFlight == nil else { return }
        guard Self.shouldRevalidate(now: now, lastRevalidate: lastRevalidate) else { return }
        lastRevalidate = now

        // **The reopen and the read it is for are one operation, so they take the slot together.**
        // Spawning the reopen and calling `readAccount` after it left a window in which the retry
        // ladder or the sign-in subscription could claim the slot first: that read would then be
        // refused nothing and this one refused everything, and the reopened head would sit
        // unconsumed until whatever asked next. Passing the intent into `readAccount` puts the whole
        // sequence behind the one guard that already exists for it.
        readAccount(generation: generation, reopeningHead: true)
        revalidateLocalHalf(generation: generation)
    }

    /// Re-reads this Mac's half: the session headers, the upload links, and the frames of any day
    /// that could still be growing.
    ///
    /// **Only the days that could have changed.** `loadedDays` exists so a scroll never re-queries a
    /// day it already has, and revalidation must not undo that for a year of history — the frames of
    /// last March are as read as they will ever be. A day is re-readable exactly when capture could
    /// have added to it since the last read, which is every day from the one that read happened on
    /// onwards: one day on an ordinary re-open, two when the panel was left open overnight.
    private func revalidateLocalHalf(generation: Int) {
        guard let store = store() else { return }
        let horizon = calendar.startOfDay(for: lastLocalRead ?? Date())
        let stale = loadedDays.filter { $0 >= horizon }
        loadedDays.subtract(stale)
        lastLocalRead = Date()

        let calendar = self.calendar
        let since = self.since
        let until = self.until
        Task.detached(priority: .userInitiated) { [weak self] in
            let opening = ActivityStore.readOpening(
                store: store, calendar: calendar, since: since, until: until)
            await self?.absorb(opening: opening, generation: generation)
        }
    }

    /// Drops everything the previous account said, from memory and from disk, and asks again.
    ///
    /// **A store that belongs to the process outlives a sign-out, and a window-lived one never did.**
    /// Nothing used to have to say this: the panel closed, the store went with it, and the next
    /// account got a new one. `ActivitySpine` traded that for a panel that opens instantly, so the
    /// obligation it used to discharge by accident is discharged here on purpose.
    ///
    /// The local half is deliberately untouched. Frames and speech on this Mac are not scoped to an
    /// Omi account — they were captured whether or not anybody was signed in, and they are the whole
    /// of what a signed-out user should still be able to see.
    func forgetTheAccount() {
        ContextLog.info("Signed out; forgetting the account half of the spine", "activity")

        // **The generation advances, and that is what makes this safe rather than merely tidy.**
        // Every landing path in this store — the account read, the cached paint, the opening read,
        // a day of frames, the write-back — is already fenced on it, so one increment invalidates
        // all of them at once. Without it a read that left before the user signed out lands
        // afterwards, passes a guard comparing a generation nothing moved, and repopulates the panel
        // with the previous account's conversations. That read is in flight for as long as the
        // network takes; sign-out is a keystroke. The window is not narrow.
        //
        // It advances *without* re-opening the window, which is the difference between this and
        // `openWindow()`. Frames and speech on this Mac were captured whether or not anybody was
        // signed in, so re-reading them would be spending the whole day walk to discard nothing.
        generation &+= 1
        // The in-flight stamp belongs to the read that is now orphaned. Left set, it would refuse
        // the next account's revalidation for as long as the process lived.
        accountReadInFlight = nil

        Task { [weak self, account, cache] in
            await (account as? ActivityAccountCursor)?.forget()
            await cache?.clear()
            // Read back rather than incremented locally: the cache owns the number, and a second
            // copy of it maintained here is a second thing to get wrong.
            guard let cache, let epoch = await cache.currentEpoch() as Int? else { return }
            await MainActor.run { self?.accountCacheEpoch = epoch }
        }

        accountFeed = .unreachable
        accountSettled = false
        accountReachable = false
        accountUnreachableReason = .signedOut
        accountLocallySourced = []
        accountAnswered = []
        accountCorpusIsWhole = false
        isShowingCachedRows = false
        accountReads = 0
        accountRereads = 0
        accountRetry?.cancel()
        accountRetry = nil
        // The next sign-in is entitled to ask immediately rather than serve out a cooldown started
        // by somebody else's session.
        lastRevalidate = nil
        recompose()
    }

    /// When the panel last asked the account what changed, so a burst of mounts is one request.
    private var lastRevalidate: Date?
    /// When this Mac's half was last read, which decides how many days a revalidation re-reads.
    private var lastLocalRead: Date?

    /// The shortest gap between two revalidations.
    ///
    /// **Main's number, deliberately** — `PollingConfig.activationCooldown` is 60 seconds, for the
    /// reason its own comment gives: activation fires on every cmd-tab, and a panel that answers
    /// each one with three requests is a client that spends someone's rate limit to re-learn what it
    /// already knew. This surface has more reason to be careful than main does, not less; it was
    /// last found rendering an entire account as 429 for hours.
    nonisolated static let revalidationCooldown: TimeInterval = 60

    /// Whether enough time has passed. A free function over its inputs so the cooldown is provable
    /// without a clock — the same shape, and the same reason, as `PollingConfig`'s.
    nonisolated static func shouldRevalidate(now: Date, lastRevalidate: Date?) -> Bool {
        guard let lastRevalidate else { return true }
        return now.timeIntervalSince(lastRevalidate) >= revalidationCooldown
    }

    /// The question the host is asking: the chip, the typed term, the time bounds.
    ///
    /// Cheap enough to call on every keystroke — it only re-runs the filter pass. Moving the *time
    /// bounds* is the one change that is not cheap, because the bounds decide which days exist at
    /// all, so that path re-opens the window instead.
    func apply(kind: ActivityKind, query: String, since: Double?, until: Double?) {
        let term = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let boundsMoved = since != self.since || until != self.until
        guard boundsMoved || kind != self.kind || term != currentQuery else { return }

        self.kind = kind
        currentQuery = term
        self.since = since
        self.until = until

        guard boundsMoved, store() != nil else {
            refilter()
            return
        }
        openWindow()
    }

    /// Discards everything read for the previous time window and reads the new one.
    private func openWindow() {
        generation &+= 1
        let generation = self.generation
        screen.removeAll()
        sessions.removeAll()
        loadedDays.removeAll()
        queue.removeAll()
        queued.removeAll()
        composed = []
        accountFeed = .unreachable
        accountSettled = false
        accountReachable = false
        accountUnreachableReason = nil
        accountLocallySourced = []
        accountAnswered = []
        // The healing schedule belongs to the window that failed. A new window asks a new question,
        // and it is entitled to the whole ladder again.
        accountRetry?.cancel()
        accountRetry = nil
        accountRereads = 0
        // Hydration belongs to the window too. The reader's own cursor does not reset — the pages it
        // has already fetched are the same pages whichever window is open, because no source here is
        // fetched by date — so a re-opened window costs no re-reads, only a fresh budget.
        accountCorpusIsWhole = false
        isShowingCachedRows = false
        accountReads = 0
        corpusSettled = false
        isPreparing = store() != nil
        readFailure = nil
        loader.purge()

        refreshCacheEpoch()
        seedFromCache(generation: generation)
        readAccount(generation: generation)

        guard let store = store() else {
            capture = .opening
            recompose()
            waitForTheStore()
            return
        }
        capture = .open
        lastLocalRead = Date()
        // A watch left over from a window opened before the database existed would fire again the
        // moment it noticed one, re-opening a window this call has just opened.
        storeWatch?.cancel()
        storeWatch = nil
        let calendar = self.calendar
        let since = self.since
        let until = self.until
        Task.detached(priority: .userInitiated) { [weak self] in
            let opening = ActivityStore.readOpening(
                store: store, calendar: calendar, since: since, until: until)
            await self?.absorb(opening: opening, generation: generation)
        }
    }

    /// One read of the account for the window that is open.
    ///
    /// Runs beside the database's read, not behind it: they are two halves of one window and neither
    /// is the other's precondition. It is `Task` rather than `Task.detached` because `read` is the
    /// seam's own `async` — where it does its work is the implementation's decision, not this
    /// store's.
    ///
    /// **One read of this window at a time, and the guard is not a nicety.** Three things call this:
    /// the window opening, the healing ladder, and hydration — and hydration reads again whenever a
    /// read grew the corpus. Two overlapping reads would each grow the corpus and each start their
    /// own successor, so a second reader is not a duplicate request, it is a doubling one.
    /// - Parameter reopeningHead: send the reader's cursor back to offset zero before reading. The
    ///   only offset a forward-only walk never re-asks for, and the only one new rows arrive at.
    ///   Inside the single-flight slot rather than before it — see `revalidate`.
    private func readAccount(generation: Int, reopeningHead: Bool = false) {
        guard accountReadInFlight != generation else { return }
        accountReadInFlight = generation
        let since = self.since
        let until = self.until
        Task { [weak self, account] in
            if reopeningHead { await (account as? ActivityAccountCursor)?.refreshHead() }
            let feed = await account.read(
                since: since, until: until, limit: Self.accountCeiling)
            // Asked only when it matters, and only of a reader that has one. A reachable account has
            // no reason to give, and most readers here are previews and fakes with nothing to say.
            let reason =
                feed.reachable ? nil : await (account as? ActivityAccountDiagnosing)?.unreachableReason()
            self?.absorb(account: feed, reason: reason, generation: generation)
        }
    }

    // MARK: - The paint before the network

    /// Draws the account's last answer off disk while the real one is in flight.
    ///
    /// **Deliberately not `absorb(account:)`.** That path draws conclusions — the account answered,
    /// these sources are live, the corpus is this whole — and a copy on disk supports none of them.
    /// Everything this touches is the rows themselves; every published fact about the *account*
    /// stays exactly as `openWindow` left it, so the corner keeps saying "still counting", the
    /// unreachable copy keeps its own counsel, and the first real answer replaces these rows without
    /// having to undo a claim this made on its behalf.
    private func seedFromCache(generation: Int) {
        guard let cache else { return }
        Task.detached(priority: .userInitiated) { [weak self] in
            let cached = await cache.load()
            await self?.seed(cached: cached, generation: generation)
        }
    }

    private func seed(
        cached: (
            conversations: [ActivityAccountConversation], memories: [ActivityAccountMemory],
            tasks: [ActivityAccountTask]
        ),
        generation: Int
    ) {
        guard generation == self.generation else { return }
        // **The account outranks a copy of it — but only where it actually spoke.** On a warm
        // connection the network can beat the disk, and painting a cache over an answer that has
        // landed would put rows back the account has just said are gone. That is what the second
        // clause refuses, and an *empty* answer is covered by it: a source in `answered` said
        // "nothing", which is a fact about the account and outranks anything on disk.
        //
        // `accountSettled` alone would have been the wrong test, and wrong in the direction that
        // matters most. A read comes back settled whether it answered or not, so an offline
        // launch — the single case where a cached paint is the whole of what the user gets — would
        // have raced the disk against a failure and lost to it about half the time.
        guard accountFeed.rowCount == 0, accountFeed.answered.isEmpty else { return }
        guard !(cached.conversations.isEmpty && cached.memories.isEmpty && cached.tasks.isEmpty)
        else { return }

        accountFeed = ActivityAccountFeed(
            conversations: cached.conversations, memories: cached.memories, tasks: cached.tasks,
            // Nothing answered. This is the load-bearing half of the whole file — see above.
            answered: [])
        isShowingCachedRows = true
        ContextLog.info(
            "Account cache: painting \(cached.conversations.count) conversations, "
                + "\(cached.memories.count) memories, \(cached.tasks.count) tasks while the account "
                + "is asked", "activity")
        recompose()
    }

    /// The generation of the account read currently in flight, if there is one.
    ///
    /// Stamped with the generation rather than a bare flag so that a window opening while an old
    /// read is still out cannot be refused a read of its own — and so that the stale read, when it
    /// lands, cannot clear a flag that now belongs to somebody else.
    private var accountReadInFlight: Int?

    /// How many reads one window may spend walking the account in.
    ///
    /// The reader has its own per-source page budget and is the real bound; this is the backstop for
    /// a reader that does not — a fake, a preview, an account that grows faster than it is read —
    /// so that "read again while it keeps growing" can never be a loop without an end.
    nonisolated static let maximumAccountReads = 400

    /// What the account answered, for the window that asked.
    private func absorb(
        account feed: ActivityAccountFeed,
        reason: ActivityAccountUnreachableReason?,
        generation: Int
    ) {
        if accountReadInFlight == generation { accountReadInFlight = nil }
        guard generation == self.generation else { return }
        // **The paged reader answers with everything it has gathered, so growth is the signal.** A
        // read that added rows means there are more pages behind it and the next one is worth
        // making; a read that added none has either reached the end of the account or failed, and
        // neither improves by asking again — the healing ladder below owns the second case.
        // **A source that did not answer does not get to erase what is on screen for it.**
        //
        // This is the offline launch, and getting it wrong made the cache worthless in the one case
        // it matters most: the seed paints from disk, the failing read lands a moment later carrying
        // nothing, and replacing the feed wholesale wiped the rows the user had just been shown.
        // Which of the two landed first was a race, so the panel was empty about half the time.
        //
        // Per source rather than whole-feed, because the account fails per source — conversations
        // served while `/v3/memories` answered 503 for eight hours. What each source last said
        // stands until that source itself says otherwise. `answered` below is still the *read's*
        // own, never the merge's: the rows may be retained, but the claim about who spoke may not.
        let held = Self.retaining(rowsNotAnsweredIn: feed, from: accountFeed)
        let grew = held.rowCount > accountFeed.rowCount
        let wasFirst = !accountSettled
        // Still a cached paint for as long as any source on screen is standing on rows that came
        // off disk rather than out of an answer.
        isShowingCachedRows =
            isShowingCachedRows && feed.answered.count < ActivityAccountSource.allCases.count
        accountFeed = held
        accountSettled = true
        accountReachable = feed.reachable
        accountUnreachableReason = feed.reachable ? nil : reason
        accountLocallySourced = feed.locallySourced
        accountAnswered = feed.answered
        if feed.answered.count == ActivityAccountSource.allCases.count {
            accountRereads = 0
        } else if feed.reachable {
            // **A partial answer is still a failure for the sources that did not give one**, and
            // until the cache existed it was invisible: the feed was reachable, the ladder reset,
            // and a source that 503'd stayed missing until the user moved the window. That is the
            // exact state the backend was in when this was written — conversations serving while
            // `/v3/memories` returned 503 — so the surface would have kept showing an hours-old
            // memory list, correctly labelled and never refreshed. There is no whole-feed reason to
            // classify here (the feed reached the account), so it climbs the same ladder as the
            // failures time fixes; `accountRereads` is deliberately *not* reset, which is what keeps
            // a permanently half-dead endpoint from being polled for the life of the window.
            scheduleAccountReread(.noAnswer, generation: generation)
        } else {
            scheduleAccountReread(reason, generation: generation)
        }

        // **The corpus is whole when the last read added nothing *and* every source answered it.**
        // A read that added nothing because a source failed is not an inventory of the account — it
        // is the same partial page it was before, and the corner may not present it as final. The
        // ladder above may yet heal that source, and a read that grows again reopens this.
        accountCorpusIsWhole =
            !grew && (feed.answered.count == ActivityAccountSource.allCases.count || !feed.reachable)
        if grew, accountReads < Self.maximumAccountReads {
            accountReads += 1
            readAccount(generation: generation)
        }
        // Stated here as well as inside composition, for the reason the day walk states it there: a
        // page that adds no row recomposes nothing, and a surface that only ever settled inside
        // `recompose` would go on saying "still counting" after the last page had landed.
        updateCorpusSettled()

        // **The first answer paints; every page after it grows the list underneath the reader.**
        // Composition costs the size of the corpus rather than the size of the page that arrived, so
        // recomposing on the spot for each of a few dozen pages would spend the whole walk rebuilding
        // a list somebody is trying to read. Same bargain the day walk already makes.
        //
        // The last page is the exception: `corpusSettled` is decided above and `corpusTotal` inside
        // composition, so leaving the final page to a coalescing timer would put the settled sentence
        // on screen beside a total that is still one page short of it.
        if wasFirst || accountCorpusIsWhole {
            recompose()
        } else {
            recomposeSoon()
        }

        // **Twice per window, and both times for a reason.** The first answer is precisely the page
        // a cold launch needs to paint, so it is worth keeping the moment it lands rather than at
        // the end of a walk the user may quit before. The settled corpus is the best copy that
        // window will ever have. Every page in between is the same newest rows plus older ones the
        // cache is going to trim off anyway, so writing those would be a database write per page to
        // store nothing new.
        if wasFirst || accountCorpusIsWhole { write(feed, toCache: generation) }
    }

    /// Writes the answer back for the next cold launch to paint. Detached: this is a SQLite write on
    /// the path of a read that has already been absorbed, and nothing on screen is waiting for it.
    ///
    /// **Two fences, because they close different holes.** The generation check here refuses a write
    /// belonging to a window that has since moved; the epoch travels *into* the cache and is checked
    /// inside the actor, which is the only place that can order this write against a `clear()` that
    /// has not run yet. Checking the generation alone would leave the sign-out race exactly as it
    /// was: the guard passes, the task is spawned, sign-out clears the table, and this lands after.
    private func write(_ feed: ActivityAccountFeed, toCache generation: Int) {
        guard let cache, generation == self.generation, feed.reachable else { return }
        let epoch = accountCacheEpoch
        Task.detached(priority: .utility) { await cache.save(feed, epoch: epoch) }
    }

    /// The cache epoch this window's reads were minted under. Refreshed when a window opens and
    /// after a sign-out, which are the two moments the account under the panel can change.
    private var accountCacheEpoch = 0

    private func refreshCacheEpoch() {
        guard let cache else { return }
        Task { [weak self] in
            let epoch = await cache.currentEpoch()
            self?.accountCacheEpoch = epoch
        }
    }

    /// `feed`, with any source it neither answered for **nor carried rows for** taken from
    /// `previous`.
    ///
    /// **Both halves of that condition are load-bearing, and getting the first one alone wrong is
    /// how this was first written.** The paging reader answers with everything it has gathered, so a
    /// source absent from `answered` routinely still carries hundreds of perfectly real rows it
    /// fetched on an earlier read — that is the documented shape of a page that did not arrive, not
    /// a stale leftover, and substituting the previous feed for it threw the whole corpus away on
    /// the first partial answer. The existing spine tests caught it immediately.
    ///
    /// So what is retained is only the case the cache exists for: a source that said nothing *and*
    /// handed over nothing, where the rows on screen came off disk and the alternative is a blank
    /// panel. An **answered** source is always taken as it comes, empty included — "I hold nothing"
    /// is an answer, and the account is the authority on it.
    ///
    /// Retained rows keep whatever standing they already had; `isShowingCachedRows` is what says a
    /// paint is still a copy. Nothing here promotes them.
    nonisolated static func retaining(
        rowsNotAnsweredIn feed: ActivityAccountFeed, from previous: ActivityAccountFeed
    ) -> ActivityAccountFeed {
        guard feed.answered.count < ActivityAccountSource.allCases.count else { return feed }
        func rows<Row>(
            _ source: ActivityAccountSource, _ incoming: [Row], _ held: [Row]
        ) -> [Row] {
            if feed.answered.contains(source) { return incoming }
            return incoming.isEmpty ? held : incoming
        }
        return ActivityAccountFeed(
            conversations: rows(.conversations, feed.conversations, previous.conversations),
            memories: rows(.memories, feed.memories, previous.memories),
            tasks: rows(.tasks, feed.tasks, previous.tasks),
            answered: feed.answered,
            locallySourced: feed.locallySourced,
            memoriesBeginPastHead: feed.memoriesBeginPastHead)
    }

    // MARK: - Hydration

    /// Whether every page the account holds is in.
    ///
    /// **This is the corner's honesty, and it is not the same claim as "the read came back".** The
    /// account is read one page per source at a time and the first of those pages came back at the
    /// cap on the real account — 200 conversations, 200 memories, 200 tasks — while the shipping Omi
    /// app beside it had already paged 1,996 rows in and was still going. A surface that settled on
    /// the first answer stated `3,334 things in everything Omi has kept` over the newest two hundred
    /// of each kind. The reference draws the same sentence from `SpineHydrator.state == .whole` and
    /// keeps saying `so far · still counting` until every page is in; this is that signal.
    private var accountCorpusIsWhole = false

    /// Whether the account rows currently composed came off disk rather than off the wire.
    ///
    /// **It exists so the corner cannot call a cached number final.** An unreachable account makes
    /// `accountCorpusIsWhole` true on purpose — there are no more pages coming, so the count has
    /// genuinely stopped moving — and before there was a cache that was also honest, because an
    /// unreachable account contributed no rows at all. Now it can contribute two hundred, and
    /// "everything Omi has kept" stated over yesterday's copy is a claim nobody checked.
    private var isShowingCachedRows = false

    /// How many reads this window has spent on the account. Bounded by `maximumAccountReads`.
    private var accountReads = 0

    // MARK: - Healing

    /// When to read the account again after a read that failed for a reason that can clear on its
    /// own, and how many times.
    ///
    /// **Bounded, and the bound is the point** — the same argument `waitForTheStore` makes. A backend
    /// that stays rate-limited is a real state, and a client that keeps asking is how this Mac
    /// becomes the reason it stays that way. Four attempts spread over about eight minutes: long
    /// enough that an ordinary rate-limit window or a closed lid has passed, short enough that
    /// someone who opened the panel is still looking at it, and then it stops. The surface keeps
    /// saying what it already says, which was true when it said it.
    nonisolated static let accountRetryDelays: [Duration] = [
        .seconds(30), .seconds(60), .seconds(120), .seconds(240),
    ]

    private var accountRetry: Task<Void, Never>?
    private var accountRereads = 0

    /// Whether waiting is a plausible repair for this reason.
    ///
    /// **Only failures that time can fix come back.** A rate limit lifts, a timeout was one packet, a
    /// route returns — a panel that never asked again would stay empty long after the cause had gone.
    /// Airgap Mode, a signed-out app and a key the account refused are not like that: they need the
    /// user, so re-reading them on a timer is a poll that can only produce the same answer — and for
    /// a rejected key it would spend a freshly minted credential every attempt.
    ///
    /// `keyUnavailable` counts as healable because minting is a network call like any other: the
    /// state this ladder was written for is an account rate-limiting `POST /v1/mcp/keys` as well as
    /// the reads. Its one permanent shape — a key that was minted and could not be written to disk —
    /// costs nothing to ask again, because `MCPKeyProvisioner` refuses to re-mint for the rest of the
    /// launch and answers from memory.
    nonisolated static func healsOnItsOwn(_ reason: ActivityAccountUnreachableReason) -> Bool {
        switch reason {
        case .rateLimited, .noAnswer, .keyUnavailable: return true
        case .airgapped, .signedOut, .keyRejected: return false
        }
    }

    /// Queues the next read, if this failure is one that another read could answer differently.
    ///
    /// A reader with no diagnosis to give — `ActivityAccountAbsent`, a preview, a fake — is never
    /// re-read: "no reason" is not evidence that waiting would help.
    private func scheduleAccountReread(
        _ reason: ActivityAccountUnreachableReason?, generation: Int
    ) {
        guard let reason, Self.healsOnItsOwn(reason) else { return }
        guard accountRereads < accountRetryDelays.count else { return }
        let delay = accountRetryDelays[accountRereads]
        accountRereads += 1
        accountRetry?.cancel()
        accountRetry = Task { @MainActor [weak self] in
            try? await Task.sleep(for: delay)
            guard let self, !Task.isCancelled, generation == self.generation else { return }
            self.accountRetry = nil
            self.readAccount(generation: generation)
        }
    }

    private func absorb(opening: ActivityOpeningRead, generation: Int) {
        guard generation == self.generation else { return }
        // **Cleared on success, not only set on failure.** `openWindow` used to be the one thing
        // that reset this, which was enough while an opening read happened once per window. A
        // revalidation runs another one, so a transient failure — a database busy for a moment
        // during a migration — left the panel apologising for a read that had since succeeded, for
        // as long as the process lived.
        readFailure = opening.failed ? Self.readFailureNote : nil
        sessions = opening.sessions
        uploadLinks = opening.uploadLinks
        // One frame of an app captured today teaches the whole back catalogue of that app what its
        // bundle id is, which is what resolves an icon for a row captured before the column existed.
        AppIconCache.shared.setBundleIds(opening.bundleIds)

        var wanted = opening.days
        // Every day a session names, whether or not the screen was being captured that day: a
        // conversation with no frames behind it is still a day, and the coverage span cannot see it.
        for session in opening.sessions {
            wanted.append(calendar.startOfDay(for: Date(timeIntervalSince1970: session.startedAt)))
        }
        enqueue(days: wanted)
        recompose()
        // Nothing to read is a finished read, not a permanent spinner.
        if queue.isEmpty, active == 0 { isPreparing = false }
        updateCorpusSettled()
    }

    private func enqueue(days: [Date]) {
        let fresh = ActivityComposer.uniqued(days, by: \.self)
            .filter { !loadedDays.contains($0) && !queued.contains($0) }
        guard !fresh.isEmpty else { return }
        queued.formUnion(fresh)
        queue.append(contentsOf: fresh)
        // Newest first: the day at the top of the list is the one the user is reading.
        queue.sort(by: >)
        pump()
    }

    /// The other half of the provider above: a window opened at launch asks before the engine has a
    /// store, and nothing publishes its opening, so the only honest way to notice is to look again.
    ///
    /// **Bounded, and that is not a detail.** A store that never opens is a real state — a denied
    /// permission, a disk that will not take a database — and a poll without an end turns it into a
    /// surface that spins for the rest of the session instead of saying so. Giving up is therefore
    /// a *state* and not merely the end of a loop: `capture` becomes `.unavailable`, and the empty
    /// copy says so rather than leaving whatever it happened to be showing on screen.
    private func waitForTheStore() {
        guard storeWatch == nil else { return }
        storeWatch = Task { @MainActor [weak self] in
            for _ in 0..<Self.storeWaitAttempts {
                try? await Task.sleep(nanoseconds: UInt64(Self.storeWaitInterval * 1_000_000_000))
                guard let self else { return }
                guard self.store() != nil else { continue }
                self.storeWatch = nil
                self.openWindow()
                return
            }
            guard let self else { return }
            self.storeWatch = nil
            self.capture = .unavailable
        }
    }

    private var storeWatch: Task<Void, Never>?
    private static let storeWaitInterval: Double = 0.5

    /// How long the surface waits for a database that is not open yet, in polls of
    /// `storeWaitInterval`.
    ///
    /// **Derived from the engine's own retry cadence rather than chosen.** `Engine`'s maintenance
    /// loop re-runs `ensureStorage()` every 30 seconds, so a database whose first open threw — a
    /// migration that lost a race, a volume that was busy — opens on one of *those* ticks and never
    /// before. This wait was 60 polls: exactly 30 seconds, exactly one cadence, which is the worst
    /// possible number. Observed on a real launch: the first open threw, the wait expired, the store
    /// opened a moment later, and the panel sat empty for the rest of the session with the database
    /// live underneath it.
    ///
    /// Three retries plus slack survives two failures in a row and still ends, which is what lets
    /// the surface *say* a database is not coming rather than spin on one.
    static let storeWaitAttempts = 200

    private func pump() {
        guard let store = store() else { return }
        let calendar = self.calendar
        let generation = self.generation
        while active < Self.maximumConcurrentDayLoads, !queue.isEmpty {
            let day = queue.removeFirst()
            active += 1
            Task.detached(priority: .userInitiated) { [weak self] in
                let read = ActivityStore.readDay(day, store: store, calendar: calendar)
                await self?.absorb(day: day, read: read, generation: generation)
            }
        }
    }

    private func absorb(day: Date, read: ActivityDayRead, generation: Int) {
        // **The counter is decremented before the generation is checked.** `active` counts reads in
        // flight, which is a fact about the process rather than about the window that asked: a stale
        // read that returned without decrementing would hold a slot for the rest of the session and
        // stall the new window's walk three days in.
        active -= 1
        guard generation == self.generation else {
            pump()
            return
        }
        queued.remove(day)
        loadedDays.insert(day)
        if read.failed { readFailure = Self.readFailureNote }
        // A day with no capture still counts as read, so the list never re-queries it forever — but
        // it is not stored, so `momentCount(for:)` can still tell "read and empty" from "not read".
        if read.screen != .empty { screen[day] = read.screen }
        // **The first day landing is what ends the wait, not the last one.** The walk covers every
        // day between the oldest capture and the newest, and a list that stayed behind a spinner
        // until all of them had been read would be behind one for the whole walk — with the day the
        // user is looking at already composed and on screen underneath it.
        isPreparing = false
        if read.screen != .empty { recomposeSoon() }
        pump()
        updateCorpusSettled()
    }

    // MARK: - Readouts

    /// The hour histogram for one day, normalised to its own busiest hour.
    ///
    /// Normalised per day rather than across the corpus: the rail is a picture of *that* day's
    /// shape, and scaling it against a record-breaking day months ago would flatten every ordinary
    /// day into a straight line.
    func density(for dayID: Date) -> [Double] {
        guard let counts = screen[dayID]?.hourCounts, let peak = counts.max(), peak > 0 else {
            return Array(repeating: 0, count: 24)
        }
        return counts.map { Double($0) / Double(peak) }
    }

    /// How much screen capture a day holds — `nil` until that day has actually been read.
    ///
    /// The two absences look identical in `screen` and are not the same claim. See the note at the
    /// top of this file: `loadedDays` already knows the difference, and this is it, told.
    func momentCount(for dayID: Date) -> Int? {
        guard loadedDays.contains(dayID) else { return nil }
        return screen[dayID]?.total ?? 0
    }

    // MARK: - Composition

    /// Recompose, but at most once per coalescing window — unless there is nothing on screen yet.
    ///
    /// **First paint is never delayed.** An empty list recomposes on the spot, because the whole
    /// point of the store is that the newest day is on screen before the walk has finished. Every
    /// arrival after that is growth behind an already-readable list, and growth is worth batching.
    private func recomposeSoon() {
        guard !composed.isEmpty else {
            recompose()
            return
        }
        guard recomposeTask == nil else { return }
        recomposeTask = Task { [weak self] in
            try? await Task.sleep(for: Self.recomposeCoalescingWindow)
            guard let self, !Task.isCancelled else { return }
            self.recomposeTask = nil
            self.recompose()
        }
    }

    private func recompose() {
        recomposeTask?.cancel()
        recomposeTask = nil
        composed = ActivityComposer.compose(
            sessions: sessions, uploads: uploadLinks, account: accountFeed, screen: screen,
            calendar: calendar)
        // **The corpus is counted from the day headers, not from the rows.** A day header counts
        // every frame of the day; the rows only ever draw the sample. A total summed over the stream
        // would therefore report a five-figure day as the two hundred frames the strips could hold.
        corpusTotal = composed.isEmpty ? nil : composed.reduce(0) { $0 + $1.thingCount }
        // **Counts only, and it is the line this surface was missing.** The corner states one number
        // over four kinds, so a corner that looks wrong is unreadable without the breakdown behind
        // it: `3,334` was read as a frame count for want of this line, when it was 2,700 frames and
        // 634 account rows. None of the user's own words are in it — see `ContextLog`.
        ContextLog.info(
            "Corpus: \(composed.count) days · \(composed.reduce(0) { $0 + $1.momentCount }) moments · "
                + "\(composed.reduce(0) { $0 + $1.conversationCount }) conversations · "
                + "\(composed.reduce(0) { $0 + $1.memoryCount }) memories · "
                + "\(composed.reduce(0) { $0 + $1.taskCount }) tasks", "activity")
        updateCorpusSettled()
        refilter()
    }

    /// Whether the corner's number has stopped moving: both halves are in and the day walk is over.
    ///
    /// Called from the walk as well as from composition, because **the last day of a walk very often
    /// composes nothing.** A day whose read came back empty is absorbed without recomposing (there
    /// is no new row to draw), so a surface that only settled inside `recompose` would keep saying
    /// "still counting" for the rest of the session on any Mac whose oldest days hold no capture.
    ///
    /// **A page is not a corpus, and that is the half that was missing.** `accountSettled` says only
    /// that a read came *back*; settling on it alone let the corner state `3,334 things in everything
    /// Omi has kept` as a finished figure over the newest two hundred of each kind, while the
    /// shipping app beside it read `4,491 so far · still counting`. `accountCorpusIsWhole` is the
    /// real signal — the reference's `SpineHydrator.state == .whole`, reached when the account has
    /// no more pages to give rather than when the first of them arrived.
    private func updateCorpusSettled() {
        corpusSettled =
            accountSettled && accountCorpusIsWhole && !isShowingCachedRows && !isPreparing
            && queue.isEmpty && active == 0
    }

    private func refilter() {
        let filtered = ActivityComposer.filter(
            composed, kind: kind, query: currentQuery,
            earliest: since.map { Date(timeIntervalSince1970: $0) },
            latest: until.map { Date(timeIntervalSince1970: $0) })
        days = filtered
        matchCount = filtered.reduce(0) { $0 + $1.matchCount }
    }

    // MARK: - Reads

    /// The coverage span, the session headers and the app→bundle map — everything the surface needs
    /// before it knows which days exist.
    ///
    /// `nonisolated` and `static`: this runs on a detached task and must touch no actor state.
    /// Every read goes through `store.read`, and a throw is caught here rather than propagated,
    /// because a database being migrated underneath the window is a state to report and not one to
    /// take the surface down for.
    nonisolated static func readOpening(
        store: ContextStore, calendar: Calendar, since: Double?, until: Double?
    ) -> ActivityOpeningRead {
        do {
            let coverage = try RewindQueries.coverage(store)
            let sessions = try Queries.sessions(
                store, since: since, until: until, limit: sessionCeiling)
            let bundleIds = try RewindQueries.bundleIdsByApp(store)
            let uploadLinks = try UploadQueue.conversationLinks(store)
            return ActivityOpeningRead(
                days: enumerateDays(
                    coverage: coverage, since: since, until: until, calendar: calendar),
                sessions: sessions,
                uploadLinks: uploadLinks,
                bundleIds: bundleIds,
                failed: false)
        } catch {
            ContextLog.error("activity opening read failed (\(type(of: error)))", "activity")
            return ActivityOpeningRead(
                days: [], sessions: [], uploadLinks: [:], bundleIds: [:], failed: true)
        }
    }

    /// One day of frames, projected down to what a row needs.
    nonisolated static func readDay(
        _ day: Date, store: ContextStore, calendar: Calendar
    ) -> ActivityDayRead {
        let start = calendar.startOfDay(for: day)
        guard let end = calendar.date(byAdding: .day, value: 1, to: start) else {
            return ActivityDayRead(screen: .empty, failed: false)
        }
        do {
            let frames = try RewindQueries.frames(
                store,
                since: start.timeIntervalSince1970,
                // Half-open at the end, so the last instant of a day cannot also belong to the next
                // one and be composed into two days at once.
                until: end.timeIntervalSince1970 - 0.001)
            return ActivityDayRead(
                screen: project(frames: frames, calendar: calendar), failed: false)
        } catch {
            ContextLog.error("activity day read failed (\(type(of: error)))", "activity")
            return ActivityDayRead(screen: .empty, failed: true)
        }
    }

    /// Turns a day's frames into the day's shape. Split out from the query so the counting, the
    /// local-hour bucketing and the even sampling are all testable without a database.
    ///
    /// **Local hours, not UTC.** Bucketing on the stored epoch seconds would put the user's evening
    /// in the wrong bar for most of the world; `Calendar` is also the only thing that gets a day
    /// with a DST transition in it right.
    nonisolated static func project(frames: [RewindFrame], calendar: Calendar) -> ActivityDayScreen {
        var hourCounts = [Int](repeating: 0, count: 24)
        var drawable: [ActivityMoment] = []
        drawable.reserveCapacity(min(frames.count, sampleCeiling))

        for frame in frames {
            let moment = ActivityMoment(frame: frame)
            let hour = calendar.component(.hour, from: moment.timestamp)
            if hour >= 0, hour < 24 { hourCounts[hour] += 1 }
            drawable.append(moment)
        }

        return ActivityDayScreen(
            total: frames.count,
            hourCounts: hourCounts,
            sampled: ActivityComposer.evenlySampled(drawable, ceiling: sampleCeiling))
    }

    /// Every local day the window covers, newest first.
    ///
    /// A calendar walk rather than a `GROUP BY` over the frames: grouping means scanning the
    /// timestamp of every frame on the machine, where a day with nothing in it costs one bounded
    /// range read that comes back empty and is then never asked about again. The ceiling is what
    /// keeps the walk finite on a database whose oldest row is years old.
    nonisolated static func enumerateDays(
        coverage: ClosedRange<Double>?,
        since: Double?,
        until: Double?,
        calendar: Calendar,
        ceiling: Int = dayWalkCeiling
    ) -> [Date] {
        guard let coverage else { return [] }
        let lower = max(coverage.lowerBound, since ?? -.greatestFiniteMagnitude)
        let upper = min(coverage.upperBound, until ?? .greatestFiniteMagnitude)
        guard lower <= upper else { return [] }

        var days: [Date] = []
        var cursor = calendar.startOfDay(for: Date(timeIntervalSince1970: upper))
        let oldest = calendar.startOfDay(for: Date(timeIntervalSince1970: lower))
        while days.count < ceiling, cursor >= oldest {
            days.append(cursor)
            guard let previous = calendar.date(byAdding: .day, value: -1, to: cursor) else { break }
            cursor = previous
        }
        return days
    }
}

// MARK: - Read results

/// What the opening read came back with. A value rather than four `@Published` writes, so the whole
/// arrival is absorbed in one main-actor hop.
struct ActivityOpeningRead: Sendable {
    let days: [Date]
    let sessions: [SessionSummary]
    /// Which account conversation each uploaded session became. Read here, with the sessions it
    /// belongs to, so composition never has to reach back into the database to decide whether a row
    /// it already holds is the same talk as one the account sent.
    let uploadLinks: [Int64: [String]]
    let bundleIds: [String: String]
    /// True when the read threw. Distinct from "there was nothing", which is the whole point.
    let failed: Bool
}

/// One day of frames, as the store absorbs it.
struct ActivityDayRead: Sendable {
    let screen: ActivityDayScreen
    let failed: Bool
}
