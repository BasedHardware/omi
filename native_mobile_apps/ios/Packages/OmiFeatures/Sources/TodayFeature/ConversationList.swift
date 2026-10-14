import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// Home's conversations by day, each day led by its recap: quiet rows between hairlines, no card
/// per row. The long-press menu has star, move, select, reprocess and delete (with undo). One quiet filter button beside the first day:
/// all, starred, a folder.
struct ConversationList: View {
    @Environment(ConversationsStore.self) private var conversations
    let onOpenConversation: (Conversation) -> Void
    let onOpenRecap: (DailySummary) -> Void
    /// `nil` outside selection mode.
    @Binding var selection: Set<String>?
    @State private var moving: MoveRequest?
    @State private var showsFolders = false
    @State private var showsMap = DebugLaunch.flag("omiConversationMap")
    /// The one-day page (`ConversationListExtras.swift`).
    @State private var day: DayRequest?

    var body: some View {
        Group {
            if conversations.phase == .loading, conversations.conversations.isEmpty {
                ForEach(0 ..< 4, id: \.self) { _ in SkeletonBlock(height: 68).padding(.top, DS.Spacing.sm) }
            } else if conversations.conversations.isEmpty, case let .failed(reason) = conversations.phase {
                failure(reason)
            } else if conversations.conversations.isEmpty, conversations.filter == .all {
                empty
            } else if conversations.sections.isEmpty {
                header(nil)
                Text(conversations.isLoadingFiltered ? L("loading") : L("nativeNothingHere"))
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .padding(.top, DS.Spacing.md)
            } else {
                ForEach(Array(conversations.sections.enumerated()), id: \.element.id) { index, section in
                    if index == 0 {
                        header(section.day)
                    } else {
                        dayTitle(section.day)
                    }
                    // Text-first, as in the ChatGPT app: the recap first, then the conversations.
                    VStack(spacing: 0) {
                        if selection == nil, let slot = conversations.recapSlot(for: section.day) {
                            RecapRow(kind: slot, onOpen: onOpenRecap)
                        }
                        ForEach(section.conversations) { conversation in
                            row(conversation)
                        }
                    }
                }
            }
        }
        .task { await conversations.loadFolders() }
        .sheet(item: $moving) { request in
            MoveToFolderSheet(ids: request.ids) { selection = nil }.presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $showsFolders) { FoldersSheet().presentationDetents([.medium, .large]) }
        .task { day = await DayConversationsScreen.requestForDebugging() }
        .fullScreenCover(item: $day) { request in
            DayConversationsScreen(store: conversations.makeDayStore(day: request.day), picking: request.picksDay) { conversation in
                day = nil
                onOpenConversation(conversation)
            }
        }
        .fullScreenCover(isPresented: $showsMap) {
            ConversationMapScreen(conversations: conversations.conversations) { conversation in
                showsMap = false
                onOpenConversation(conversation)
            }
        }
    }

    // MARK: Rows

    /// Where a row's text starts (after the emoji tile): separators begin there, as in iOS lists.
    static let textInset = DS.Size.tile + DS.Spacing.md

    private func row(_ conversation: Conversation) -> some View {
        Button {
            if selection != nil {
                toggle(conversation.id)
            } else {
                onOpenConversation(conversation)
            }
        } label: {
            ConversationRow(conversation, isSelected: selection.map { $0.contains(conversation.id) }, style: .plain)
                .padding(.vertical, DS.Spacing.sm + 1)
        }
        .buttonStyle(.hapticTap)
        // Behind the paywall: frosted, and a tap opens the plans.
        .overlay { if conversation.isLocked, selection == nil { LockedRowCover() } }
        .overlay(alignment: .trailing) {
            if conversation.summaryFailed, selection == nil {
                Button(L("retry")) { Task { await conversations.reprocess(conversation.id) } }
                    .buttonStyle(.omiPillSubtle)
            }
        }
        // Star and delete live in the long-press menu: a horizontal row swipe would fight the
        // sideways swipe between Home, Tasks and Memories.
        .contextMenu { if selection == nil { menu(conversation) } }
        .onAppear {
            if conversation.id == conversations.visible.last?.id { Task { await conversations.loadMore() } }
        }
    }

    @ViewBuilder
    private func menu(_ conversation: Conversation) -> some View {
        Button { Task { await conversations.setStarred(conversation.id, !conversation.isStarred) } } label: {
            conversation.isStarred
                ? Label(L("unstarConversation"), systemImage: "star.slash")
                : Label(L("starConversation"), systemImage: "star")
        }
        Button { moving = MoveRequest(ids: [conversation.id]) } label: {
            Label(L("moveToFolder"), systemImage: "folder")
        }
        Button { selection = [conversation.id] } label: { Label(L("selectOption"), systemImage: "checkmark.circle") }
        if conversation.summaryFailed || conversation.status == .completed {
            Button { Task { await conversations.reprocess(conversation.id) } } label: {
                Label(L("reprocessConversation"), systemImage: "arrow.clockwise")
            }
        }
        Divider()
        Button(role: .destructive) { delete([conversation.id]) } label: { Label(L("delete"), systemImage: "trash") }
    }

    private func toggle(_ id: String) {
        DSHaptics.selection()
        if selection?.contains(id) == true { selection?.remove(id) } else { selection?.insert(id) }
    }

    private func delete(_ ids: [String]) {
        DSHaptics.tap(.medium)
        withAnimation(DS.Motion.standard) { conversations.deleteWithUndo(ids) }
    }

    // MARK: Header and filter

    /// The first day's title with the filter beside it (or just the filter when nothing matches).
    private func header(_ day: Date?) -> some View {
        HStack(spacing: DS.Spacing.sm) {
            if let day {
                Text(Formatting.dayTitle(day)).font(DS.Typography.sectionLabel).foregroundStyle(DS.Palette.inkSecondary)
            }
            Spacer(minLength: 0)
            if conversations.filter != .all {
                Button { Task { await conversations.setFilter(.all) } } label: {
                    HStack(spacing: DS.Spacing.xs) {
                        Text(filterName)
                        Image(systemName: "xmark").font(.system(size: 10, weight: .bold))
                    }
                    .font(DS.Typography.caption.weight(.semibold))
                    .foregroundStyle(DS.Palette.agent)
                    .padding(.horizontal, DS.Spacing.md)
                    .padding(.vertical, DS.Spacing.xs + 2)
                    .background(DS.Palette.agentSoft, in: Capsule())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(L("nativeClearFilter", filterName))
            }
            filterMenu
        }
        .padding(.top, DS.Spacing.md)
        .padding(.bottom, DS.Spacing.xxs)
    }

    private func dayTitle(_ day: Date) -> some View {
        Text(Formatting.dayTitle(day))
            .font(DS.Typography.sectionLabel)
            .foregroundStyle(DS.Palette.inkSecondary)
            .padding(.top, DS.Spacing.lg)
            .padding(.bottom, DS.Spacing.xxs)
    }

    private var filterMenu: some View {
        Menu {
            Section {
                filterButton(L("nativeAllConversations"), systemImage: "tray.full", .all)
                filterButton(L("starred"), systemImage: "star", .starred)
            }
            Section(L("nativeFolders")) {
                ForEach(conversations.folders) { folder in
                    filterButton(folder.name, systemImage: "folder", .folder(folder.id))
                }
                Button { showsFolders = true } label: { Label(L("nativeEditFolders"), systemImage: "folder.badge.gearshape") }
            }
            DisplayOptionsMenu()
            Button { day = DayRequest(day: .now, picksDay: true) } label: { Label(L("filterByDate"), systemImage: "calendar") }
                .accessibilityIdentifier("conversations.day")
            Button { showsMap = true } label: { Label(L("conversationMap"), systemImage: "map") }
                .accessibilityIdentifier("conversations.map")
            Button { selection = [] } label: { Label(L("selectOption"), systemImage: "checkmark.circle") }
        } label: {
            Image(systemName: "line.3.horizontal.decrease")
                .font(.system(size: 16, weight: .regular))
                .foregroundStyle(conversations.filter == .all ? DS.Palette.inkSecondary : DS.Palette.agent)
                .frame(width: 36, height: 36)
                .contentShape(Rectangle())
        }
        .accessibilityLabel(L("nativeFilterConversations"))
        .accessibilityIdentifier("conversations.filter")
    }

    private func filterButton(_ title: String, systemImage: String, _ filter: ConversationFilter) -> some View {
        Button {
            Task { await conversations.setFilter(filter) }
        } label: {
            Label(title, systemImage: conversations.filter == filter ? "checkmark" : systemImage)
        }
    }

    private var filterName: String {
        switch conversations.filter {
        case .all: L("nativeAllConversations")
        case .starred: L("starred")
        case let .folder(id): conversations.folder(id)?.name ?? L("nativeFolders")
        }
    }

    // MARK: Empty and failure

    private func failure(_ reason: String) -> some View {
        OmiEmptyState(
            L("nativeCouldNotLoadConversations"), systemImage: "wifi.exclamationmark", message: reason,
            actionTitle: L("tryAgain")
        ) { Task { await conversations.load() } }
            .padding(.top, 72)
    }

    /// Nothing recorded yet: the pendant as a hero, a serif line, one calm sentence.
    private var empty: some View {
        VStack(spacing: DS.Spacing.md) {
            OmiPendantIllustration(size: 132)
                .padding(.bottom, DS.Spacing.lg)
            Text(L("nativeNoConversationsYet"))
                .font(DS.Typography.title)
                .foregroundStyle(DS.Palette.ink)
            Text(L("nativeNoConversationsToday"))
                .font(DS.Typography.callout)
                .foregroundStyle(DS.Palette.inkSecondary)
                .frame(maxWidth: 300)
        }
        .multilineTextAlignment(.center)
        .frame(maxWidth: .infinity)
        .padding(.top, DS.Spacing.section)
        .accessibilityElement(children: .combine)
    }
}

/// The conversations a "Move to folder…" sheet is for.
struct MoveRequest: Identifiable {
    let ids: [String]
    var id: String {
        ids.joined(separator: ",")
    }
}
