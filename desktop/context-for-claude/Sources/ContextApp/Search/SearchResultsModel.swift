//
//  SearchResultsModel.swift — what the second panel is showing, and where it came from.
//
//  The panel draws three things it does not compute: the moments, the totals, and the facets (which
//  sites and which apps are actually in the answer). All three come from one read, because they are
//  three views of the same rows — deriving the facets from a *second* query is how a filter row ends
//  up offering an app that none of the results below it belong to.
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

// MARK: - The model

@MainActor
final class SearchResultsModel: ObservableObject {

    /// How many cards the grid draws. Three across, four rows deep, which is what the panel can show
    /// before scrolling stops being a scroll and becomes a second surface.
    nonisolated static let pageSize = 60
    /// How many chips a facet row offers. Past this the row is a list, and a list of everything the
    /// user has ever opened is not a filter.
    nonisolated static let facetLimit = 12

    @Published private(set) var moments: [SearchMoment] = []
    /// Every match, not just the page above. The number the panel says out loud.
    @Published private(set) var totalCount = 0
    @Published private(set) var websites: [String] = []
    @Published private(set) var apps: [SearchAppFacet] = []
    @Published private(set) var loadError: String?

    @Published private(set) var time: SearchTimeFilter = .anytime
    @Published private(set) var website: String?
    @Published private(set) var app: String?
    @Published var pickedDate = Date() {
        didSet { if time == .pickADate { reload() } }
    }

    /// What was last typed, trimmed.
    ///
    /// Published rather than private, because the panel's copy depends on it: a panel with nothing
    /// typed into it has not been asked anything, and saying so is `SearchIntent`'s job. Derived
    /// state would not do — an intent read off an unpublished field changes without telling SwiftUI,
    /// and on a store-less model (previews, the render harness, tests) nothing else would publish in
    /// its place, so the panel would keep drawing the previous question's copy.
    @Published private(set) var query = ""

    let loader = FrameLoader()

    private let store: ContextStore?

    init(store: ContextStore?) {
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
        self.store = nil
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

    /// **The first read, when the surface opens.**
    ///
    /// Separate from `search` because `search` is a keystroke de-duplicator, and its "identical text
    /// is a no-op" guard is exactly wrong for the opening read: the query starts empty, the bar opens
    /// empty, so `search("")` matched and returned without ever reading the database. The panel then
    /// drew the empty state on every open — on a Mac with a hundred thousand captures — which is the
    /// other half of the same defect the empty-query copy fixes. `RewindQueries.search` is explicit
    /// that an empty query means "the newest captures", and this is the call that asks for them.
    func start(_ text: String) {
        query = text.trimmingCharacters(in: .whitespacesAndNewlines)
        reload()
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

    // MARK: Loading

    /// Reads the page, the total and the facets in one go.
    ///
    /// The app and website filters are applied *after* the read rather than in SQL, and deliberately:
    /// the facets offered are the ones present in this query's answer, so narrowing by one of them can
    /// only ever remove rows the user can already see. Pushing them into the query would mean the chip
    /// row and the grid were answering two different questions.
    func reload() {
        guard let store else { return }
        let bounds = time.range(pickedDate: pickedDate)
        do {
            let page = try RewindQueries.search(
                store, matching: query, since: bounds.since, until: bounds.until,
                limit: Self.pageSize)
            let all = page.frames.map(SearchMoment.init(frame:))
            websites = Self.facetWebsites(all)
            apps = Self.facetApps(all)
            // A filter left standing that this answer has nothing for would show an empty grid with a
            // lit chip and no way to tell which of the two was wrong.
            if let website, !websites.contains(website) { self.website = nil }
            if let app, !apps.contains(where: { $0.name == app }) { self.app = nil }

            let filtered = all.filter { moment in
                (self.website.map { moment.source == $0 } ?? true)
                    && (self.app.map { moment.appName == $0 } ?? true)
            }
            moments = filtered
            // The unfiltered total when nothing is narrowing it, and the narrowed count when
            // something is: "109 results" over a grid of four is a lie either way round.
            totalCount = (self.website == nil && self.app == nil) ? page.total : filtered.count
            loadError = nil
        } catch {
            moments = []
            totalCount = 0
            websites = []
            apps = []
            loadError = "Could not search this Mac's capture: \(error.localizedDescription)"
            ContextLog.error("search read failed: \(error)", "search")
        }
    }

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
