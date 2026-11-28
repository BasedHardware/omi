import AgentFeature
import ConversationsFeature
import MemoryFeature
import OmiComponents
import OmiCore
import OmiDesign
import OmiDevice
import OmiPersistence
import OmiService
import SettingsFeature
import SwiftUI
import TasksFeature
import TodayFeature

/// The app shell in Omi's layout: device pill + round buttons, the big "Home  Chat  Memories"
/// switcher, and the bottom bar (Ask Omi + record) on Home and Memories. Tasks live on Home
/// (Needs you, All tasks one level down). The only place that imports feature modules.
struct MainTabView: View {
    enum Tab: String, Hashable, CaseIterable {
        case home, chat, memory

        init?(debugName: String?) {
            guard let debugName else { return nil }
            // Old names: Tasks moved onto Home (`-omiTab tasks` pushes All tasks, `DebugHooks`).
            self.init(rawValue: ["today", "conversations", "tasks"].contains(debugName) ? "home" : debugName)
        }

        var title: String {
            switch self {
            case .home: L("home")
            case .chat: L("nativeTabChat")
            case .memory: L("memories")
            }
        }
    }

    enum Route: Hashable {
        case conversation(Conversation)
        case recap(DailySummary)
        case search
        /// Every task (search, add, buckets, day view), from Home's "All tasks (n)".
        case allTasks
    }

    @Environment(AppEnvironment.self) var environment
    @Environment(DeepLinkRouter.self) var deepLinks
    @State var tab: Tab = .init(debugName: DebugLaunchOptions.current.initialTab) ?? .home
    @State var path = NavigationPath()
    @State var showsSettings = false
    /// The Settings section the sheet opens at (Account from a chat quota answer).
    @State var settingsTopic = DebugLaunchOptions.current.settingsTopic
    /// Set to go to the Chat tab (Ask Omi, a link, Siri); the shell switches and clears it.
    @State var showsAgent = DebugLaunchOptions.current.showsAgent
    // -omiDictate YES (with -omiShowAgent): the chat opens listening, as from the mic.
    @State var startsDictation = UserDefaults.standard.bool(forKey: "omiDictate")
    /// A new value rebuilds the Chat page with the latest dictation / draft request.
    @State var chatRequest: ChatScreen.Request?
    @State var handOverTask: ActionItem?
    /// A task card tapped on Home: its detail (text, due date, where it came from).
    @State var detailTask: ActionItem?
    @State var afterSettings = false
    @State var showsRecordWith = false
    @State var showsDevice = DebugLaunchOptions.current.showsDevice
    // Siri and quick actions: a question waiting in the chat's composer; the new-task form.
    @State var chatDraft = ""
    @State var showsNewTask = false
    /// Home's one-time "Ask Omi with Siri" row opens this.
    @State var showsSiriTip = false
    /// An app page from a link (`h.omi.me/apps/<id>`).
    @State var linkedApp: LinkedApp?

    var body: some View {
        presentingSheets(navigation)
            .task {
                environment.devices.start()
                environment.sync.start()
                // An Omi connected during onboarding starts capturing once the app opens.
                if environment.devices.connection == .connected, let codec = environment.devices.codec, !environment.capture.isLive {
                    await environment.capture.startDevice(codec: codec)
                }
            }
            .task { if environment.tasks.phase == .idle { await environment.tasks.load() } }
            .task {
                // -omiShowSettings: a sheet presented during the first root transition is dropped.
                guard DebugLaunchOptions.current.showsSettings else { return }
                try? await Task.sleep(for: .milliseconds(900))
                showsSettings = true
            }
            // Notification taps and omi:// links, including one that arrived before the shell was up.
            // Not `.task(id:)`: taking the link changes `pending`, which would cancel the load.
            .onChange(of: deepLinks.pending, initial: true) { _, link in if link != nil { Task { await openPendingLink() } } }
            .modifier(DebugHooks(path: $path, handOverTask: $handOverTask, showsAgent: $showsAgent))
            // What's new after an update, then pending announcements (one sheet at a time).
            .modifier(WhatsNewPresenter(appVersion: "\(environment.configuration.appVersion)+\(environment.configuration.appBuild)"))
            .modifier(OngoingCallPresenter()) // Phone calls: banner + call screen while a call runs outside Settings
            // A locked conversation's "Upgrade to Unlimited" opens Plan & usage.
            .environment(\.openUpgrade, OpenUpgradeAction { (settingsTopic, showsSettings) = ("planUsage", true) })
    }

    /// The pages, the Omi bar and every pushed screen.
    private var navigation: some View {
        NavigationStack(path: $path) {
            VStack(spacing: 0) {
                header
                switcher
                content
            }
            .background(AuroraBackground())
            // Over the pages, not beside them: lists scroll on under the bar and fade out there
            // instead of being cut off at its top edge (the pages pad their ends by its height).
            .overlay(alignment: .bottom) {
                // Chat has its own composer: the floating Ask Omi bar is for Home and Memories.
                if tab != .chat { bottomBar }
            }
            .animation(DS.Motion.standard, value: tab == .chat)
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(for: Route.self) { route in
                switch route {
                case let .conversation(conversation): detail(conversation)
                case let .recap(recap):
                    RecapScreen(recap: recap, onOpenConversation: { path.append(Route.conversation($0)) })
                case .allTasks:
                    TasksScreen(onHandOver: handOver)
                        .navigationTitle(L("tasks"))
                        .navigationBarTitleDisplayMode(.inline)
                        .background(DS.Palette.background)
                case .search:
                    SearchScreen(
                        store: SearchStore(
                            api: environment.api, conversations: environment.conversations,
                            tasks: environment.tasks, memories: environment.memories
                        ),
                        onOpenConversation: { path.append(Route.conversation($0)) },
                        onOpenRecap: { path.append(Route.recap($0)) }
                    )
                    .navigationTitle(L("search"))
                }
            }
            // At the root: a destination declared inside a pushed screen is unreliable.
            .navigationDestination(for: Conversation.self, destination: detail)
        }
        // Above every screen, clear of the Omi bar: a delete from the detail page is undone on Home.
        .overlay(alignment: .bottom) { UndoDeleteToast().padding(.bottom, DS.Size.omiBarHeight + DS.Spacing.lg) }
        // "Ask Omi" anywhere (the bar, a conversation, a link) goes to the Chat tab at the root.
        .onChange(of: showsAgent, initial: true) { _, shows in
            guard shows else { return }
            showsAgent = false
            openChat()
        }
    }

    /// Ask Omi + mic + record, floating over Home and Memories.
    private var bottomBar: some View {
        OmiBottomBar(
            onAsk: { openChat() },
            onDictate: {
                startsDictation = true
                openChat()
            },
            onRecordWith: { showsRecordWith = true }
        )
        .transition(.opacity)
        .background(alignment: .top) {
            // Content fades out under the bar instead of colliding with it, as in Omi.
            LinearGradient(
                stops: [
                    .init(color: DS.Palette.background.opacity(0), location: 0),
                    .init(color: DS.Palette.background.opacity(0.75), location: 0.35),
                    .init(color: DS.Palette.background, location: 0.62),
                ],
                startPoint: .top, endPoint: .bottom
            )
            // A long, soft fade that turns solid behind the bar, not above it.
            .padding(.top, -56)
            .ignoresSafeArea(edges: .bottom)
            .allowsHitTesting(false)
        }
    }

    /// The Chat tab, from the root (a pushed screen goes away first).
    func openChat() {
        // A dictation or a draft reaches the page once, as a request.
        if startsDictation {
            chatRequest = .dictate()
        } else if !chatDraft.isEmpty {
            chatRequest = .draft(chatDraft)
        }
        (startsDictation, chatDraft) = (false, "")
        path = NavigationPath()
        withAnimation(DS.Motion.snappy) { tab = .chat }
    }

    private var header: some View {
        HStack(spacing: DS.Spacing.sm) {
            Button { showsDevice = true } label: { DevicePill() }
                .buttonStyle(.plain)
                .accessibilityIdentifier("header.device")
            Spacer()
            // One header for every tab: on Chat its search looks through the thread, and the
            // chat's "…" (talk to, show only, clear) joins it; the chat has no bar of its own.
            if tab == .chat {
                CircleIconButton("magnifyingglass") { chatRequest = .search() }
                    .accessibilityLabel(L("nativeChatSearch"))
                    .accessibilityIdentifier("chat.search")
                ChatMenu { chatRequest = .filter($0) }
                    .transition(.opacity)
            } else {
                CircleIconButton("magnifyingglass") { path.append(Route.search) }
                    .accessibilityLabel(L("search"))
            }
            CircleIconButton("gearshape") {
                settingsTopic = nil
                showsSettings = true
            }
            .accessibilityLabel(L("settings"))
            .accessibilityIdentifier("header.settings")
        }
        .padding(.horizontal, DS.Spacing.gutter)
        .padding(.top, DS.Spacing.xs)
        .dynamicTypeSize(...DynamicTypeSize.accessibility1)
    }

    /// Omi's word tabs. Long words (German "Erinnerungen") first get a smaller size; at large
    /// text sizes the row scrolls sideways instead of breaking words. The words keep their size on
    /// every page, also while the chat's thread is scrolled.
    private var switcher: some View {
        ViewThatFits(in: .horizontal) {
            switcherRow(DS.Typography.switcher)
            switcherRow(.title2.weight(.bold))
            ScrollViewReader { proxy in
                ScrollView(.horizontal) { switcherRow(DS.Typography.switcher) }
                    .scrollIndicators(.hidden)
                    .onChange(of: tab) { _, item in withAnimation(DS.Motion.snappy) { proxy.scrollTo(item, anchor: .center) } }
            }
        }
        .dynamicTypeSize(...DynamicTypeSize.accessibility2)
        .padding(.top, DS.Spacing.xl)
        .padding(.bottom, DS.Spacing.lg)
    }

    private func switcherRow(_ font: Font) -> some View {
        HStack(spacing: DS.Spacing.lg) {
            ForEach(Tab.allCases, id: \.self) { item in
                Button {
                    withAnimation(DS.Motion.snappy) { tab = item }
                } label: {
                    Text(item.title)
                        .font(font)
                        .lineLimit(1)
                        .fixedSize()
                        .foregroundStyle(tab == item ? DS.Palette.ink : DS.Palette.inkTertiary)
                }
                .buttonStyle(.plain)
                .id(item)
                .accessibilityAddTraits(tab == item ? .isSelected : [])
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, DS.Spacing.gutter)
    }

    /// The three spaces as pages: tap a word above or swipe sideways.
    private var content: some View {
        TabView(selection: $tab) {
            TodayScreen(
                onOpenConversation: { path.append(Route.conversation($0)) },
                onHandOver: handOver,
                onOpenRun: openRun,
                onOpenDevice: { showsDevice = true },
                onOpenRecap: { path.append(Route.recap($0)) },
                onOpenSiriTip: { showsSiriTip = true },
                onOpenAllTasks: { path.append(Route.allTasks) },
                onOpenTask: { detailTask = $0 },
                onAskOmi: { text in
                    chatDraft = text
                    openChat()
                }
            )
            .safeAreaPadding(.bottom, OmiBottomBar.height)
            .tag(Tab.home)
            chatPage.tag(Tab.chat)
            MemoryScreen(onOpenConversation: { path.append(Route.conversation($0)) })
                .safeAreaPadding(.bottom, OmiBottomBar.height)
                .tag(Tab.memory)
        }
        .tabViewStyle(.page(indexDisplayMode: .never))
        .omiNoScrollEdgeEffect()
        .onChange(of: tab) { _, _ in DSHaptics.selection() }
    }

    /// The one thread with Omi, as a page.
    private var chatPage: some View {
        ChatScreen(
            mode: .tab, dictation: environment.dictation, request: chatRequest,
            onOpenConversation: { id in
                Task {
                    let destination = await DeepLinkRouter.destination(for: .conversation(id: id), in: environment)
                    guard case let .route(route) = destination else { return }
                    path.append(route)
                }
            },
            onUpgrade: { (settingsTopic, showsSettings) = ("planUsage", true) }
        )
    }

    private func detail(_ conversation: Conversation) -> some View {
        ConversationDetailScreen(
            store: ConversationDetailStore(preview: conversation, api: environment.api),
            onHandOver: handOver,
            onAskOmi: { showsAgent = true }
        )
    }
}
