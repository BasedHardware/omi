//
//  SearchResultsModel.swift — what the second panel is showing, and where it came from.
//
//  The panel draws three things it does not compute: the moments, the totals, and the facets (which
//  sites and which apps are actually in the answer). All three come from one read, because they are
//  three views of the same rows — deriving the facets from a *second* query is how a filter row ends
//  up offering an app that none of the results below it belong to.
//
//  **Two halves, one answer.** A read asks the screen index and the speech index the same question,
//  with the same time bounds and the same sanitized terms, and `SearchRanking` merges them into one
//  ordered page. The alternative — two sections, each with its own order — was rejected because it
//  makes the reader do the merge: "what did we decide about pricing" is answered by the sentence in
//  which it was decided *and* by the spreadsheet it was decided over, and which of those is the
//  better answer is a question about the query, not about which table the row is in.
//

import AppKit
import ContextCore
import SwiftUI

// MARK: - Filters

/// The time chips, in the order the reference puts them.
enum SearchTimeFilter: String, CaseIterable, Identifiable, Sendable {
    /// Not a chip — the state with no time filter on, which is what pressing a lit chip returns to.
    case anytime
    case today
    case yesterday
    case lastWeek
    case pickADate

    var id: String { rawValue }

    /// The chips that are actually drawn. `anytime` is a state, not a control: a row where one chip
    /// is always lit and one of them means "no filter" reads as a segmented control, which this is
    /// not — any chip can be pressed again to turn it off.
    static let chips: [SearchTimeFilter] = [.today, .yesterday, .lastWeek, .pickADate]

    var title: String {
        switch self {
        case .anytime: return "Anytime"
        case .today: return "today"
        case .yesterday: return "yesterday"
        case .lastWeek: return "last week"
        case .pickADate: return "Pick a date…"
        }
    }

    var systemImage: String {
        switch self {
        case .pickADate: return "calendar"
        default: return "clock"
        }
    }

    /// The window this filter selects, or nil for "no bound".
    ///
    /// Takes `now`, `calendar` and the picked day rather than reading them, so the boundaries are
    /// assertable on a fixed date instead of on whichever day the suite happens to run.
    func range(
        now: Date = Date(), calendar: Calendar = .current, pickedDate: Date? = nil
    ) -> (since: Double?, until: Double?) {
        func day(_ date: Date) -> (Double?, Double?) {
            let start = calendar.startOfDay(for: date)
            let end = calendar.date(byAdding: .day, value: 1, to: start) ?? start.addingTimeInterval(86_400)
            // Half-open at the end, so the last instant of a day cannot also belong to the next one.
            return (start.timeIntervalSince1970, end.timeIntervalSince1970 - 0.001)
        }
        switch self {
        case .anytime:
            return (nil, nil)
        case .today:
            return day(now)
        case .yesterday:
            return day(calendar.date(byAdding: .day, value: -1, to: now) ?? now)
        case .lastWeek:
            let start = calendar.date(byAdding: .day, value: -7, to: calendar.startOfDay(for: now))
            return (start?.timeIntervalSince1970, nil)
        case .pickADate:
            return day(pickedDate ?? now)
        }
    }
}

/// One app in the `FILTER BY APP` row.
struct SearchAppFacet: Identifiable, Equatable, Sendable {
    let name: String
    let bundleId: String?
    var id: String { name }
}

// MARK: - Moving through the grid

/// One arrow key, as a direction on the results grid.
///
/// A direction rather than the `±1` this used to take, because the results are a **grid** and the
/// old signature could not describe one: with three cards across, "the card below this one" is
/// three along, and a single delta collapses ↓ and → onto the same movement. That is what the
/// surface shipped — pressing ↓ walked the highlight *sideways* across the first row — and it is
/// invisible in a delta and obvious in a direction.
enum SearchGridStep: Equatable, Sendable {
    case up
    case down
    case left
    case right
}

// MARK: - The model

@MainActor
final class SearchResultsModel: ObservableObject {

    /// How many cards the grid draws. Three across, four rows deep, which is what the panel can show
    /// before scrolling stops being a scroll and becomes a second surface.
    nonisolated static let pageSize = 60
    /// How many chips a facet row offers. Past this the row is a list, and a list of everything the
    /// user has ever opened is not a filter.
    nonisolated static let facetLimit = 12

    /// What the bar says when the read itself failed.
    ///
    /// One sentence, and deliberately not the underlying error: see the `catch` in `reload`. It says
    /// what happened and what it is not — a search that ran and found nothing — because those two
    /// license completely different conclusions and the panel's empty state cannot tell them apart.
    nonisolated static let readFailureNote =
        "I couldn't read this Mac's capture just now, so this is not an empty answer — try again."

    @Published private(set) var moments: [SearchMoment] = []
    /// Every match, not just the page above. The number the panel says out loud.
    @Published private(set) var totalCount = 0
    @Published private(set) var websites: [String] = []
    @Published private(set) var apps: [SearchAppFacet] = []
    @Published private(set) var loadError: String?

    @Published private(set) var time: SearchTimeFilter = .anytime
    @Published private(set) var website: String?
    @Published private(set) var app: String?

    /// Whether the three filter rows are open under the header.
    ///
    /// **Closed is the resting state, and that is the whole of a defect this surface shipped with.**
    /// The filter block is three full-width sections — time chips, a site row, a row of 46 pt app
    /// icons — and it sat above the results inside a panel whose ceiling is
    /// `SearchLayout.maximumResultsBodyHeight`. It ate very nearly all of it. So the answer to a
    /// query was: a screenful of filter furniture, the word `RESULTS`, one row of cards, and the
    /// next row sliced by the panel's edge. A person who had just searched their own machine saw
    /// three of their hundred-and-nine screenshots without scrolling, under a stack of controls they
    /// had not asked for — which is exactly the report this closed: the results "look dull", they
    /// should "already pop up with screens".
    ///
    /// Closing it by default is not hiding the filters; it is putting them one press behind the
    /// thing they filter. The header stays visible, says `Filter`, carries a chevron, and — when a
    /// chip really is lit — names the narrowing in words (`hiddenFilterSummary`), so a collapsed
    /// block can never be a filter the user cannot see acting on an answer they can.
    @Published private(set) var isShowingFilters = false
    @Published var pickedDate = Date() {
        didSet { if time == .pickADate { reload() } }
    }

    /// The result the keyboard is on, by `SearchMoment.id`, or nil when the keyboard is still in the
    /// field.
    ///
    /// **Nil is the resting state and has to be**, because the text field owns the first responder
    /// for the whole life of this surface (see `FocusingTextField`): the user is typing, and Return
    /// means "ask again". Only once they have stepped into the results with ↓ does Return mean "open
    /// this one" — which is exactly the Spotlight bargain, and the only way a grid whose cards can
    /// never take focus is reachable from the keyboard at all.
    ///
    /// Stored by id rather than by index because the answer under it is live: a keystroke re-reads
    /// both halves, and an index would silently point at a different moment afterwards.
    @Published private(set) var selection: SearchMoment.ID?

    /// What was last typed, trimmed.
    ///
    /// Published rather than private, because the panel's copy depends on it: a panel with nothing
    /// typed into it has not been asked anything, and saying so is `SearchIntent`'s job. Derived
    /// state would not do — an intent read off an unpublished field changes without telling SwiftUI,
    /// and on a store-less model (previews, the render harness, tests) nothing else would publish in
    /// its place, so the panel would keep drawing the previous question's copy.
    @Published private(set) var query = ""

    let loader = FrameLoader()

    /// **The capture database, asked for on every read rather than captured once.**
    ///
    /// A provider and not a `ContextStore?`. The store opens lazily on the engine's own queue, so it
    /// is routinely `nil` for the second or two after launch — and a surface handed that `nil` once,
    /// at construction, holds it for as long as it lives: a panel summoned in that second renders as
    /// permanently empty, with no error to explain it and no path back. Asked for on every read
    /// instead, so the answer is always the store that exists *now*.
    private let store: () -> ContextStore?

    /// Whether this panel session has already reported that results were shown.
    ///
    /// **An instance flag is the session**, and it is one because of how `SearchBarWindow` is built:
    /// `dismiss()` drops `current` and the next `present()` rebuilds the window, its view, and this
    /// model — so a new model *is* a new panel, and a panel merely brought forward keeps the one it
    /// had. Nothing has to reset it, which is the reason it cannot drift out of step.
    private var hasReportedTheSearchSurface = false

    init(store: @escaping () -> ContextStore?) {
        self.store = store
    }

    /// A model with its answer already in it, for previews, the render harness and tests. Takes no
    /// store, so nothing it does can touch the user's database.
    init(
        moments: [SearchMoment],
        totalCount: Int? = nil,
        websites: [String] = [],
        apps: [SearchAppFacet] = [],
        query: String = ""
    ) {
        self.store = { nil }
        self.moments = moments
        self.totalCount = totalCount ?? moments.count
        self.websites = websites
        self.apps = apps
        self.query = query.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: What the panel is answering

    /// Whether a filter is narrowing the answer. `anytime` with no site and no app is the resting
    /// state, which is not a question.
    var isNarrowed: Bool { time != .anytime || website != nil || app != nil }

    /// Browsing, filtering or searching — the state the panel's copy is written against.
    var intent: SearchIntent { .of(query: query, isNarrowed: isNarrowed) }

    // MARK: Input

    /// **Run this question now**, whatever the field last said — the opening read and the Return key.
    ///
    /// Separate from `search` because `search` is a keystroke de-duplicator, and its "identical text
    /// is a no-op" guard is wrong for both of this method's callers:
    ///
    /// - *Opening.* The query starts empty and the bar opens empty, so `search("")` matched and
    ///   returned without ever reading the database. The panel then drew the empty state on every
    ///   open — on a Mac with a hundred thousand captures — which is the other half of the same
    ///   defect the empty-query copy fixes. Both query layers are explicit that an empty query means
    ///   "the newest captures", and this is the call that asks for them.
    /// - *Return.* The bar searches as you type, so Return is not what runs the query — it re-runs
    ///   it, which is worth something precisely because capture is live: the answer to "what was I
    ///   just looking at" is a few seconds older than the keystroke that asked it. "The same question
    ///   again" is a question, so it must not be de-duplicated away.
    func ask(_ text: String) {
        query = text.trimmingCharacters(in: .whitespacesAndNewlines)
        // Asked before the reload, because the reload is what closes over it: `reload()` returns
        // early when the capture database is not open yet, leaving `totalCount` holding the
        // *previous* question's answer. Reporting then would bucket one query's result count
        // against another's — and a search that never ran is not a search. The emit used to live
        // inside `reload()` past this same guard, so this keeps the behaviour it always had.
        let storeWasOpen = store() != nil
        reload()
        guard storeWasOpen else { return }
        report(Self.searchEvents(
            query: query, resultCount: totalCount, isFirstOfSession: !hasReportedTheSearchSurface))
    }

    /// **What a committed question reports** — nothing at all for an empty one.
    ///
    /// Pure, and separated from the emit, because the rule it states is the whole of a defect that
    /// shipped: `cfc_search_ran` came from `reload()`, which runs on **every keystroke** (there is no
    /// debounce), once per panel open with an *empty* query from `SearchBarView.onAppear`, and again
    /// on every filter click. The series counted typing, opening and filtering, and called all three
    /// searches. A question is a question when it is committed, and an empty field is not one.
    ///
    /// `.search` rides along on the first of them rather than on the panel opening, and that is the
    /// distinction `Surface` now draws: `.activity` is the window going up, `.search` is results
    /// being shown in it. Once per panel session, so it counts sessions that searched rather than
    /// letters typed.
    ///
    /// `nonisolated` because it reads nothing but its arguments — which is the property that makes
    /// it assertable at all, from a suite that has no panel and no main actor to run one on.
    ///
    /// - Parameter isFirstOfSession: whether results have already been reported for this panel.
    nonisolated static func searchEvents(
        query: String, resultCount: Int, isFirstOfSession: Bool
    ) -> [AnalyticsEvent] {
        guard !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return [] }
        var events: [AnalyticsEvent] = []
        // `.inAppPill`: the results body is only ever reached from a control inside the panel that
        // is already open — the field itself, or a query another surface handed it.
        if isFirstOfSession { events.append(.surfaceOpened(.search, via: .inAppPill)) }
        // Bucketed, and never the query. Read after the answer settles so a zero-result search —
        // the one worth knowing about — is counted as a search rather than as nothing happening.
        events.append(.searchRan(resultCountBucket: AnalyticsEvent.CountBucket(resultCount)))
        return events
    }

    private func report(_ events: [AnalyticsEvent]) {
        guard !events.isEmpty else { return }
        hasReportedTheSearchSurface = true
        for event in events { ContextAnalytics.record(event) }
    }

    /// A new query. Cheap to call on every keystroke: identical text is a no-op.
    func search(_ text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed != query else { return }
        query = trimmed
        reload()
    }

    func select(time value: SearchTimeFilter) {
        time = value
        reload()
    }

    func select(website value: String?) {
        website = value
        reload()
    }

    func select(app value: String?) {
        app = value
        reload()
    }

    /// Open or close the filter block. Does not re-read: which controls are on screen is not a
    /// question about the answer.
    func toggleFilters() {
        isShowingFilters.toggle()
    }

    /// What the header says about a narrowing the closed block is no longer showing, or nil when
    /// there is nothing hidden — the block is open, or nothing is lit.
    ///
    /// This is what makes closing the block safe. A lit chip changes the answer, so a collapsed
    /// block that swallowed one would leave the panel reporting a narrowed count with nothing on
    /// screen to explain it, and no way to tell a filtered answer from an empty machine.
    var hiddenFilterSummary: String? {
        guard !isShowingFilters else { return nil }
        return SearchCopy.filterSummary(time: time, website: website, app: app)
    }

    // MARK: Which result the keyboard is on

    /// The moment Return would open, or nil while the keyboard is still in the field.
    var selectedMoment: SearchMoment? {
        guard let selection else { return nil }
        return moments.first { $0.id == selection }
    }

    /// Steps the selection through the page — what the four arrow keys do.
    ///
    /// **Reading order was the first design and the grid outgrew it.** The original rule stepped
    /// ±1 on ↓/↑ and offered ← and → to nobody, on the reasoning that the grid's reading order *is*
    /// the ranking order, so "next" means "the next best answer" and one pair of keys covers the
    /// page. That reasoning is still true about the *order*; what it got wrong is the *key*. With
    /// three cards across, ↓ moved the highlight one card to the right, and a key labelled "down"
    /// that visibly moves sideways reads as broken rather than as clever — the more so now that
    /// this panel opens on the grid rather than on the filter block. So ↓/↑ move by a row and ←/→
    /// move along the ranking, which is the arrangement every macOS icon grid already teaches.
    ///
    /// **← and → still belong to the query until the keyboard is in the grid.** That was the real
    /// objection to offering them, and it is answered by state rather than by omission: with nothing
    /// selected this returns `false` and the field moves the insertion point exactly as before, so
    /// typing and editing a query are untouched. Only once ↓ has stepped into the results do they
    /// mean anything here.
    ///
    /// - Returns: whether the results took the key. `false` means "not mine" — the caller must let
    ///   the field have it, or ← and → would be dead in the one place they are most used.
    @discardableResult
    func move(_ step: SearchGridStep) -> Bool {
        guard !moments.isEmpty else { return false }
        let index = selection.flatMap { current in moments.firstIndex { $0.id == current } }
        guard index != nil || (step != .left && step != .right) else { return false }
        let landing = Self.destination(
            of: step, from: index, count: moments.count, columns: Self.gridColumns)
        selection = landing.map { moments[$0].id }
        return true
    }

    /// How many cards a row holds, as the navigation sees it. Read off the layout rather than
    /// restated, so a grid that becomes two or four across cannot leave ↓ stepping by three.
    nonisolated static var gridColumns: Int { SearchLayout.resultColumns }

    /// **Where an arrow key lands** — the whole of 2-D navigation, as arithmetic.
    ///
    /// Static and pure so every case is a test rather than something to try by hand on a page that
    /// happens to be twelve cards long: the ones that break in the wild are the ragged last row, the
    /// page shorter than one row, and the empty page, none of which anybody thinks to open.
    ///
    /// `nil` means **the keyboard is back in the field**, which is a real destination and not a
    /// failure — see `.left` below.
    ///
    /// Clamped rather than wrapping. Wrapping at the bottom of a 60-card page puts the selection back
    /// at the top with no scroll to explain it, which reads as the key having lost the selection.
    nonisolated static func destination(
        of step: SearchGridStep, from index: Int?, count: Int, columns: Int
    ) -> Int? {
        guard count > 0, columns > 0 else { return nil }
        let last = count - 1
        guard let index, (0...last).contains(index) else {
            // The first press steps *into* the results from the field: down enters at the best
            // answer, up enters at the last one, which is what an "end" key press means to a list.
            // ← and → do not enter at all — with no card to move from they are still the query's.
            switch step {
            case .down: return 0
            case .up: return last
            case .left, .right: return nil
            }
        }
        switch step {
        case .down:
            // Clamped to the last card and not to the last *full* row: on a ragged final row ↓ from
            // the row above would otherwise do nothing, and a key that appears dead at the bottom of
            // the page is how a user concludes the grid is not navigable at all.
            return min(index + columns, last)
        case .up:
            // Held at the top row rather than stepping out. The way out is ←, and it has to be only
            // one key: if ↑ also left the grid then a second ↑ would re-enter at the *last* card —
            // the "up from nothing" rule above — and the keyboard would teleport to the bottom of
            // the page for pressing one key twice.
            return index < columns ? index : index - columns
        case .left:
            // Out of the first card is out of the grid, back to the query. One exit, at the one
            // place where "the thing before this" really is the search field: the top-left corner.
            // Every other ← is the previous card in the ranking, which is also the previous row's
            // last card at a row start — the same flow a macOS icon grid has.
            return index == 0 ? nil : index - 1
        case .right:
            return min(index + 1, last)
        }
    }

    /// Puts the keyboard back in the field with nothing selected — what a new question means, and
    /// what the surface rests at.
    func clearSelection() {
        selection = nil
    }

    // MARK: Loading

    /// Reads both halves, the totals and the facets in one go.
    ///
    /// The app and website filters are applied *after* the read rather than in SQL, and deliberately:
    /// the facets offered are the ones present in this query's answer, so narrowing by one of them can
    /// only ever remove rows the user can already see. Pushing them into the query would mean the chip
    /// row and the grid were answering two different questions.
    ///
    /// **A site or app chip narrows to screens.** Both are claims about a window, and a spoken line
    /// was not in one — so lighting either one drops speech from the answer rather than keeping lines
    /// that cannot satisfy the filter. That is why the facets are derived from the screen half alone:
    /// a chip the conversation rows could never match must not be offered as if they could.
    func reload() {
        guard let store = store() else {
            waitForTheStore()
            return
        }
        storeWatch?.cancel()
        storeWatch = nil
        let bounds = time.range(pickedDate: pickedDate)
        do {
            let seen = try RewindQueries.search(
                store, matching: query, since: bounds.since, until: bounds.until,
                limit: Self.pageSize)
            // Why the frame text is a second read rather than more columns on the first: see
            // `ScreenSearchQueries.frameText`. It is one index seek per card of the page already
            // returned, and it is what lets a card say why it matched.
            let text = try ScreenSearchQueries.frameText(store, ids: seen.frames.map(\.id))
            let screens = seen.frames.map { SearchMoment(frame: $0, snippet: text[$0.id]) }

            let spoken = try ScreenSearchQueries.conversations(
                store, matching: query, since: bounds.since, until: bounds.until,
                limit: Self.pageSize)
            let conversations = spoken.lines.map(SearchMoment.init(line:))

            websites = Self.facetWebsites(screens)
            apps = Self.facetApps(screens)
            // A filter left standing that this answer has nothing for would show an empty grid with a
            // lit chip and no way to tell which of the two was wrong.
            if let website, !websites.contains(website) { self.website = nil }
            if let app, !apps.contains(where: { $0.name == app }) { self.app = nil }

            let narrowedBySource = self.website != nil || self.app != nil
            let visibleScreens = screens.filter { moment in
                (self.website.map { moment.source == $0 } ?? true)
                    && (self.app.map { moment.appName == $0 } ?? true)
            }
            moments = SearchRanking.merge(
                screens: visibleScreens,
                conversations: narrowedBySource ? [] : conversations,
                query: query,
                limit: Self.pageSize)
            // The unfiltered total when nothing is narrowing it, and the narrowed count when
            // something is: "109 results" over a grid of four is a lie either way round. Unnarrowed,
            // it is both halves added up — the page is one answer, so its count has to be too.
            totalCount = narrowedBySource ? visibleScreens.count : seen.total + spoken.total
            // **Nothing is reported from here**, and that is the fix rather than an omission: this
            // runs on every keystroke, on every filter click, and once per panel open with an empty
            // query. See `searchEvents`, which `ask(_:)` is the one caller of.
            // A selection the new answer no longer contains is a keyboard target that is not on
            // screen — Return would open a card the user cannot see. Kept when the moment survived
            // the re-read, because a chip that merely reorders the page should not cost somebody
            // their place in it.
            if let selection, !moments.contains(where: { $0.id == selection }) { self.selection = nil }
            loadError = nil
            // Said out loud, so nothing outside this panel has to run a second search to find out
            // what this one answered. The tutorial's search beat is the caller that matters: its gate
            // is "a real question really came back with something", and this is the only place in the
            // app that can report it without asking the database again.
            SearchPanelWatch.report(.answered(query: query, results: moments.count))
        } catch {
            moments = []
            totalCount = 0
            websites = []
            apps = []
            selection = nil
            loadError = Self.readFailureNote
            // **The error's *type*, never the error.** A GRDB `DatabaseError` renders its failing
            // statement and its bound arguments, and one of those arguments is the FTS expression
            // built from what the user typed — so interpolating the error, which this line used to
            // do, wrote the user's own question into the unified log. The same reasoning keeps it out
            // of `loadError`: a note that spills SQL at somebody is not an explanation either.
            ContextLog.error("search read failed (\(type(of: error)))", "search")
            // Reported too, at zero. A read that failed is not an answer, and an observer left
            // waiting on a report that never came would be waiting for something that cannot arrive —
            // `readFailureNote` is what tells the *user* the difference, and zero results is what
            // stops anything downstream claiming a find.
            SearchPanelWatch.report(.answered(query: query, results: 0))
        }
    }

    /// **Reads again once capture has a database to read.**
    ///
    /// The other half of the provider above. A panel summoned before the store is open asks and gets
    /// nothing; without this it would sit on an empty body until the user typed, which is the first
    /// thing anybody sees. Nothing publishes the store's opening — `Engine.contextStore` is a
    /// computed property over the capture stack's own queue — so this looks, briefly and at a cadence
    /// nobody can perceive.
    ///
    /// **Bounded, and that is not a detail.** A store that never opens is a real state (a denied
    /// grant, a disk that will not take the file), and an unbounded retry against it is a loop that
    /// outlives the reason for it. Thirty seconds is comfortably longer than the open takes and short
    /// enough that a machine where it will not happen stops asking.
    private func waitForTheStore() {
        guard storeWatch == nil else { return }
        storeWatch = Task { @MainActor [weak self] in
            for _ in 0..<Self.storeWaitAttempts {
                try? await Task.sleep(nanoseconds: UInt64(Self.storeWaitInterval * 1_000_000_000))
                guard !Task.isCancelled, let self else { return }
                guard self.store() != nil else { continue }
                self.storeWatch = nil
                self.reload()
                return
            }
            self?.storeWatch = nil
        }
    }

    private var storeWatch: Task<Void, Never>?
    private static let storeWaitInterval: Double = 0.5
    private static let storeWaitAttempts = 60

    /// Distinct hosts in the answer, most frequent first — the sites the user actually spent the
    /// query's time on, rather than whichever one happened to be captured last.
    nonisolated static func facetWebsites(_ moments: [SearchMoment], limit: Int = facetLimit) -> [String] {
        rank(moments.compactMap { SearchSource.domain(in: $0.title) }, limit: limit)
    }

    nonisolated static func facetApps(_ moments: [SearchMoment], limit: Int = facetLimit) -> [SearchAppFacet] {
        let names = rank(moments.map(\.appName), limit: limit)
        // The newest bundle id seen for each name, which is the one that resolves an icon today.
        var bundles: [String: String] = [:]
        for moment in moments where bundles[moment.appName] == nil {
            bundles[moment.appName] = moment.bundleId
        }
        return names.map { SearchAppFacet(name: $0, bundleId: bundles[$0]) }
    }

    /// Most frequent first, ties broken by first appearance so the row is stable between reads.
    nonisolated private static func rank(_ values: [String], limit: Int) -> [String] {
        var counts: [String: Int] = [:]
        var order: [String] = []
        for value in values where !value.isEmpty {
            if counts[value] == nil { order.append(value) }
            counts[value, default: 0] += 1
        }
        return order
            .enumerated()
            .sorted { left, right in
                let a = counts[left.element] ?? 0
                let b = counts[right.element] ?? 0
                return a == b ? left.offset < right.offset : a > b
            }
            .prefix(limit)
            .map(\.element)
    }
}
