import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// A locked conversation's row (behind the paywall): frosted, with "Upgrade to Unlimited"
/// (Flutter `OmiLockedPreview`). Tapping anywhere opens the plans.
struct LockedRowCover: View {
    @Environment(\.openUpgrade) private var openUpgrade

    var body: some View {
        Button { openUpgrade() } label: {
            Label(L("upgradeToUnlimited"), systemImage: "lock")
                .font(DS.Typography.callout.weight(.semibold))
                .foregroundStyle(DS.Palette.ink)
                .padding(.horizontal, DS.Spacing.md)
                .padding(.vertical, DS.Spacing.sm)
                .omiSurface(Capsule())
        }
        .buttonStyle(.plain)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: DS.Radius.card, style: .continuous))
        .accessibilityIdentifier("conversation.locked")
    }
}

/// Home's filter menu: discarded conversations on or off, and how short a conversation may be.
struct DisplayOptionsMenu: View {
    @Environment(ConversationsStore.self) private var conversations

    var body: some View {
        Section(L("conversationDisplay")) {
            Button {
                Task { await conversations.setShowsDiscarded(!conversations.display.showsDiscarded) }
            } label: {
                Label(
                    L("showDiscardedConversations"),
                    systemImage: conversations.display.showsDiscarded ? "checkmark" : "trash.slash"
                )
            }
            .accessibilityIdentifier("conversations.showDiscarded")
            Menu {
                choice(L("showShortConversations"), selected: conversations.display.hidesShorterThan == nil) {
                    conversations.hideShorter(than: nil)
                }
                ForEach(ConversationsStore.shortThresholds, id: \.self) { seconds in
                    choice(L("nativeHideUnderMinutes", String(seconds / 60)), selected: conversations.display.hidesShorterThan == seconds) {
                        conversations.hideShorter(than: seconds)
                    }
                }
            } label: {
                Label(L("shortConversationThreshold"), systemImage: "timer")
            }
            .accessibilityIdentifier("conversations.shortThreshold")
        }
    }

    private func choice(_ title: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            if selected { Label(title, systemImage: "checkmark") } else { Text(title) }
        }
    }
}

/// "Go to a day": a calendar to pick one day (never after today).
struct DayPickerSheet: View {
    @State var day: Date
    let onPick: (Date) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            DatePicker(L("filterByDate"), selection: $day, in: ...Date.now, displayedComponents: .date)
                .datePickerStyle(.graphical)
                .tint(DS.Palette.agent)
                .padding(.horizontal, DS.Spacing.gutter)
                .navigationTitle(L("filterByDate"))
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button(L("cancel")) { dismiss() } }
                    ToolbarItem(placement: .confirmationAction) {
                        Button(L("nativeShowDay")) {
                            dismiss()
                            onPick(day)
                        }
                        .accessibilityIdentifier("day.show")
                    }
                }
        }
    }
}

/// One day's conversations (Flutter `day_conversations_page`): the previous and next day, a
/// calendar to jump, pull to refresh, "show more".
struct DayConversationsScreen: View {
    @State var store: DayConversationsStore
    /// Opens on the calendar, so the day is picked first.
    @State var picking = true
    let onOpenConversation: (Conversation) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: DS.Spacing.md) {
                    switch store.phase {
                    case .loading:
                        ForEach(0 ..< 4, id: \.self) { _ in SkeletonBlock(height: 68) }
                    case .failed:
                        VStack(spacing: DS.Spacing.md) {
                            Text(L("somethingWentWrong")).font(DS.Typography.cardTitle)
                            Button(L("tryAgain")) { Task { await store.load() } }.buttonStyle(.omiPillSubtle)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.top, 80)
                    case .loaded:
                        if store.conversations.isEmpty {
                            Text(L("noConversationsOnDate", Formatting.dayTitle(store.day)))
                                .font(DS.Typography.callout)
                                .foregroundStyle(DS.Palette.inkSecondary)
                                .frame(maxWidth: .infinity)
                                .padding(.top, 80)
                        }
                        ForEach(store.conversations) { conversation in
                            Button { open(conversation) } label: { ConversationRow(conversation, style: .plain) }
                                .buttonStyle(.hapticTap)
                                .overlay { if conversation.isLocked { LockedRowCover() } }
                        }
                        if store.hasMore {
                            Button { Task { await store.loadMore() } } label: {
                                if store.isLoadingMore { ProgressView() } else { Label(L("showMore"), systemImage: "chevron.down") }
                            }
                            .buttonStyle(.omiPillSubtle)
                            .frame(maxWidth: .infinity)
                        }
                    }
                }
                .padding(.horizontal, DS.Spacing.gutter)
                .padding(.bottom, DS.Spacing.section)
            }
            .refreshable { await store.load() }
            .background(DS.Palette.background)
            .navigationTitle(Formatting.dayTitle(store.day))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(L("done")) { dismiss() } }
                ToolbarItemGroup(placement: .primaryAction) {
                    Button { Task { await store.go(by: -1) } } label: { Image(systemName: "chevron.left") }
                        .accessibilityLabel(L("previousDay"))
                    Button { Task { await store.go(by: 1) } } label: { Image(systemName: "chevron.right") }
                        .disabled(!store.canGoForward())
                        .accessibilityLabel(L("nextDay"))
                    Button { picking = true } label: { Image(systemName: "calendar") }
                        .accessibilityLabel(L("filterByDate"))
                }
            }
            .sheet(isPresented: $picking) {
                DayPickerSheet(day: store.day) { day in Task { await store.show(day) } }.presentationDetents([.medium, .large])
            }
            .task { if store.conversations.isEmpty { await store.load() } }
        }
    }

    /// `-omiOpenDay YES` (the calendar first) or `-omiOpenDay 2026-10-04` opens this page once Home
    /// has settled (scripted screenshots; Debug only).
    static func requestForDebugging() async -> DayRequest? {
        #if DEBUG
            guard let value = UserDefaults.standard.string(forKey: "omiOpenDay") else { return nil }
            try? await Task.sleep(for: .seconds(1.5))
            let format = DateFormatter()
            format.dateFormat = "yyyy-MM-dd"
            return format.date(from: value).map { DayRequest(day: $0, picksDay: false) } ?? DayRequest(day: .now, picksDay: true)
        #else
            return nil
        #endif
    }

    private func open(_ conversation: Conversation) {
        dismiss()
        onOpenConversation(conversation)
    }
}

/// The day the one-day page opens at; `picksDay` opens its calendar first.
struct DayRequest: Identifiable {
    let day: Date
    let picksDay: Bool
    var id: Date {
        day
    }
}
