//
//  ActivityStore.swift — what the Activity list is made of, and when it is rebuilt.
//
//  The capture database and the account already own all of this and none of it is replaced here:
//  frames stay with `RewindQueries`, speech stays with `Queries`, and conversations, memories and
//  tasks stay with the account behind `ActivityAccountReading`. This is a projection over the three,
//  and it deliberately holds no authority — no writes, no second cache, no third opinion about what
//  was captured.
//
//  **The account is read once per time window, and it is allowed to say nothing.** An unreachable
//  account is an ordinary state, not an error: the store keeps `accountReachable` so the empty copy
//  can tell "nobody answered" from "there was nothing", and the local half of the stream is composed
//  either way.
//
//  **Once per window is right for an answer and wrong for a failure.** A read that failed for a
//  reason that heals on its own — a rate limit, a timeout, no route — leaves the panel empty until
//  the user moves the window, which is a surface that stays broken long after the thing that broke
//  it has gone. So those reasons, and only those, are re-read on a bounded schedule; see
//  `scheduleAccountReread`.
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
    /// Set when a read threw. **Not the same as an empty day**, and the surface has to be able to
    /// say which: an empty list under a failed read is not an answer about the machine.
    @Published private(set) var readFailure: String?

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
    nonisolated static let accountCeiling = 300

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
    private let calendar: Calendar
    /// The healing schedule, injectable so a test can prove the ladder without spending it.
    private let accountRetryDelays: [Duration]

    /// Composed, unfiltered. The filter pass reads this and never mutates it.
    private var composed: [ActivityDay] = []
    /// Per-day screen capture, keyed by the local start of the day.
    private var screen: [Date: ActivityDayScreen] = [:]
    private var sessions: [SessionSummary] = []
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

    init(
        store: @escaping () -> ContextStore?,
        account: ActivityAccountReading = ActivityAccountAbsent(),
        calendar: Calendar = .current,
        accountRetryDelays: [Duration] = ActivityStore.accountRetryDelays
    ) {
        self.store = store
        self.account = account
        self.calendar = calendar
        self.accountRetryDelays = accountRetryDelays
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
        self.calendar = calendar
        self.accountRetryDelays = Self.accountRetryDelays
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

    /// Begins the opening read, once. Safe to call from `.task` on every appearance.
    func start() {
        guard !didStart else { return }
        didStart = true
        openWindow()
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
        // The healing schedule belongs to the window that failed. A new window asks a new question,
        // and it is entitled to the whole ladder again.
        accountRetry?.cancel()
        accountRetry = nil
        accountRereads = 0
        corpusSettled = false
        isPreparing = store() != nil
        readFailure = nil
        loader.purge()

        readAccount(generation: generation)

        guard let store = store() else {
            recompose()
            waitForTheStore()
            return
        }
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
    private func readAccount(generation: Int) {
        let since = self.since
        let until = self.until
        Task { [weak self, account] in
            let feed = await account.read(
                since: since, until: until, limit: Self.accountCeiling)
            // Asked only when it matters, and only of a reader that has one. A reachable account has
            // no reason to give, and most readers here are previews and fakes with nothing to say.
            let reason =
                feed.reachable ? nil : await (account as? ActivityAccountDiagnosing)?.unreachableReason()
            self?.absorb(account: feed, reason: reason, generation: generation)
        }
    }

    /// What the account answered, for the window that asked.
    private func absorb(
        account feed: ActivityAccountFeed,
        reason: ActivityAccountUnreachableReason?,
        generation: Int
    ) {
        guard generation == self.generation else { return }
        accountFeed = feed
        accountSettled = true
        accountReachable = feed.reachable
        accountUnreachableReason = feed.reachable ? nil : reason
        if feed.reachable {
            accountRereads = 0
        } else {
            scheduleAccountReread(reason, generation: generation)
        }
        recompose()
    }

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
        if opening.failed { readFailure = Self.readFailureNote }
        sessions = opening.sessions
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
    /// surface that spins for the rest of the session instead of saying so.
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
            self?.storeWatch = nil
        }
    }

    private var storeWatch: Task<Void, Never>?
    private static let storeWaitInterval: Double = 0.5
    private static let storeWaitAttempts = 60

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
            sessions: sessions, account: accountFeed, screen: screen, calendar: calendar)
        // **The corpus is counted from the day headers, not from the rows.** A day header counts
        // every frame of the day; the rows only ever draw the sample. A total summed over the stream
        // would therefore report a five-figure day as the two hundred frames the strips could hold.
        corpusTotal = composed.isEmpty ? nil : composed.reduce(0) { $0 + $1.thingCount }
        updateCorpusSettled()
        refilter()
    }

    /// Whether the corner's number has stopped moving: both halves are in and the day walk is over.
    ///
    /// Called from the walk as well as from composition, because **the last day of a walk very often
    /// composes nothing.** A day whose read came back empty is absorbed without recomposing (there
    /// is no new row to draw), so a surface that only settled inside `recompose` would keep saying
    /// "still counting" for the rest of the session on any Mac whose oldest days hold no capture.
    private func updateCorpusSettled() {
        corpusSettled = accountSettled && !isPreparing && queue.isEmpty && active == 0
    }

    private func refilter() {
        let filtered = ActivityComposer.filter(
            composed, kind: kind, query: currentQuery,
            earliest: since.map { Date(timeIntervalSince1970: $0) })
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
            return ActivityOpeningRead(
                days: enumerateDays(
                    coverage: coverage, since: since, until: until, calendar: calendar),
                sessions: sessions,
                bundleIds: bundleIds,
                failed: false)
        } catch {
            ContextLog.error("activity opening read failed (\(type(of: error)))", "activity")
            return ActivityOpeningRead(days: [], sessions: [], bundleIds: [:], failed: true)
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
    let bundleIds: [String: String]
    /// True when the read threw. Distinct from "there was nothing", which is the whole point.
    let failed: Bool
}

/// One day of frames, as the store absorbs it.
struct ActivityDayRead: Sendable {
    let screen: ActivityDayScreen
    let failed: Bool
}
