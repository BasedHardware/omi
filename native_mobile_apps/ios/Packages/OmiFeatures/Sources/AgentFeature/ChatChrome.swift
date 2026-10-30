import OmiDesign
import OmiService
import SwiftUI

/// The chat's one "…" menu. On the Chat tab it sits in the app header: who you talk to (Omi or a
/// chat app, Flutter `chat_apps_drawer`), what to show (the thread's filters), and Clear chat
/// behind a confirmation (Flutter `chat/page`). While a chat app is chosen its picture is the
/// menu's label. The full-screen chat names who you talk to in its title instead.
public struct ChatMenu: View {
    @Environment(ChatStore.self) private var chat
    @Environment(VoicePlaybackStore.self) private var voice
    @State private var confirmsClear = false
    @State private var clearFailed = false
    let showsTalkTo: Bool
    let onFilter: ((ChatThreadFilter) -> Void)?

    /// `showsTalkTo`: the "Talk to" section (the tab; the full-screen chat has it in its title).
    /// `onFilter`: the thread's filters (the tab; they open its search with the filter on).
    public init(showsTalkTo: Bool = true, onFilter: ((ChatThreadFilter) -> Void)? = nil) {
        self.showsTalkTo = showsTalkTo
        self.onFilter = onFilter
    }

    public var body: some View {
        Menu {
            if showsTalkTo { talkTo }
            if let onFilter, hasMessages {
                Section(L("nativeChatShowOnly")) {
                    ForEach(ChatThreadFilter.allCases, id: \.self) { filter in
                        Button { onFilter(filter) } label: {
                            Label(ChatThreadFilter.title(filter), systemImage: ChatThreadFilter.symbol(filter))
                        }
                    }
                }
            }
            if hasMessages {
                Button(role: .destructive) { confirmsClear = true } label: { Label(L("clearChat"), systemImage: "trash") }
                    .disabled(chat.isStreaming)
            }
        } label: {
            if let app = chat.chatApp, showsTalkTo {
                AsyncImage(url: app.imageURL) { $0.resizable().scaledToFill() } placeholder: { DS.Palette.fill }
                    .frame(width: 26, height: 26)
                    .clipShape(Circle())
                    .frame(width: DS.Size.headerButton, height: DS.Size.headerButton)
                    .contentShape(Rectangle())
            } else {
                OmiCircleIcon("ellipsis")
            }
        }
        .accessibilityLabel(L("moreOptions"))
        .accessibilityValue(showsTalkTo ? chat.chatApp?.name ?? "Omi" : "")
        .accessibilityIdentifier("chat.menu")
        .task { if showsTalkTo { await chat.loadChatApps() } }
        .confirmationDialog(L("clearChat"), isPresented: $confirmsClear, titleVisibility: .visible) {
            Button(L("clearChat"), role: .destructive) {
                voice.stop()
                Task { clearFailed = !(await chat.clearChat()) }
            }
            Button(L("cancel"), role: .cancel) {}
        } message: {
            Text(L("clearChatConfirm"))
        }
        .alert(L("nativeChatClearFailed"), isPresented: $clearFailed) {
            Button(L("ok"), role: .cancel) {}
        }
    }

    private var hasMessages: Bool {
        chat.hasLoaded && !chat.messages.isEmpty
    }

    /// Omi, or one of the enabled apps that can chat; each keeps its own history. Switching waits
    /// until an answer has finished.
    @ViewBuilder
    private var talkTo: some View {
        Section(L("nativeTalkTo")) {
            Button { Task { await chat.talk(to: nil) } } label: {
                if chat.chatApp == nil { Label("Omi", systemImage: "checkmark") } else { Text(verbatim: "Omi") }
            }
            ForEach(chat.chatApps) { app in
                Button { Task { await chat.talk(to: app) } } label: {
                    if chat.chatApp?.id == app.id { Label(app.name, systemImage: "checkmark") } else { Text(app.name) }
                }
            }
            if chat.chatApps.isEmpty {
                Text(L("nativeNoChatApps"))
            }
        }
        .disabled(chat.isStreaming)
    }
}

extension ChatThreadFilter {
    static func title(_ filter: ChatThreadFilter) -> String {
        switch filter {
        case .approvals: L("nativeChatFilterApprovals")
        case .drafts: L("nativeChatFilterDrafts")
        case .jobs: L("nativeChatFilterJobs")
        case .files: L("nativeChatFilterFiles")
        }
    }

    static func symbol(_ filter: ChatThreadFilter) -> String {
        switch filter {
        case .approvals: "checkmark.seal"
        case .drafts: "square.and.pencil"
        case .jobs: "sparkles"
        case .files: "paperclip"
        }
    }
}

extension View {
    /// The chat's top bar (the full-screen chat's title, search, Running now) pinned on top, solid
    /// behind its content and fading out below it: messages leave under a soft edge, never a hard
    /// cut, also when the bar is empty (the tab under the app header).
    func chatTopBar(@ViewBuilder _ bar: () -> some View) -> some View {
        safeAreaInset(edge: .top, spacing: 0) {
            bar().background(alignment: .top) {
                VStack(spacing: 0) {
                    DS.Palette.background
                    LinearGradient(
                        colors: [DS.Palette.background, DS.Palette.background.opacity(0)],
                        startPoint: .top, endPoint: .bottom
                    )
                    .frame(height: chatFadeHeight)
                }
                .padding(.bottom, -chatFadeHeight)
                .ignoresSafeArea(edges: .top)
                .allowsHitTesting(false)
            }
        }
    }
}

/// How far the top fade reaches over the messages below it.
private let chatFadeHeight: CGFloat = 28

/// The chat page around its thread. Full screen: on the page color under its top bar. As a tab:
/// on the shell's own background (no band of a second color under the app header), the bar's
/// lines (search, offline, Running now) above the thread, and the thread itself fading out at its
/// top edge, so messages leave softly instead of being cut off.
struct ChatPageFrame<Header: View>: ViewModifier {
    let mode: ChatScreen.Mode
    let header: Header

    func body(content: Content) -> some View {
        switch mode {
        case .sheet:
            content
                .background(DS.Palette.background.ignoresSafeArea())
                .chatTopBar { header }
        case .tab:
            VStack(spacing: 0) {
                header
                content.mask {
                    VStack(spacing: 0) {
                        LinearGradient(colors: [.clear, .black], startPoint: .top, endPoint: .bottom)
                            .frame(height: chatFadeHeight)
                        Color.black
                    }
                    // The composer below is not part of the fade.
                    .ignoresSafeArea(.container, edges: .bottom)
                }
            }
        }
    }
}

/// Under the header while the phone has no connection (Flutter `ChatOfflineHint`).
struct OfflineHint: View {
    var body: some View {
        Label(L("chatOfflineHint"), systemImage: "wifi.slash")
            .font(DS.Typography.caption)
            .foregroundStyle(DS.Palette.inkSecondary)
            .padding(.horizontal, DS.Spacing.md)
            .padding(.vertical, DS.Spacing.sm)
            .frame(maxWidth: .infinity)
            .background(DS.Palette.fill, in: Capsule())
            .transition(.move(edge: .top).combined(with: .opacity))
            .accessibilityAddTraits(.updatesFrequently)
    }
}
