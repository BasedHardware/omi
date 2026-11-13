import Foundation
import Observation
import OmiCore
import OmiNetwork
import OmiPersistence

/// Home's display options (Flutter "Conversation display"): discarded conversations come from the
/// backend only when asked for; short ones are hidden on the device below a threshold.
public extension ConversationsStore {
    /// The thresholds Flutter offers, in seconds.
    static let shortThresholds = [60, 120, 180, 240, 300]

    /// Shows or hides discarded conversations, then reloads the list.
    func setShowsDiscarded(_ shows: Bool) async {
        guard display.showsDiscarded != shows else { return }
        display.showsDiscarded = shows
        preferences?.set(shows, for: .showDiscardedMemories)
        await load()
    }

    /// Hides conversations shorter than `seconds`; `nil` shows every length.
    func hideShorter(than seconds: Int?) {
        if let seconds {
            display.showsShort = false
            display.shortThreshold = seconds
            preferences?.set(seconds, for: .shortConversationThreshold)
        } else {
            display.showsShort = true
        }
        preferences?.set(display.showsShort, for: .showShortConversations)
    }

    internal static func display(_ preferences: Preferences) -> ConversationDisplay {
        ConversationDisplay(
            showsDiscarded: preferences.bool(.showDiscardedMemories, default: false),
            showsShort: preferences.bool(.showShortConversations, default: false),
            shortThreshold: preferences.integer(.shortConversationThreshold, default: 0)
        )
    }

    /// One page of the unfiltered list, discarded ones included when shown.
    internal func fetchPage(offset: Int) async throws -> [Conversation] {
        if display.showsDiscarded {
            return try await api.conversations(limit: pageSize, offset: offset, query: ConversationQuery(includeDiscarded: true))
        }
        return try await api.conversations(limit: pageSize, offset: offset)
    }

    /// The one-day page (Flutter `day_conversations_page`).
    func makeDayStore(day: Date) -> DayConversationsStore {
        DayConversationsStore(api: api, day: day, calendar: calendar, display: display)
    }
}

/// One day's conversations, paged, with the previous and next day (never past today).
@MainActor
@Observable
public final class DayConversationsStore {
    public enum Phase: Equatable, Sendable { case loading, loaded, failed }

    public private(set) var day: Date
    public private(set) var phase: Phase = .loading
    private var loaded: [Conversation] = []
    public private(set) var hasMore = false
    public private(set) var isLoadingMore = false

    let api: any APIClientProtocol
    let calendar: Calendar
    let display: ConversationDisplay
    let pageSize = 50

    init(api: any APIClientProtocol, day: Date, calendar: Calendar, display: ConversationDisplay) {
        self.api = api
        self.calendar = calendar
        self.display = display
        self.day = calendar.startOfDay(for: day)
    }

    /// Newest first; short ones hidden as on Home (discarded ones never come on this page).
    public var conversations: [Conversation] {
        ConversationDisplay.oneRowPerCaptureGroup(loaded.filter(display.keeps)).sorted { $0.date > $1.date }
    }

    public func canGoForward(now: Date = .now) -> Bool {
        day < calendar.startOfDay(for: now)
    }

    public func load() async {
        phase = loaded.isEmpty ? .loading : phase
        do {
            let page = try await fetch(offset: 0)
            loaded = page
            hasMore = page.count == pageSize
            phase = .loaded
        } catch {
            phase = .failed
        }
    }

    public func loadMore() async {
        guard hasMore, !isLoadingMore, phase == .loaded else { return }
        isLoadingMore = true
        defer { isLoadingMore = false }
        guard let page = try? await fetch(offset: loaded.count) else { return }
        let known = Set(loaded.map(\.id))
        loaded += page.filter { !known.contains($0.id) }
        hasMore = page.count == pageSize
    }

    /// Moves by `days` (negative for earlier) or to a picked day, then loads it.
    public func go(by days: Int, now: Date = .now) async {
        guard let next = calendar.date(byAdding: .day, value: days, to: day) else { return }
        await show(next, now: now)
    }

    public func show(_ day: Date, now: Date = .now) async {
        let target = min(calendar.startOfDay(for: day), calendar.startOfDay(for: now))
        guard target != self.day else { return }
        self.day = target
        loaded = []
        hasMore = false
        await load()
    }

    private func fetch(offset: Int) async throws -> [Conversation] {
        let end = calendar.date(byAdding: DateComponents(day: 1, second: -1), to: day) ?? day
        return try await api.conversations(limit: pageSize, offset: offset, query: ConversationQuery(start: day, end: end))
    }
}
