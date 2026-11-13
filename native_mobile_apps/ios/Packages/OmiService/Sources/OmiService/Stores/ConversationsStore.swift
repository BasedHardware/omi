import Foundation
import Observation
import OmiCore
import OmiNetwork
import OmiPersistence

/// Conversation list. Mirrors the Flutter app's `conversation_provider.dart`; star, folders,
/// delete with undo, merge and reprocess live in `ConversationsStore+Organizing.swift`.
@MainActor
@Observable
public final class ConversationsStore {
    public enum Phase: Equatable, Sendable {
        case idle, loading, loaded, failed(String)
    }

    public struct DaySection: Identifiable, Equatable, Sendable {
        public let day: Date
        public let conversations: [Conversation]
        public var id: Date {
            day
        }

        public init(day: Date, conversations: [Conversation]) {
            self.day = day
            self.conversations = conversations
        }
    }

    /// Conversations removed from the list whose backend delete waits out the undo window.
    public struct PendingDeletion: Equatable, Sendable {
        public let ids: [String]
        var removed: [(index: Int, conversation: Conversation)]
        var removedFiltered: [(index: Int, conversation: Conversation)]

        public static func == (lhs: Self, rhs: Self) -> Bool {
            lhs.ids == rhs.ids
        }
    }

    public internal(set) var phase: Phase = .idle
    /// Every conversation, newest first (the unfiltered list other screens look titles up in).
    public internal(set) var conversations: [Conversation] = []
    public internal(set) var hasMore = true
    public internal(set) var isLoadingMore = false

    /// What the Home list shows; anything but `.all` fills `filtered` from the backend.
    public internal(set) var filter: ConversationFilter = .all
    public internal(set) var filtered: [Conversation] = []
    public internal(set) var filteredHasMore = false
    public internal(set) var isLoadingFiltered = false
    public internal(set) var folders: [Folder] = []
    public internal(set) var pendingDeletion: PendingDeletion?
    /// Conversations opened outside the loaded pages (from a memory, a search), kept current here.
    var known: [String: Conversation] = [:]
    /// Details loaded for task sources (where each task came from), by conversation id.
    public internal(set) var sourceDetails: [String: ConversationDetail] = [:]
    var deletionTask: Task<Void, Never>?

    /// Discarded and short conversations shown or hidden (`ConversationsStore+Display.swift`).
    public internal(set) var display: ConversationDisplay

    let api: any APIClientProtocol
    let calendar: Calendar
    let pageSize = 50
    let undoWindow: Duration
    let mergeRefreshDelay: Duration
    let preferences: Preferences?

    public init(
        api: any APIClientProtocol,
        calendar: Calendar = .current,
        undoWindow: Duration = .seconds(5),
        mergeRefreshDelay: Duration = .seconds(8),
        preferences: Preferences? = nil
    ) {
        self.api = api
        self.calendar = calendar
        self.undoWindow = undoWindow
        self.mergeRefreshDelay = mergeRefreshDelay
        self.preferences = preferences
        display = preferences.map(Self.display) ?? ConversationDisplay()
    }

    /// Omi's daily recaps, newest first.
    public private(set) var recaps: [DailySummary] = []
    public private(set) var isCreatingRecap = false

    public func loadRecaps() async {
        if let loaded = try? await api.dailySummaries(limit: 14) { recaps = loaded }
    }

    /// Generates (or fetches) the recap for a local day.
    public func createRecap(for day: Date) async {
        guard !isCreatingRecap else { return }
        isCreatingRecap = true
        defer { isCreatingRecap = false }
        let formatter = DateFormatter()
        formatter.calendar = calendar
        formatter.dateFormat = "yyyy-MM-dd"
        if let recap = try? await api.createDailySummary(date: formatter.string(from: day)) {
            recaps.removeAll { $0.id == recap.id || $0.date == recap.date }
            recaps.insert(recap, at: 0)
        }
    }

    /// What Home shows first under a day: that day's recap, or for yesterday (with conversations,
    /// no recap yet) the offer to write it. Only in the unfiltered list.
    public enum RecapSlot: Equatable, Sendable {
        case recap(DailySummary)
        case write(Date)
    }

    public func recapSlot(for day: Date, now: Date = .now) -> RecapSlot? {
        guard filter == .all else { return nil }
        if let recap = recaps.first(where: { $0.date == Self.dayKey(day, calendar: calendar) }) { return .recap(recap) }
        guard let yesterday = calendar.date(byAdding: .day, value: -1, to: calendar.startOfDay(for: now)),
              calendar.isDate(day, inSameDayAs: yesterday),
              conversations.contains(where: { calendar.isDate($0.date, inSameDayAs: day) }) else { return nil }
        return .write(calendar.startOfDay(for: day))
    }

    /// `YYYY-MM-DD` in the user's calendar, how recaps name their day.
    static func dayKey(_ day: Date, calendar: Calendar) -> String {
        let parts = calendar.dateComponents([.year, .month, .day], from: day)
        return String(format: "%04d-%02d-%02d", parts.year ?? 0, parts.month ?? 0, parts.day ?? 0)
    }

    /// Optimistic rename; the old title comes back if the backend refuses.
    public func rename(_ id: String, to title: String) async {
        let title = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else { return }
        let edit = edit([id]) { $0.title = title }
        guard !edit.isEmpty else { return }
        do {
            try await api.renameConversation(id: id, title: title)
        } catch {
            revert(edit)
        }
    }

    /// Removes the conversation at once (no undo); it comes back if the backend refuses.
    public func delete(_ id: String) async {
        guard let index = conversations.firstIndex(where: { $0.id == id }) else { return }
        let removed = conversations.remove(at: index)
        do {
            try await api.deleteConversation(id: id)
        } catch {
            conversations.insert(removed, at: min(index, conversations.count))
        }
    }

    public func load() async {
        if conversations.isEmpty { phase = .loading }
        do {
            let page = try await fetchPage(offset: 0)
            // A delete waiting for its undo window stays hidden.
            let hidden = Set(pendingDeletion?.ids ?? [])
            conversations = page.filter { !hidden.contains($0.id) }
            hasMore = page.count == pageSize
            phase = .loaded
        } catch {
            // Keep showing what we had; only an empty screen shows the error state.
            phase = .failed(String(describing: error))
        }
    }

    /// Next page (`offset` paging, like the Flutter app). Call when the last row appears.
    public func loadMore() async {
        if filter != .all { return await loadMoreFiltered() }
        guard hasMore, !isLoadingMore, phase == .loaded else { return }
        isLoadingMore = true
        defer { isLoadingMore = false }
        guard let page = try? await fetchPage(offset: conversations.count) else { return }
        let known = Set(conversations.map(\.id))
        conversations += page.filter { !known.contains($0.id) }
        hasMore = page.count == pageSize
    }

    /// What the list shows under the current filter (short and discarded ones as `display` says,
    /// one row per capture group).
    public var visible: [Conversation] {
        ConversationDisplay.oneRowPerCaptureGroup((filter == .all ? conversations : filtered).filter(display.keeps))
    }

    /// Newest day first, newest conversation first within a day.
    public var sections: [DaySection] {
        let grouped = Dictionary(grouping: visible) { calendar.startOfDay(for: $0.date) }
        return grouped.keys.sorted(by: >).map { day in
            DaySection(day: day, conversations: grouped[day, default: []].sorted { $0.date > $1.date })
        }
    }

    /// The conversation with this id: from the list, otherwise fetched (a memory can come from a
    /// conversation older than the loaded pages). `nil` when it is gone.
    public func conversation(id: String) async -> Conversation? {
        if let loaded = conversations.first(where: { $0.id == id }) ?? known[id] { return loaded }
        return try? await api.conversationDetail(id: id).conversation
    }

    public func today(now: Date = .now) -> [Conversation] {
        conversations.filter { calendar.isDate($0.date, inSameDayAs: now) }.sorted { $0.date > $1.date }
    }
}
