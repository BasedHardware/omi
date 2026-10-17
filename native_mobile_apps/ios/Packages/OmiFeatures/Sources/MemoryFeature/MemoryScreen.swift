import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// What Omi knows about me: search on top, kind and category chips, one card per memory (Omi's
/// memories page). The header menu holds the memory graph and "make all private/public"; a delete
/// can be undone for a few seconds.
public struct MemoryScreen: View {
    @Environment(MemoriesStore.self) private var store
    @Environment(ConversationsStore.self) private var conversations
    @Environment(SessionStore.self) private var session
    @State private var query = ""
    @State private var category: String?
    @State private var editing: Memory?
    @State private var showsNewMemory = DebugLaunch.flag("omiNewMemory")
    @State private var showsGraph = DebugLaunch.flag("omiMemoryGraph")
    @State private var visibilityResult: String?
    @State private var reviewing = DebugLaunch.flag("omiMemoryReview")
    private let onOpenConversation: (Conversation) -> Void
    private let onReview: (() -> Void)?

    /// `onOpenConversation` opens the conversation a memory came from. `onReview` opens the review
    /// of new memories from the "Review new memories" entry; without it the built-in one-at-a-time
    /// sheet opens.
    public init(onOpenConversation: @escaping (Conversation) -> Void, onReview: (() -> Void)? = nil) {
        self.onOpenConversation = onOpenConversation
        self.onReview = onReview
    }

    public var body: some View {
        // The search row stays put above the list, at the same place as on Tasks.
        VStack(spacing: 0) {
            search.padding(.horizontal, DS.Spacing.gutter)
            list
        }
    }

    private var list: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                reviewEntry
                if !store.memories.isEmpty { chips.padding(.bottom, DS.Spacing.sm) }
                content
            }
            .padding(.horizontal, DS.Spacing.gutter)
            .padding(.top, DS.Spacing.sm)
            .padding(.bottom, DS.Spacing.section)
        }
        .scrollIndicators(.hidden)
        .scrollDismissesKeyboard(.immediately)
        .refreshable { await store.load() }
        .task { if store.phase == .idle { await store.load() } }
        .task { await store.loadReviewQueue() }
        .sheet(item: $editing) { memory in EditMemorySheet(memory: memory).presentationDetents([.medium, .large]) }
        .sheet(isPresented: $showsNewMemory) { NewMemorySheet().presentationDetents([.medium]) }
        .sheet(isPresented: $reviewing) { MemoryReviewSheet(sources: source(of:)) }
        .navigationDestination(isPresented: $showsGraph) {
            MemoryGraphScreen(store: store.makeGraphStore(userName: session.displayName))
        }
        .overlay(alignment: .bottom) { toast.padding(.bottom, DS.Spacing.sm) }
        .animation(DS.Motion.standard, value: store.pendingDeletion)
        .onDisappear { Task { await store.commitPendingDeletion() } }
    }

    @ViewBuilder
    private var toast: some View {
        if store.pendingDeletion != nil {
            OmiToast(text: L("memoryDeleted"), systemImage: "trash", actionTitle: L("undo")) {
                DSHaptics.tap()
                withAnimation(DS.Motion.standard) { store.undoDelete() }
            }
            .transition(.move(edge: .bottom).combined(with: .opacity))
        } else if let visibilityResult {
            OmiToast(text: visibilityResult, systemImage: "lock")
                .transition(.move(edge: .bottom).combined(with: .opacity))
                .task {
                    try? await Task.sleep(for: .seconds(3))
                    withAnimation { self.visibilityResult = nil }
                }
        }
    }

    /// New memories wait behind one entry instead of asking on every row.
    @ViewBuilder
    private var reviewEntry: some View {
        let count = store.reviewCount
        if count > 0, query.isEmpty {
            MemoryReviewEntry(count: count) { if let onReview { onReview() } else { reviewing = true } }
                .padding(.bottom, DS.Spacing.md)
        }
    }

    private var search: some View {
        HStack(spacing: DS.Spacing.sm) {
            OmiSearchField(L("searchMemories"), text: $query, clearLabel: L("cancel"))
            menu
            CircleIconButton("plus") { showsNewMemory = true }
                .accessibilityLabel(L("createMemoryTooltip"))
                .accessibilityIdentifier("memories.add")
        }
        .padding(.bottom, DS.Spacing.xs)
    }

    /// Memory graph, and the visibility of every memory at once (Flutter's management sheet).
    private var menu: some View {
        Menu {
            Button { showsGraph = true } label: { Label(L("memoryGraph"), systemImage: "point.3.connected.trianglepath.dotted") }
                .accessibilityIdentifier("memories.graph")
            Section(L("nativeMemoryVisibilityCounts", String(store.publicCount), String(store.privateCount))) {
                Button { setAll(.private) } label: { Label(L("makeAllPrivate"), systemImage: "lock") }
                Button { setAll(.public) } label: { Label(L("makeAllPublic"), systemImage: "globe") }
            }
        } label: {
            OmiCircleIcon("ellipsis")
        }
        .accessibilityLabel(L("moreOptions"))
        .accessibilityIdentifier("memories.menu")
    }

    private func setAll(_ visibility: Memory.Visibility) {
        Task {
            let allTook = await store.setAllVisibility(visibility)
            withAnimation {
                visibilityResult = allTook
                    ? (visibility == .private ? L("nativeAllMemoriesPrivate") : L("nativeAllMemoriesPublic"))
                    : L("nativeSomeMemoriesNotUpdated")
            }
        }
    }

    private var chips: some View {
        ScrollView(.horizontal) {
            HStack(spacing: DS.Spacing.sm) {
                chip(L("filterAll"), nil, count: store.visible(matching: query).count)
                // Empty kinds ("Manual 0") are noise; a chosen one stays so it can be cleared.
                ForEach(store.filterChips(matching: query).filter { $0.count > 0 || $0.category == category }, id: \.category) {
                    chip(MemoryKind.title($0.category), $0.category, count: $0.count)
                }
            }
        }
        .scrollIndicators(.hidden)
        .padding(.bottom, DS.Spacing.xs)
    }

    private func chip(_ title: String, _ value: String?, count: Int) -> some View {
        let selected = category == value
        return Button {
            withAnimation(DS.Motion.standard) { category = value }
        } label: {
            HStack(spacing: DS.Spacing.xs) {
                Text(title)
                Text("\(count)").foregroundStyle(selected ? DS.Palette.onAccent.opacity(0.6) : DS.Palette.inkTertiary)
            }
            .font(DS.Typography.label)
            .tracking(DS.Tracking.label)
            .foregroundStyle(selected ? DS.Palette.onAccent : DS.Palette.ink)
            .padding(.horizontal, DS.Spacing.md)
            .frame(minHeight: 32)
            .background(selected ? DS.Palette.accent : DS.Palette.card, in: Capsule())
            .overlay { if !selected { Capsule().strokeBorder(DS.Palette.cardStroke, lineWidth: 1) } }
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("memories.filter.\(value ?? "all")")
    }

    @ViewBuilder
    private var content: some View {
        if store.phase == .loading, store.memories.isEmpty {
            ForEach(0 ..< 5, id: \.self) { _ in SkeletonBlock(height: 64).padding(.bottom, DS.Spacing.sm) }
        } else if store.memories.isEmpty, store.phase == .loaded {
            OmiEmptyState(
                L("noMemoriesYet"), systemImage: "brain.head.profile", message: L("createYourFirstMemory"),
                actionTitle: L("createMemoryTooltip")
            ) { showsNewMemory = true }
                .padding(.top, 72)
        } else {
            let memories = store.visible(matching: query, category: category)
            ForEach(memories) { memory in
                MemoryCard(memory: memory, source: source(of: memory))
                    .contentShape(Rectangle())
                    .contextMenu { actions(for: memory) }
                    .onTapGesture { editing = memory }
                if memory.id != memories.last?.id { OmiHairline() }
            }
        }
    }

    @ViewBuilder
    private func actions(for memory: Memory) -> some View {
        if let open = openSource(of: memory) {
            Button(action: open) { Label(L("openConversation"), systemImage: "bubble.left") }
        }
        Button { editing = memory } label: { Label(L("edit"), systemImage: "pencil") }
        Button {
            Task { await store.setBaseline(memory.id, pinned: !memory.isBaseline) }
        } label: {
            Label(memory.isBaseline ? L("unpinAsBaseline") : L("pinAsBaseline"), systemImage: memory.isBaseline ? "pin.slash" : "pin")
        }
        Button {
            Task { await store.setVisibility(memory.id, memory.visibility == .private ? .public : .private) }
        } label: {
            memory.visibility == .private
                ? Label(L("nativeMakePublic"), systemImage: "globe")
                : Label(L("nativeMakePrivate"), systemImage: "lock")
        }
        Button(role: .destructive) {
            withAnimation(DS.Motion.standard) { store.deleteWithUndo(memory.id) }
        } label: {
            Label(L("delete"), systemImage: "trash")
        }
    }

    /// The source conversation's title while it is loaded.
    private func source(of memory: Memory) -> String? {
        memory.conversationID.flatMap { id in
            conversations.conversations.first { $0.id == id }.map { $0.title.isEmpty ? L("untitledConversation") : $0.title }
        }
    }

    /// Opens the source conversation, fetching it when it is older than the loaded list.
    private func openSource(of memory: Memory) -> (() -> Void)? {
        guard let id = memory.conversationID else { return nil }
        return {
            Task { if let conversation = await conversations.conversation(id: id) { onOpenConversation(conversation) } }
        }
    }
}
