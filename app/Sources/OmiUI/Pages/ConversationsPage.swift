import OmiKit
import SwiftUI

// Conversations page, ported from `react-native/src/pages/Conversations.tsx`
// (embedded/mobile presentation): All/Starred filters, in-place loaded-library
// search, Today/Yesterday groupings, detail pane with Back outside the
// scrolled content, Load more, and the ReadStatus footer.

public struct ConversationsPage: View {
    public var embedded: Bool
    /// Shared draft binding; when provided there is no duplicate top search
    /// field (the mobile omnibar owns the query).
    public var search: Binding<String>?
    public var onRefresh: (() async -> Void)?
    public var onLoadMore: (() async -> Void)?
    public var loadingMore: Bool = false
    public var preserveLoadedPages: Bool = false
    public var notice: String? = nil

    @EnvironmentObject private var store: AppStore

    @State private var selectedId: String?
    @State private var localQuery: String = ""
    @State private var starredOnly = false
    @State private var paginated = false
    @State private var scrolledAway = false
    @State private var nowEpochMilliseconds: Int64 = Int64(Date().timeIntervalSince1970 * 1000)

    public init(
        embedded: Bool = false, search: Binding<String>? = nil,
        onRefresh: (() async -> Void)? = nil,
        onLoadMore: (() async -> Void)? = nil, loadingMore: Bool = false,
        preserveLoadedPages: Bool = false, notice: String? = nil
    ) {
        self.embedded = embedded
        self.search = search
        self.onRefresh = onRefresh
        self.onLoadMore = onLoadMore
        self.loadingMore = loadingMore
        self.preserveLoadedPages = preserveLoadedPages
        self.notice = notice
    }

    private var outcome: ReadOutcome<DomainRead<ConversationProjection>>? {
        store.outcomes?.conversations
    }

    private var loading: Bool { store.readsLoading }

    private var conversations: [ConversationProjection] {
        if case .success(let read) = outcome { return read.items }
        return []
    }

    private var query: String {
        get { search?.wrappedValue ?? localQuery }
        nonmutating set {
            if search != nil { search?.wrappedValue = newValue } else { localQuery = newValue }
        }
    }

    private var error: String? {
        if case .error(let message) = outcome { return message }
        return nil
    }

    private var filtered: [ConversationProjection] {
        conversations.filter { item in
            (!starredOnly || item.starred)
                && (matchesSearchQuery(item.title, query) || matchesSearchQuery(item.summary, query))
        }
    }

    private var grouped: [(label: String, items: [ConversationProjection])] {
        var groups: [(label: String, items: [ConversationProjection])] = []
        for item in filtered {
            let label = conversationGroupLabel(
                item.startedAt ?? item.createdAt, nowEpochMilliseconds: nowEpochMilliseconds
            )
            if var current = groups.last, current.label == label {
                current.items.append(item)
                groups[groups.count - 1] = current
            } else {
                groups.append((label: label, items: [item]))
            }
        }
        return groups
    }

    private var filtering: Bool {
        !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || starredOnly
    }

    private var selected: ConversationProjection? {
        filtered.first(where: { $0.id == selectedId })
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if !embedded {
                Text("Conversations")
                    .font(TypeStyle(size: 22, lineHeight: 28, weight: .semibold).font)
                    .foregroundColor(Color.white)
                    .padding(.bottom, 18)
            }
            if selected == nil {
                discovery
            }
            content
        }
        .onAppear {
            paginated = paginated || preserveLoadedPages
            nowEpochMilliseconds = Int64(Date().timeIntervalSince1970 * 1000)
            refreshIfReady()
        }
        .onChange(of: starredOnly) { _ in refreshIfReady() }
    }

    /// Entry/foreground refresh pauses during reads, in detail, when scrolled
    /// away from the top, and once older pages are loaded.
    private func refreshIfReady() {
        guard onRefresh != nil else { return }
        if !loading && !loadingMore && selected == nil && !scrolledAway && !paginated {
            Task { await onRefresh?() }
        }
    }

    // MARK: Filters

    private var discovery: some View {
        VStack(alignment: .leading, spacing: 12) {
            if search == nil {
                HStack(spacing: Space.sm) {
                    KitIcon(.search, size: 17, color: OmiColor.hex(0x777777))
                    TextField(
                        embedded ? "Search loaded conversations…" : "Search loaded conversations",
                        text: $localQuery
                    )
                    .font(TypeStyle(size: embedded ? 16 : 14, lineHeight: 20, weight: .regular).font)
                    .foregroundColor(Color.white)
                    .frame(minHeight: 44)
                    .accessibilityLabel("Search loaded conversations")
                    if embedded, !localQuery.isEmpty {
                        Button(action: { localQuery = "" }) {
                            KitIcon(.close, size: 18, color: MobilePalette.textMuted)
                                .frame(width: 44, height: 44)
                        }
                        .buttonStyle(KitPressableStyle())
                        .accessibilityLabel("Clear conversation search")
                    }
                }
                .padding(.trailing, 4)
                .frame(minHeight: 52)
                .background(MobilePalette.surface)
                .overlay(
                    RoundedRectangle(cornerRadius: MobileRadius.md)
                        .strokeBorder(MobilePalette.border, lineWidth: 0.5)
                )
                .clipShape(RoundedRectangle(cornerRadius: MobileRadius.md))
            }
            HStack(spacing: 6) {
                if embedded {
                    filterChip("All", selected: !starredOnly) {
                        starredOnly = false
                    }
                    .accessibilityLabel("Show all conversations")
                }
                filterChip("Starred", selected: starredOnly) {
                    starredOnly = embedded ? true : !starredOnly
                }
                .accessibilityLabel("Show starred conversations")
            }
            .padding(4)
            .background(MobilePalette.surfaceQuiet)
            .clipShape(RoundedRectangle(cornerRadius: MobileRadius.md))
        }
    }

    private func filterChip(
        _ title: String, selected: Bool, action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Text(title)
                .font(
                    TypeStyle(
                        size: 14, lineHeight: 18,
                        weight: selected ? .semibold : .medium
                    ).font
                )
                .foregroundColor(selected ? MobilePalette.text : MobilePalette.textMuted)
                .frame(maxWidth: .infinity, minHeight: 44)
                .background(
                    RoundedRectangle(cornerRadius: MobileRadius.sm)
                        .fill(selected ? MobilePalette.surfaceRaised : Color.clear)
                )
        }
        .buttonStyle(KitPressableStyle())
        .animation(KitMotion.slide, value: selected)
    }

    // MARK: Content

    private var content: some View {
        HStack(alignment: .top, spacing: Space.lg) {
            if selected == nil {
                listPane
            }
            detailPane
        }
        .frame(maxWidth: .infinity, alignment: .top).frame(maxHeight: .infinity)
    }

    private var listPane: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.lg) {
                if let notice {
                    Text(notice)
                        .font(Typography.caption.font)
                        .foregroundColor(Palette.textMuted)
                        .accessibilityLabel(notice)
                }
                if loading && outcome == nil {
                    VStack(spacing: Space.lg) {
                        if embedded {
                            OmiAvatarView(size: 48, motion: .breathe)
                        }
                        Text("Loading conversations…")
                            .font(Typography.caption.font)
                            .foregroundColor(Palette.textMuted)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(24)
                } else if let error {
                    VStack(spacing: 8) {
                        Text("Conversations unavailable")
                            .font(TypeStyle(size: 16, lineHeight: 22, weight: .semibold).font)
                            .foregroundColor(Palette.text)
                        Text(error)
                            .font(Typography.caption.font)
                            .foregroundColor(Palette.textMuted)
                            .accessibilityLabel(error)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(24)
                } else if grouped.isEmpty {
                    VStack(spacing: Space.lg) {
                        if embedded {
                            OmiAvatarView(size: 48, motion: .arrive)
                        }
                        Text(filtering ? "No loaded conversations match." : "No conversations yet.")
                            .font(TypeStyle(size: 16, lineHeight: 22, weight: .semibold).font)
                            .foregroundColor(Palette.text)
                        if filtering {
                            Text("Search and filters cover conversations already loaded on this device.")
                                .font(Typography.caption.font)
                                .foregroundColor(Palette.textMuted)
                                .multilineTextAlignment(.center)
                        }
                        if embedded, !filtering {
                            Text("Your saved conversations will appear here, ready to revisit.")
                                .font(TypeStyle(size: 14, lineHeight: 22, weight: .regular).font)
                                .foregroundColor(MobilePalette.textMuted)
                                .multilineTextAlignment(.center)
                        }
                        if embedded, filtering {
                            Button(action: {
                                query = ""
                                starredOnly = false
                            }) {
                                Text("Clear filters")
                                    .font(TypeStyle(size: 14, lineHeight: 18, weight: .semibold).font)
                                    .foregroundColor(MobilePalette.text)
                                    .frame(minHeight: 44)
                                    .padding(.horizontal, 20)
                            }
                            .buttonStyle(KitPressableStyle())
                            .background(MobilePalette.surfaceRaised)
                            .clipShape(RoundedRectangle(cornerRadius: 14))
                            .accessibilityLabel("Clear conversation filters")
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding(24)
                } else {
                    ForEach(grouped, id: \.label) { group in
                        VStack(alignment: .leading, spacing: 7) {
                            Text(group.label)
                                .font(Typography.caption.font)
                                .foregroundColor(Palette.textMuted)
                            ForEach(group.items) { item in
                                ConversationListRow(
                                    item: item,
                                    embedded: embedded,
                                    selected: item.id == selectedId,
                                    onPress: {
                                        if embedded { scrolledAway = false }
                                        selectedId = item.id
                                    }
                                )
                            }
                        }
                    }
                }
                if case .success(let read) = outcome, read.page.hasMore, onLoadMore != nil {
                    Button(action: {
                        // A first-page refresh would discard the older rows.
                        paginated = true
                        Task { await onLoadMore?() }
                    }) {
                        Text(loadingMore ? "Loading…" : "Load more")
                            .font(Typography.caption.font)
                            .foregroundColor(Palette.textMuted)
                            .frame(maxWidth: .infinity, alignment: .leading).frame(minHeight: 44)
                    }
                    .buttonStyle(KitPressableStyle())
                    .disabled(loading || loadingMore)
                    .accessibilityLabel("Load more conversations")
                }
                if case .success(let read) = outcome {
                    ReadStatusView(label: "Conversations", page: read.page)
                }
            }
            .padding(.bottom, 28)
        }
        .accessibilityLabel("Loaded conversations")
    }

    // MARK: Detail

    private var detailPane: some View {
        VStack(alignment: .leading, spacing: 0) {
            if embedded, selected != nil {
                Button(action: { selectedId = nil }) {
                    HStack(spacing: 6) {
                        KitIcon(.chevronLeft, size: 20, color: MobilePalette.text)
                        Text("Conversations")
                            .font(TypeStyle(size: 14, lineHeight: 18, weight: .semibold).font)
                            .foregroundColor(MobilePalette.text)
                    }
                    .frame(minHeight: 48)
                    .padding(.trailing, 14)
                }
                .buttonStyle(KitPressableStyle())
                .padding(.bottom, 12)
                .accessibilityLabel("Back to conversations")
            }
            ScrollView {
                if let selected {
                    ConversationDetailView(conversation: selected)
                        .padding(4)
                        .padding(.bottom, 32)
                } else {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Select a conversation")
                            .font(TypeStyle(size: 16, lineHeight: 22, weight: .semibold).font)
                            .foregroundColor(Palette.text)
                        Text("Choose a conversation to view its summary and details.")
                            .font(Typography.caption.font)
                            .foregroundColor(Palette.textMuted)
                    }
                    .frame(maxWidth: .infinity, minHeight: 200, alignment: .center)
                    .padding(20)
                }
            }
            .accessibilityLabel("Selected conversation details")
        }
        .frame(maxWidth: embedded ? .infinity : Size.content, alignment: .leading)
    }
}

// MARK: - List row

public struct ConversationListRow: View {
    public let item: ConversationProjection
    public let embedded: Bool
    public let selected: Bool
    public let onPress: () -> Void

    public init(
        item: ConversationProjection, embedded: Bool, selected: Bool,
        onPress: @escaping () -> Void
    ) {
        self.item = item
        self.embedded = embedded
        self.selected = selected
        self.onPress = onPress
    }

    public var body: some View {
        Button(action: onPress) {
            VStack(alignment: .leading, spacing: 5) {
                HStack {
                    Text(KitFormat.conversationDate(item.startedAt ?? item.createdAt))
                        .font(TypeStyle(size: 11, lineHeight: 14, weight: .semibold).font)
                        .foregroundColor(
                            embedded ? MobilePalette.textSubtle : OmiColor.hex(0x777777)
                        )
                    Spacer()
                    Text(item.starred ? "★" : "☆")
                        .font(TypeStyle(size: 16, lineHeight: 18, weight: .regular).font)
                        .foregroundColor(OmiColor.hex(0xD0D0D0))
                }
                Text(item.title)
                    .font(
                        TypeStyle(
                            size: embedded ? 17 : 14,
                            lineHeight: embedded ? 24 : 20, weight: .semibold
                        ).font
                    )
                    .foregroundColor(Color.white)
                    .lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text(item.summary)
                    .font(TypeStyle(size: embedded ? 14 : 12, lineHeight: embedded ? 21 : 17, weight: .regular).font)
                    .foregroundColor(
                        embedded ? MobilePalette.textMuted : Palette.textSubtle
                    )
                    .lineLimit(2)
                Text(KitFormat.conversationDuration(startedAt: item.startedAt, finishedAt: item.finishedAt))
                    .font(TypeStyle(size: 11, lineHeight: 14, weight: .regular).font)
                    .foregroundColor(
                        embedded ? MobilePalette.textSubtle : OmiColor.hex(0x777777)
                    )
            }
            .padding(embedded ? 18 : 12)
            .background(
                RoundedRectangle(cornerRadius: embedded ? 22 : Radius.lg)
                    .fill(embedded ? MobilePalette.surface : Palette.surface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: embedded ? 22 : Radius.lg)
                    .strokeBorder(
                        selected ? Color.white : (embedded ? MobilePalette.border : Palette.line),
                        lineWidth: selected ? 1 : 0.5
                    )
            )
        }
        .buttonStyle(KitPressableStyle())
        .accessibilityLabel("Open conversation \(item.title)")
        .accessibilityAddTraits(selected ? [.isSelected] : [])
    }
}

// MARK: - Detail body

public struct ConversationDetailView: View {
    public let conversation: ConversationProjection

    public init(conversation: ConversationProjection) {
        self.conversation = conversation
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(conversation.title)
                .font(TypeStyle(size: 22, lineHeight: 30, weight: .bold).font)
                .foregroundColor(Color.white)
            Text(conversation.summary)
                .font(TypeStyle(size: 16, lineHeight: 24, weight: .regular).font)
                .foregroundColor(Palette.textMuted)
            VStack(alignment: .leading, spacing: 8) {
                if let capturedAtMs = conversation.capturedAtMs {
                    field(
                        "Captured (device time) · \(KitFormat.localDateTime(milliseconds: capturedAtMs))"
                    )
                }
                field("Started · \(KitFormat.conversationDate(conversation.startedAt))")
                field("Finished · \(KitFormat.conversationDate(conversation.finishedAt))")
                field(
                    "Duration · \(KitFormat.conversationDuration(startedAt: conversation.startedAt, finishedAt: conversation.finishedAt))"
                )
                field("Status · \(conversation.status)")
                if conversation.locked {
                    field("Locked")
                }
                if conversation.discarded {
                    field("Discarded")
                }
            }
            .padding(.top, 14)
            if conversation.source == "chat" {
                Text("Chat history for this conversation is not available here.")
                    .font(TypeStyle(size: 16, lineHeight: 24, weight: .regular).font)
                    .foregroundColor(Palette.textMuted)
                    .padding(.top, 8)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func field(_ copy: String) -> some View {
        Text(copy)
            .font(TypeStyle(size: 13, lineHeight: 18, weight: .regular).font)
            .foregroundColor(OmiColor.hex(0xD0D0D0))
    }
}
