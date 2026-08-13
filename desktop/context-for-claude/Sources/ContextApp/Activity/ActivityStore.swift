//
//  ActivityStore.swift — what the Activity list is made of, and when it is rebuilt.
//
//  The capture database already owns all of this and none of it is replaced here: frames stay with
//  `RewindQueries`, speech stays with `Queries`. This is a projection over the two, and it
//  deliberately holds no authority — no writes, no second cache, no third opinion about what was
//  captured.
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
    private(set) var kind: ActivityKind = .everything

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
    private let calendar: Calendar

    /// Composed, unfiltered. The filter pass reads this and never mutates it.
    private var composed: [ActivityDay] = []
    /// Per-day screen capture, keyed by the local start of the day.
    private var screen: [Date: ActivityDayScreen] = [:]
    private var sessions: [SessionSummary] = []

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

    init(store: @escaping () -> ContextStore?, calendar: Calendar = .current) {
        self.store = store
        self.calendar = calendar
    }

    /// A store with its answer already in it, for previews and tests. Takes no store, so nothing it
    /// does can touch the user's database.
    init(days: [ActivityDay], calendar: Calendar = .current) {
        self.store = { nil }
        self.calendar = calendar
        self.composed = days
        self.days = days
        self.matchCount = days.reduce(0) { $0 + $1.matchCount }
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
        screen.removeAll()
        sessions.removeAll()
        loadedDays.removeAll()
        queue.removeAll()
        queued.removeAll()
        composed = []
        isPreparing = store() != nil
        readFailure = nil
        loader.purge()

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
            await self?.absorb(opening: opening)
        }
    }

    private func absorb(opening: ActivityOpeningRead) {
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
        while active < Self.maximumConcurrentDayLoads, !queue.isEmpty {
            let day = queue.removeFirst()
            active += 1
            Task.detached(priority: .userInitiated) { [weak self] in
                let read = ActivityStore.readDay(day, store: store, calendar: calendar)
                await self?.absorb(day: day, read: read)
            }
        }
    }

    private func absorb(day: Date, read: ActivityDayRead) {
        active -= 1
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
        composed = ActivityComposer.compose(sessions: sessions, screen: screen, calendar: calendar)
        refilter()
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
