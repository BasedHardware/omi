import Foundation
import Observation
import OmiCore
import OmiNetwork

/// One search over conversations, recaps, tasks and memories. What is already loaded matches at
/// once; the backend's conversation search (titles, overviews and what was said) follows once
/// typing pauses. Filters (starred, a person, a date range) narrow it to conversations; recent
/// searches are kept like Flutter's (`global_search`). Created per search screen.
@MainActor
@Observable
public final class SearchStore {
    public enum Phase: Equatable, Sendable {
        /// No query and no filter.
        case idle
        /// Waiting for typing to pause, or for the backend.
        case searching
        case done
        /// The backend search failed; local matches still show.
        case failed
    }

    /// Narrows the search to conversations (Flutter's starred tile, people, date filter).
    public struct Filter: Equatable, Sendable {
        public var starred = false
        public var person: Person?
        public var start: Date?
        public var end: Date?

        public init(starred: Bool = false, person: Person? = nil, start: Date? = nil, end: Date? = nil) {
            self.starred = starred
            self.person = person
            self.start = start
            self.end = end
        }

        public var isActive: Bool {
            starred || person != nil || start != nil || end != nil
        }

        var server: ConversationSearchFilter {
            ConversationSearchFilter(start: start, end: end, speakerID: person?.id)
        }
    }

    public private(set) var query = ""
    public private(set) var phase: Phase = .idle
    public var filter = Filter() {
        didSet { if filter != oldValue { search() } }
    }

    /// Newest first, at most `maxRecents`.
    public private(set) var recents: [String]
    /// Day recaps matching the query.
    public private(set) var recaps: [DailySummary] = []
    /// Backend hits for `query`; empty until they arrive.
    var serverHits: [Conversation] = []
    /// The debounced backend search for the current query (tests await it).
    private(set) var pending: Task<Void, Never>?

    let api: any APIClientProtocol
    let conversationsStore: ConversationsStore
    private let tasksStore: TasksStore
    private let memoriesStore: MemoriesStore
    private let debounce: Duration
    private let defaults: UserDefaults
    let perPage = 30
    /// Flutter's key and limit, so an update keeps the list.
    static let recentsKey = "flutter.globalSearchRecentQueries"
    static let maxRecents = 6

    public init(
        api: any APIClientProtocol,
        conversations: ConversationsStore,
        tasks: TasksStore,
        memories: MemoriesStore,
        debounce: Duration = .milliseconds(300),
        defaults: UserDefaults = .standard
    ) {
        self.api = api
        conversationsStore = conversations
        tasksStore = tasks
        memoriesStore = memories
        self.debounce = debounce
        self.defaults = defaults
        recents = defaults.stringArray(forKey: Self.recentsKey) ?? []
    }

    var needle: String {
        query.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// A query or a filter is set: results show instead of the full list.
    public var isActive: Bool {
        !needle.isEmpty || filter.isActive
    }

    /// Loaded and backend matches together, newest first; the loaded copy wins (it has local edits).
    public var conversations: [Conversation] {
        guard isActive else { return [] }
        // The loaded list does not know who spoke; a person filter is the backend's alone.
        let local = filter.person != nil ? [] : conversationsStore.conversations.filter {
            (needle.isEmpty || $0.title.localizedStandardContains(needle) || $0.overview.localizedStandardContains(needle)) && passes($0)
        }
        let known = Set(local.map(\.id))
        let loaded = Dictionary(conversationsStore.conversations.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let remote = serverHits.filter { !known.contains($0.id) }.map { loaded[$0.id] ?? $0 }.filter(passes)
        return (local + remote).sorted { $0.date > $1.date }
    }

    public var tasks: [ActionItem] {
        needle.isEmpty || filter.isActive ? [] : tasksStore.matching(needle)
    }

    public var memories: [Memory] {
        guard !needle.isEmpty, !filter.isActive else { return [] }
        return memoriesStore.memories.filter { $0.content.localizedStandardContains(needle) }.sorted { $0.createdAt > $1.createdAt }
    }

    public var hasResults: Bool {
        !conversations.isEmpty || !tasks.isEmpty || !memories.isEmpty || !recaps.isEmpty
    }

    /// Loads whatever the local matches need and has not been loaded yet.
    public func loadSources() async {
        let conversations = conversationsStore, tasks = tasksStore, memories = memoriesStore
        await withDiscardingTaskGroup { group in
            if conversations.phase == .idle { group.addTask { await conversations.load() } }
            if tasks.phase == .idle { group.addTask { await tasks.load() } }
            if memories.phase == .idle { group.addTask { await memories.load() } }
        }
    }

    /// Call on every keystroke: local matches update now, the backend is asked once typing pauses,
    /// and an answer for an older query is dropped.
    public func update(query newValue: String) {
        guard newValue != query else { return }
        let previousNeedle = needle
        query = newValue
        guard needle != previousNeedle else { return }
        search()
    }

    // MARK: Recent searches

    /// Keeps `text` on top of the recent searches (on submit, or when a result is opened).
    public func remember(_ text: String? = nil) {
        let entry = (text ?? query).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !entry.isEmpty else { return }
        recents = Array(([entry] + recents.filter { $0.caseInsensitiveCompare(entry) != .orderedSame }).prefix(Self.maxRecents))
        defaults.set(recents, forKey: Self.recentsKey)
    }

    public func removeRecent(_ text: String) {
        recents.removeAll { $0 == text }
        defaults.set(recents, forKey: Self.recentsKey)
    }

    public func clearRecents() {
        recents = []
        defaults.removeObject(forKey: Self.recentsKey)
    }

    // MARK: Backend

    private func passes(_ conversation: Conversation) -> Bool {
        (!filter.starred || conversation.isStarred)
            && filter.start.map { conversation.date >= $0 } ?? true
            && filter.end.map { conversation.date <= $0 } ?? true
    }

    private func search() {
        pending?.cancel()
        serverHits = []
        recaps = []
        guard isActive else {
            pending = nil
            phase = .idle
            return
        }
        phase = .searching
        let needle = needle, filter = filter
        pending = Task { [weak self, api, debounce, perPage] in
            do { try await Task.sleep(for: debounce) } catch { return }
            let wantsRecaps = !needle.isEmpty && !filter.starred && filter.person == nil
            async let found = Self.conversations(api: api, needle: needle, filter: filter, perPage: perPage)
            async let days: [DailySummary] = wantsRecaps ? (try? await api.searchRecaps(query: needle)) ?? [] : []
            let (hits, recapHits) = await (found, days)
            guard let self, !Task.isCancelled, self.needle == needle, self.filter == filter else { return }
            serverHits = hits ?? []
            recaps = recapHits.filter { recap in
                let day = BackendDate.parse(recap.date + "T12:00:00Z")
                return day.map { day in filter.start.map { day >= $0 } ?? true && filter.end.map { day <= $0 } ?? true } ?? true
            }
            phase = hits == nil ? .failed : .done
        }
    }

    /// Starred with nothing else: the starred list itself. Otherwise the backend search.
    private nonisolated static func conversations(
        api: any APIClientProtocol, needle: String, filter: Filter, perPage: Int
    ) async -> [Conversation]? {
        if needle.isEmpty, filter.starred, filter.server.isEmpty {
            return try? await api.conversations(limit: 50, offset: 0, filter: .starred)
        }
        if filter.server.isEmpty {
            return try? await api.searchConversations(query: needle, page: 1, perPage: perPage)
        }
        return try? await api.searchConversations(query: needle, page: 1, perPage: perPage, filter: filter.server)
    }
}
