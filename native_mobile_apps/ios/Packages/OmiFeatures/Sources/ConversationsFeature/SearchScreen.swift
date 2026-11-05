import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// Search (the magnifying glass on Home): recent searches and every conversation by day until
/// something is typed or filtered, then one list of matching conversations, recaps, tasks and
/// memories. Loaded matches show at once; the backend adds conversations it finds by what was said.
/// Filters (starred, a person, a date range) narrow it to conversations.
public struct SearchScreen: View {
    @Environment(ConversationsStore.self) private var store
    @Environment(TasksStore.self) private var tasks
    @Environment(SettingsStore.self) private var settings
    @State private var search: SearchStore
    @State private var query = DebugLaunch.string("omiSearchQuery") ?? ""
    @State private var pickingDates = false
    private let onOpenConversation: (Conversation) -> Void
    private let onOpenRecap: ((DailySummary) -> Void)?

    public init(store: SearchStore, onOpenConversation: @escaping (Conversation) -> Void, onOpenRecap: ((DailySummary) -> Void)? = nil) {
        _search = State(initialValue: store)
        self.onOpenConversation = onOpenConversation
        self.onOpenRecap = onOpenRecap
    }

    public var body: some View {
        List {
            if search.filter.isActive { activeFilters }
            if search.isActive { results } else { idle }
        }
        .listStyle(.grouped)
        .omiList()
        .safeAreaInset(edge: .bottom) {
            if store.isLoadingMore, !search.isActive { ProgressView().padding(DS.Spacing.md) }
        }
        .searchable(text: $query, prompt: L("search"))
        .onSubmit(of: .search) { search.remember() }
        .onChange(of: query) { _, text in search.update(query: text) }
        .toolbar { ToolbarItem(placement: .topBarTrailing) { SearchFilterMenu(search: search, pickingDates: $pickingDates) } }
        .refreshable { await store.load() }
        .task { await search.loadSources() }
        .task { if !query.isEmpty { search.update(query: query) } }
        .task { await settings.loadPeople() }
        .sheet(isPresented: $pickingDates) { DateRangeSheet(search: search).presentationDetents([.medium, .large]) }
        .overlay { emptyState }
        // Opening a result (or leaving) keeps the typed query among the recent searches.
        .onDisappear { search.remember() }
    }

    @ViewBuilder
    private var idle: some View {
        if !search.recents.isEmpty {
            Section {
                ForEach(search.recents, id: \.self) { recent in
                    Button {
                        query = recent
                        search.remember(recent)
                    } label: {
                        Label(recent, systemImage: "clock.arrow.circlepath").foregroundStyle(DS.Palette.ink)
                    }
                    .searchResultRow()
                    .swipeActions { Button(L("delete"), role: .destructive) { search.removeRecent(recent) } }
                }
            } header: {
                HStack {
                    Text(L("recent"))
                    Spacer()
                    Button(L("nativeClearRecents")) { search.clearRecents() }
                        .font(DS.Typography.caption)
                        .textCase(nil)
                        .accessibilityIdentifier("search.clearRecents")
                }
            }
        }
        allConversations
    }

    @ViewBuilder
    private var allConversations: some View {
        switch store.phase {
        case .loading where store.conversations.isEmpty:
            ForEach(0 ..< 4, id: \.self) { _ in SkeletonBlock().listRowSeparator(.hidden) }
        case .failed where store.conversations.isEmpty:
            OmiEmptyState(L("nativeCouldNotLoad"), systemImage: "wifi.exclamationmark")
                .listRowBackground(Color.clear)
        default:
            ForEach(store.sections) { section in
                Section(Formatting.dayTitle(section.day)) {
                    ForEach(section.conversations) { conversation in
                        conversationLink(conversation)
                            .onAppear {
                                if conversation.id == store.conversations.last?.id { Task { await store.loadMore() } }
                            }
                    }
                }
            }
        }
    }

    private var activeFilters: some View {
        Section {
            ScrollView(.horizontal) {
                HStack(spacing: DS.Spacing.sm) {
                    if search.filter.starred {
                        FilterChip(title: L("starred"), symbol: "star.fill") { search.filter.starred = false }
                    }
                    if let person = search.filter.person {
                        FilterChip(title: person.name, symbol: "person.fill") { search.filter.person = nil }
                    }
                    if let range = DateRangeSheet.title(search.filter) {
                        FilterChip(title: range, symbol: "calendar") {
                            search.filter.start = nil
                            search.filter.end = nil
                        }
                    }
                }
            }
            .scrollIndicators(.hidden)
            .listRowBackground(Color.clear)
            .listRowInsets(EdgeInsets())
        }
    }

    @ViewBuilder
    private var results: some View {
        let conversations = search.conversations
        if !conversations.isEmpty || search.phase == .searching {
            Section(L("conversations")) {
                ForEach(conversations, content: conversationLink)
                if search.phase == .searching {
                    Label { Text(L("nativeSearching")) } icon: { ProgressView() }
                        .font(DS.Typography.callout)
                        .foregroundStyle(DS.Palette.inkSecondary)
                }
            }
        }
        if !search.recaps.isEmpty {
            Section(L("recaps")) {
                ForEach(search.recaps) { recap in
                    Button {
                        search.remember()
                        onOpenRecap?(recap)
                    } label: {
                        HStack(spacing: DS.Spacing.md) {
                            Text(recap.emoji ?? "📅").font(.system(size: 22)).frame(width: 30).accessibilityHidden(true)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(recap.headline).font(DS.Typography.cardTitle).foregroundStyle(DS.Palette.ink).lineLimit(2)
                                Text(recap.day.map { Formatting.dayTitle($0) } ?? recap.date)
                                    .font(DS.Typography.caption)
                                    .foregroundStyle(DS.Palette.inkSecondary)
                            }
                        }
                    }
                    .disabled(onOpenRecap == nil)
                    .searchResultRow()
                }
            }
        }
        let matchingTasks = search.tasks
        if !matchingTasks.isEmpty {
            Section(L("tasks")) {
                ForEach(matchingTasks) { task in
                    TaskRow(
                        task,
                        source: task.conversationID.flatMap(title),
                        onToggle: { Task { await tasks.setCompleted(task.id, !task.isCompleted) } }
                    )
                    .contentShape(Rectangle())
                    .onTapGesture { if let id = task.conversationID { open(id) } }
                    .searchResultRow()
                }
            }
        }
        let memories = search.memories
        if !memories.isEmpty {
            Section(L("memories")) {
                ForEach(memories) { memory in
                    Group {
                        if let id = memory.conversationID {
                            Button { open(id) } label: { MemoryResult(memory: memory, source: title(of: id)) }
                                .buttonStyle(.plain)
                        } else {
                            MemoryResult(memory: memory, source: nil)
                        }
                    }
                    .searchResultRow()
                }
            }
        }
    }

    @ViewBuilder
    private var emptyState: some View {
        if !search.isActive, store.phase == .loaded, store.conversations.isEmpty {
            OmiEmptyState(L("nativeNoConversationsYet"), systemImage: "waveform", message: L("nativeNoConversationsToday"))
        } else if search.isActive, search.phase == .failed, !search.hasResults {
            OmiEmptyState(L("nativeCouldNotLoad"), systemImage: "wifi.exclamationmark")
        } else if search.isActive, search.phase == .done, !search.hasResults {
            OmiEmptyState(L("noResultsFound"), systemImage: "magnifyingglass")
        }
    }

    /// A conversation row that opens it, without the list's chevron (text-first, as on Home).
    private func conversationLink(_ conversation: Conversation) -> some View {
        ConversationRow(conversation, style: .plain)
            .background { NavigationLink(value: conversation) { EmptyView() }.opacity(0) }
            .searchResultRow()
    }

    private func title(of id: String) -> String? {
        store.conversations.first { $0.id == id }.map { $0.title.isEmpty ? L("untitledConversation") : $0.title }
    }

    private func open(_ conversationID: String) {
        search.remember()
        Task { if let conversation = await store.conversation(id: conversationID) { onOpenConversation(conversation) } }
    }
}

private extension View {
    /// A result on the page itself: no cell background, no separator.
    func searchResultRow() -> some View {
        listRowBackground(Color.clear).listRowSeparator(.hidden)
    }
}

/// A matching memory: its text, and the conversation it came from when that is loaded.
private struct MemoryResult: View {
    let memory: Memory
    let source: String?

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.xs) {
            Text(memory.content)
                .font(DS.Typography.callout)
                .foregroundStyle(DS.Palette.ink)
                .fixedSize(horizontal: false, vertical: true)
            Text(source.map { L("nativeFromConversation", $0) } ?? memory.category.capitalized)
                .font(DS.Typography.caption)
                .foregroundStyle(DS.Palette.inkSecondary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .padding(.vertical, DS.Spacing.xxs)
    }
}
