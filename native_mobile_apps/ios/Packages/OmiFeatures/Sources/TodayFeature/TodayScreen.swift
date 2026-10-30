import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// Home: what Omi hears now, "Needs you" (at most five cards, then "Later" and "All tasks"), then
/// every conversation by day (each day led by its recap), goals at the end.
public struct TodayScreen: View {
    @Environment(ConversationsStore.self) private var conversations
    @Environment(TasksStore.self) private var tasks
    @Environment(AgentStore.self) private var agent
    @Environment(CaptureStore.self) private var capture
    @Environment(VoicesStore.self) private var voices
    @Environment(GoalsStore.self) private var goals
    private let onOpenConversation: (Conversation) -> Void
    private let onHandOver: (ActionItem) -> Void
    private let onOpenRun: (String) -> Void
    private let onOpenDevice: () -> Void
    private let onOpenRecap: (DailySummary) -> Void
    private let onOpenSiriTip: () -> Void
    private let onOpenAllTasks: () -> Void
    /// A task card's detail (text, due date, where it came from).
    private let onOpenTask: (ActionItem) -> Void
    /// The Chat tab with this question in the composer.
    private let onAskOmi: (String) -> Void
    /// Conversations picked for a bulk action; `nil` outside selection mode.
    @State private var selection: Set<String>?
    /// "For you" nudges (the proactivity feed), made once this screen exists.
    @State private var forYou: ForYouStore?
    /// A task card just swiped to Later, while "Undo" is offered.
    @State private var laterUndo: LaterUndo?

    public init(
        onOpenConversation: @escaping (Conversation) -> Void,
        onHandOver: @escaping (ActionItem) -> Void,
        onOpenRun: @escaping (String) -> Void,
        onOpenDevice: @escaping () -> Void,
        onOpenRecap: @escaping (DailySummary) -> Void,
        onOpenSiriTip: @escaping () -> Void,
        onOpenAllTasks: @escaping () -> Void,
        onOpenTask: @escaping (ActionItem) -> Void,
        onAskOmi: @escaping (String) -> Void
    ) {
        self.onOpenTask = onOpenTask
        self.onAskOmi = onAskOmi
        self.onOpenConversation = onOpenConversation
        self.onHandOver = onHandOver
        self.onOpenRun = onOpenRun
        self.onOpenDevice = onOpenDevice
        self.onOpenRecap = onOpenRecap
        self.onOpenSiriTip = onOpenSiriTip
        self.onOpenAllTasks = onOpenAllTasks
    }

    public var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                if capture.phase != .idle { LiveBar().padding(.bottom, DS.Spacing.lg) }
                CaptureRecoveryBanner()
                    .padding(.bottom, capture.recovery == nil && capture.notice == nil ? 0 : DS.Spacing.lg)
                NeedsYouSection(
                    laterUndo: $laterUndo, forYou: forYou, onOpenRun: onOpenRun, onHandOver: onHandOver,
                    onOpenConversation: openConversation, onOpenSiriTip: onOpenSiriTip, onOpenAllTasks: onOpenAllTasks,
                    onOpenTask: onOpenTask, onAskOmi: onAskOmi
                )
                ConversationList(onOpenConversation: onOpenConversation, onOpenRecap: onOpenRecap, selection: $selection)
                GoalsCard()
            }
            .padding(.horizontal, DS.Spacing.gutter)
            .padding(.top, DS.Spacing.sm)
            .padding(.bottom, DS.Spacing.section)
        }
        .scrollIndicators(.hidden)
        .safeAreaInset(edge: .bottom) {
            if selection != nil {
                SelectionBar(selection: $selection).transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(DS.Motion.standard, value: selection == nil)
        .overlay(alignment: .bottom) {
            ZStack {
                GoalUndoToast()
                LaterUndoToast(undo: $laterUndo)
            }
            .padding(.bottom, DS.Spacing.lg)
        }
        .animation(DS.Motion.standard, value: capture.recovery)
        .refreshable {
            async let list: Void = conversations.load()
            async let open: Void = tasks.load()
            async let recaps: Void = conversations.loadRecaps()
            async let filtered: Void = conversations.reloadFiltered()
            async let goalList: Void = goals.load()
            async let nudges: Void = forYou?.load() ?? ()
            async let recommendations: Void = agent.loadRecommendations()
            async let prompts: Void = voices.loadPrompts()
            _ = await (list, open, recaps, filtered, goalList, nudges, recommendations, prompts)
        }
        .task { if conversations.phase == .idle { await conversations.load() } }
        .task { await agent.loadRecommendations() }
        .task {
            let store = forYou ?? conversations.makeForYouStore()
            forYou = store
            await store.load()
        }
        .task { await voices.loadPrompts() }
        .task { if goals.phase == .idle { await goals.load() } }
        // Reloads when the list changes: a new conversation can mean a new day to recap.
        .task(id: conversations.conversations.count) { await conversations.loadRecaps() }
        .task(id: tasks.tasks.count) { await agent.loadWorkstreams(for: tasks.tasks) }
        // The day's tidy-up: once the tasks are in, on the first visit after 6:00.
        .task(id: tasks.phase == .loaded) { await tidyUp() }
    }

    /// `-omiNoTidyUp YES` keeps it off (an account that must not change), `-omiTidyUpNow YES` runs it now.
    private func tidyUp() async {
        let force = DebugLaunch.flag("omiTidyUpNow")
        guard tasks.phase == .loaded, !DebugLaunch.flag("omiNoTidyUp"), force || tasks.tidyUpIsDue() else { return }
        // The words behind each task help it spot requests made of someone else.
        await conversations.loadSources(for: tasks.tasks.filter(\.isOpen))
        await tasks.tidyUpIfDue(
            source: { conversations.source(of: $0)?.title }, quote: { conversations.quote(of: $0) },
            force: force
        )
    }

    /// Opens a conversation by id, fetching it when it is older than the loaded list.
    private func openConversation(_ id: String) {
        Task { if let conversation = await conversations.conversation(id: id) { onOpenConversation(conversation) } }
    }
}

/// Omi's live pill: where the audio comes from, the newest words, a running timer and stop.
/// Tapping it opens the full live transcript.
struct LiveBar: View {
    @Environment(CaptureStore.self) private var capture
    @State private var showsTranscript = false

    var body: some View {
        content
            .contentShape(Capsule())
            .onTapGesture { if capture.isLive { showsTranscript = true } }
            .accessibilityAddTraits(.isButton)
            .accessibilityIdentifier("live.bar")
            .sheet(isPresented: $showsTranscript) { LiveTranscriptSheet() }
            .animation(DS.Motion.standard, value: capture.phase)
    }

    @ViewBuilder
    private var content: some View {
        switch capture.phase {
        case .finishing:
            quiet {
                ProgressView().controlSize(.small).tint(DS.Palette.agent)
                Text(L("nativeSavingConversation")).font(DS.Typography.callout.weight(.medium))
            }
        case let .failed(reason):
            quiet {
                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(DS.Palette.warning)
                Text(LiveBar.message(reason)).font(DS.Typography.callout).lineLimit(2)
            }
        default:
            OmiLivePill(since: since, title: title, symbol: symbol) {
                if capture.isLive { stop }
            }
        }
    }

    private var since: Date? {
        if case let .live(since) = capture.phase, !capture.isPaused { since } else { nil }
    }

    /// The newest words (the iPhone previews them before the server confirms), else what is going on.
    private var title: String {
        if capture.isPaused { return L("paused") }
        if !capture.liveWords.isEmpty { return String(capture.liveWords.suffix(80)) }
        if capture.isBuffering { return L("nativeRecordingToPhone") }
        return "\(L("nativeListeningPhone")) · \(LiveBar.tag(capture.source))"
    }

    /// The pendant for an Omi; the phone and the watch get their symbol.
    private var symbol: String? {
        switch capture.source {
        case .device: nil
        case .watch: "applewatch"
        case .phone, nil: "iphone"
        }
    }

    private var stop: some View {
        Button {
            Task { await capture.stop() }
        } label: {
            Image(systemName: "stop.fill")
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(DS.Palette.ink)
                .frame(width: 32, height: 32)
                .background(DS.Palette.cardRaised, in: Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(L("nativeStopRecording"))
    }

    private func quiet(@ViewBuilder _ content: () -> some View) -> some View {
        HStack(spacing: DS.Spacing.sm) {
            content()
            Spacer(minLength: 0)
        }
        .padding(.horizontal, DS.Spacing.lg)
        .frame(minHeight: 48)
        .omiSurface(Capsule())
    }

    static func tag(_ source: CaptureStore.Source?) -> String {
        switch source {
        case .device: "Omi"
        case .watch: "Apple Watch"
        case .phone, nil: "iPhone"
        }
    }

    static func message(_ reason: String) -> String {
        switch reason {
        case "microphone": L("nativeMicPermissionNeeded")
        case "speech": L("nativeSpeechPermissionNeeded")
        case "speechUnavailable": L("nativeSpeechUnavailable")
        default: L("nativeCaptureFailed")
        }
    }
}
