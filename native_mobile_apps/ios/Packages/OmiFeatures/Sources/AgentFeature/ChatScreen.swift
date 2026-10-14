import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// Chat with Omi: one long thread (the pinned main chat) with greeting and starters when empty,
/// streamed answers with the agent's tool steps, and the cards the app draws for what Omi did.
/// As a tab it also shows what Omi is working on right now ("Running now") and can be searched.
public struct ChatScreen: View {
    /// A full-screen page with its own close button, or the Chat tab (no close, search, Running now).
    public enum Mode: Sendable { case sheet, tab }

    /// Something the shell hands the chat tab: start listening, a question waiting in the
    /// composer, or searching the thread (the app header's search and "…" filters on the tab).
    /// Each new `id` is handled once.
    public struct Request: Equatable, Sendable {
        public let id: UUID
        public let draft: String
        public let dictate: Bool
        public let search: Bool
        public let filter: ChatThreadFilter?

        public init(draft: String = "", dictate: Bool = false, search: Bool = false, filter: ChatThreadFilter? = nil) {
            id = UUID()
            self.draft = draft
            self.dictate = dictate
            self.search = search
            self.filter = filter
        }

        /// The header's search on the Chat tab: the field opens, the keyboard comes up.
        public static func search() -> Request {
            Request(search: true)
        }

        /// A filter from the header's "…": the thread shows only those.
        public static func filter(_ filter: ChatThreadFilter) -> Request {
            Request(search: true, filter: filter)
        }

        /// The Ask bar's mic: the chat opens listening.
        public static func dictate() -> Request {
            Request(dictate: true)
        }

        /// A question in the composer, not sent yet (one Siri could not answer).
        public static func draft(_ text: String) -> Request {
            Request(draft: text)
        }
    }

    @Environment(ChatStore.self) var chat
    @Environment(SessionStore.self) var session
    @Environment(ConversationsStore.self) var conversations
    @Environment(TasksStore.self) var tasks
    @Environment(AgentStore.self) var agent
    @Environment(\.dismiss) var dismiss
    @Environment(CaptureStore.self) private var capture
    @Environment(VoicePlaybackStore.self) var voice
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.openURL) var openURL
    @State var network = NetworkMonitor()
    @State var draft = ""
    /// Whether the thread rests at its end (follows new words, hides the jump button).
    @State private var bottom = ChatBottomTracker()
    /// The widest a bubble gets (78 % of the thread's width).
    @State private var bubbleWidth: CGFloat = 300
    /// The history has been laid out at the end; only then may the top load older messages.
    @State private var historySettled = false
    @FocusState var composerFocused: Bool
    /// Speaks into the draft; nil hides the mic.
    let dictation: VoiceIntroStore?
    let startsDictation: Bool
    /// The draft before dictation began; dictated words are added after it.
    @State private var draftBeforeDictation = ""
    /// Dictation started from the filled circle: the question goes out when it stops.
    @State private var sendsAfterDictation = false
    /// A conversation an answer drew on was tapped (the shell closes the chat and opens it).
    let onOpenConversation: ((String) -> Void)?
    /// "Upgrade" on a quota answer (the shell opens Account).
    let onUpgrade: (() -> Void)?
    let mode: Mode
    let request: Request?
    @State var handledRequest: UUID?
    /// Searching the thread: the field and the filter chips show, the thread shows matches only.
    @State var isSearching = false
    @State var query = ""
    @State var filter: ChatThreadFilter?
    @FocusState var searchFocused: Bool
    /// A match the user tapped: the full thread comes back scrolled to it.
    @State var jumpTarget: String?
    /// The hand-over whose detail is open (from Running now or a finished run's row).
    @State var openRun: ActionItem?

    /// `draft`: a question already in the composer (one Siri could not answer), not sent yet.
    /// `request`: for the tab, what the shell asks for on switching to it (dictate, a draft).
    public init(
        mode: Mode = .sheet, dictation: VoiceIntroStore? = nil, startsDictation: Bool = false, draft: String = "",
        request: Request? = nil, onOpenConversation: ((String) -> Void)? = nil, onUpgrade: (() -> Void)? = nil
    ) {
        _draft = State(initialValue: draft)
        self.mode = mode
        self.request = request
        self.dictation = dictation
        self.startsDictation = startsDictation
        self.onOpenConversation = onOpenConversation
        self.onUpgrade = onUpgrade
    }

    public var body: some View {
        ScrollViewReader { proxy in
            tracksScrolling(ScrollView {
                list(proxy)
            }
            // Opens at the latest message; follows a streaming answer only while the user is at
            // the bottom, so scrolling up to read is never yanked back.
            .defaultScrollAnchor(.bottom)
            // The keyboard (or a growing composer) shrinks the list from below: the newest message
            // stays right above the composer instead of sliding under it.
            .defaultScrollAnchor(.bottom, for: .sizeChanges)
            .scrollIndicators(.hidden)
            .scrollDismissesKeyboard(.interactively))
            .onChange(of: followKey) { _, _ in
                if bottom.isAtBottom { proxy.scrollTo(Self.bottomID, anchor: .bottom) }
            }
            .onChange(of: jumpTarget) { _, target in
                guard let target else { return }
                // Back in the full thread: the tapped match comes into view once it is laid out.
                Task {
                    try? await Task.sleep(for: .milliseconds(120))
                    withAnimation(DS.Motion.snappy) { proxy.scrollTo(target, anchor: .center) }
                    jumpTarget = nil
                }
            }
            .onChange(of: chat.messages.last?.id) { _, _ in
                // A question the user just sent always comes into view (older pages land at the top
                // and leave the last message as it is).
                if chat.messages.last?.sender == .omi {
                    bottom.jumpedToBottom()
                    withAnimation(DS.Motion.snappy) { proxy.scrollTo(Self.bottomID, anchor: .bottom) }
                }
            }
            .task(id: chat.hasLoaded) {
                // Once the history is laid out (lazy rows measure as they appear), settle at the end.
                guard chat.hasLoaded else { return }
                for _ in 0 ..< 3 {
                    proxy.scrollTo(Self.bottomID, anchor: .bottom)
                    try? await Task.sleep(for: .milliseconds(80))
                }
                historySettled = true
            }
            .task(id: composerFocused) {
                // Typing starts at the newest message: once the keyboard has come up (scrolling
                // during its animation would fight it), bring the end into view if it is not.
                guard composerFocused else { return }
                do { try await Task.sleep(for: .milliseconds(350)) } catch { return }
                bottom.jumpedToBottom()
                withAnimation(DS.Motion.snappy) { proxy.scrollTo(Self.bottomID, anchor: .bottom) }
            }
            .overlay {
                if !chat.hasLoaded { loadingOrFailed }
            }
            .overlay(alignment: .bottom) {
                // Above the composer (the overlay keeps to the list's safe area), only while the end
                // is out of view by more than the threshold, so it never sits on the last bubble.
                if !bottom.isAtBottom, chat.hasLoaded, !chat.messages.isEmpty, !isFiltering {
                    Button {
                        DSHaptics.selection()
                        withAnimation(DS.Motion.snappy) { proxy.scrollTo(Self.bottomID, anchor: .bottom) }
                        bottom.jumpedToBottom()
                    } label: {
                        Image(systemName: "arrow.down")
                            .font(.body.weight(.semibold))
                            .foregroundStyle(DS.Palette.ink)
                            .frame(width: 40, height: 40)
                            .omiSurface(Circle(), interactive: true)
                    }
                    .buttonStyle(.plain)
                    .padding(.bottom, DS.Spacing.sm)
                    .transition(.scale.combined(with: .opacity))
                    .accessibilityLabel(L("nativeJumpToLatest"))
                }
            }
            .animation(DS.Motion.snappy, value: bottom.isAtBottom)
        }
        .modifier(ChatPageFrame(mode: mode, header: header))
        .safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: DS.Spacing.sm) {
                if chat.messages.isEmpty, chat.hasLoaded, !isFiltering {
                    // Fades instead of collapsing while typing, so the composer does not jump.
                    starters
                        .opacity(draft.isEmpty ? 1 : 0)
                        .allowsHitTesting(draft.isEmpty)
                }
                ChatComposer(
                    draft: $draft, focused: $composerFocused, isDictating: isDictating, canDictate: canDictate,
                    canSend: canSend, level: dictation?.level ?? 0, sendsAfterDictation: sendsAfterDictation,
                    onSend: send,
                    onDictate: { thenSend in
                        sendsAfterDictation = thenSend
                        Task { await startDictation() }
                    },
                    onStopDictation: stopDictation
                )
            }
            // Messages scroll on under the composer and blur behind its material, down to the
            // screen's edge (and to the keyboard's top while it is up).
            .background { ComposerBackdrop() }
        }
        .task {
            // What the agent does to tasks shows as cards under its answers.
            chat.tasks = tasks
            await chat.loadHistory()
        }
        .task { if startsDictation { await startDictation() } }
        .task(id: request?.id) { await handle(request) }
        .task { await debugLaunch() }
        .sheet(item: $openRun) { task in
            HandOverSheet(task: task, conversationTitle: conversationTitle(for: task))
        }
        .task {
            // -omiChatFocus YES: the keyboard up, for screenshots of the composer on top of it.
            guard DebugLaunch.flag("omiChatFocus") else { return }
            try? await Task.sleep(for: .seconds(1.5))
            composerFocused = true
        }
        .onAppear {
            network.start()
            // Finished answers are read aloud while the chat is on screen (as the reply mode allows).
            let voice = voice
            chat.onAnswer = { voice.answerArrived($0) }
        }
        .onChange(of: network.isOffline, initial: true) { _, offline in chat.networkUnavailable = offline }
        .onChange(of: scenePhase) { _, phase in if phase != .active { voice.stop() } }
        .onChange(of: isDictating) { _, listening in
            // Talking from the filled circle: the question goes out once listening ends.
            guard !listening, sendsAfterDictation else { return }
            sendsAfterDictation = false
            send()
        }
        .onChange(of: dictation?.transcript ?? "") { _, words in
            guard isDictating, !words.isEmpty else { return }
            draft = draftBeforeDictation.isEmpty ? words : draftBeforeDictation + " " + words
        }
        .onDisappear {
            dictation?.stop()
            network.stop()
            chat.onAnswer = nil
            voice.stop()
        }
    }

    var isDictating: Bool {
        guard let dictation else { return false }
        return dictation.phase == .listening || dictation.phase == .starting
    }

    /// The phone microphone is busy while the phone itself records a conversation.
    var canDictate: Bool {
        dictation != nil && !(capture.isLive && capture.source == .phone)
    }

    func startDictation() async {
        guard let dictation, canDictate else { return }
        voice.stop()
        DSHaptics.tap(.medium)
        draftBeforeDictation = draft
        await dictation.start(source: .phone, language: Locale.current.language.languageCode?.identifier ?? "en")
    }

    private func stopDictation() {
        dictation?.stop()
        DSHaptics.tap(.light)
    }

    /// The thread inside the scroll view: greeting, older pages, the rows (or the matches), the end.
    private func list(_ proxy: ScrollViewProxy) -> some View {
        // Plain VStack: a lazy stack estimates rows it has not measured, so the list's height
        // (and with it "at the bottom") kept changing after the user had scrolled down.
        VStack(alignment: .leading, spacing: DS.Spacing.md) {
            if chat.messages.isEmpty, chat.hasLoaded, chat.chatApp == nil, !isFiltering {
                // Lined up with the app header's words above.
                greeting.padding(.horizontal, DS.Spacing.gutter - DS.Spacing.lg)
            }
            if chat.hasEarlier, !isFiltering {
                // Reaching the top loads the page before it, again while it stays on screen
                // (the pause lets a prepended page scroll it away, which cancels the task).
                ProgressView()
                    .frame(maxWidth: .infinity)
                    .task(id: "\(historySettled)|\(chat.messages.count)") {
                        guard historySettled else { return }
                        do { try await Task.sleep(for: .milliseconds(200)) } catch { return }
                        await loadEarlier(proxy)
                    }
            }
            if isFiltering {
                matches(proxy)
            } else {
                thread
            }
            // The end of the list, to scroll to.
            Color.clear.frame(height: 1).id(Self.bottomID)
        }
        .padding(.horizontal, DS.Spacing.lg)
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { width in
            bubbleWidth = (width - 2 * DS.Spacing.lg) * 0.78
        }
        .environment(\.chatBubbleWidth, bubbleWidth)
        // Clear of the top bar's fade while the thread rests at its start.
        .padding(.top, DS.Spacing.md)
        .padding(.bottom, DS.Spacing.lg)
    }

    /// Where the thread rests: at its end (the jump button, following new words).
    private func tracksScrolling(_ list: some View) -> some View {
        list
            .onScrollGeometryChange(for: Bool.self) { geometry in
                ChatBottomTracker.isAtBottom(
                    offsetY: geometry.contentOffset.y, containerHeight: geometry.containerSize.height,
                    bottomInset: geometry.contentInsets.bottom, contentHeight: geometry.contentSize.height
                )
            } action: { _, atBottom in
                // Only the user's own scrolling leaves the bottom: a growing answer or the keyboard
                // never stops the list from following.
                bottom.geometryChanged(atBottom: atBottom)
            }
            .onScrollPhaseChange { _, phase in
                // Scrolling ended (also after a fling that bounced at the end): believe where it rests.
                bottom.phaseChanged(isIdle: phase == .idle)
            }
    }

    private static let bottomID = "chat.bottom"

    /// The rows, grouped as in Messages (a few points inside a group, more between groups).
    private var thread: some View {
        let rows = self.rows
        let positions = groupPositions(rows)
        return VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(rows.enumerated()), id: \.element.id) { index, row in
                Group {
                    switch row {
                    case let .message(message):
                        bubble(message, position: positions[message.id] ?? .alone)
                    case let .run(run):
                        RunOutcomeRow(run: run) { open(run) }.omiColumn()
                    case let .runs(runs):
                        ChatCardStack(items: runs) { run in RunOutcomeRow(run: run) { open(run) } }.omiColumn()
                    case let .day(date):
                        DayDivider(date: date)
                    }
                }
                .padding(.top, Self.gap(before: row, at: index, positions: positions))
                .id(row.id)
            }
        }
    }

    /// Changes whenever the last answer grows: new text, a new step, or a finished state.
    private var followKey: String {
        guard let last = chat.messages.last else { return "" }
        let cards = chat.cards(for: last.id).count + (chat.pendingDeviceToolMessageID == last.id ? 1 : 0)
        let state = "\(last.failure?.rawValue ?? "")|\(chat.isStreaming)|\(cards)|\(finishedRuns.count)"
        return "\(last.id)|\(last.text.count)|\(last.steps.count)|\(state)"
    }
}
