import OmiComponents
import OmiCore
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// Settings hold configuration only, every topic exactly once (docs/STRUCTURE.md, "Settings tree"):
/// the profile on top, four live tiles (the Omi, the plan, apps, voices), then one flat list of the
/// other topics and "More" for the rare ones. Search sits behind the magnifier in the top bar.
public struct SettingsScreen: View {
    @Environment(SessionStore.self) private var session
    @Environment(SettingsStore.self) private var settings
    @Environment(DeveloperStore.self) private var developer
    @Environment(CapabilitiesStore.self) private var capabilities
    @Environment(AppleHealthStore.self) private var health
    @Environment(RemindersSyncStore.self) private var reminders
    @Environment(\.dismiss) private var dismiss
    /// Read by the app root (`OmiApp`); shown as the Appearance row's value.
    @AppStorage("flutter.appearanceMode") private var appearance = "dark"
    let appVersion: String
    /// Screens owned by other features, supplied by the app shell (features never import each other).
    let devicesScreen: AnyView
    /// Re-recording the voice profile (Onboarding's voice step), supplied by the shell.
    let voiceScreen: AnyView?
    /// Opens the chat (an app page's "Chat with…"; the chat already talks to that app).
    let onOpenChat: @MainActor () -> Void
    /// A person's conversation was tapped (Voices & people): the shell closes Settings and opens it.
    let onOpenConversation: ((Conversation) -> Void)?

    @State private var path: NavigationPath
    /// The magnifier in the top bar shows the search field; typing lists matching settings.
    @State private var isSearching = false
    @State private var searchText = ""

    /// `initialTopic` opens a screen directly (deep links, headless QA): a topic's raw value
    /// ("account", "listening"), a pushed screen ("referral", "planUsage", "browseApps"), or a
    /// "/"-separated stack ("listening/vocabulary", "browseApps/app:<id>", "voices/person:<id>").
    public init(
        appVersion: String, devicesScreen: AnyView, voiceScreen: AnyView? = nil, initialTopic: String? = nil,
        onOpenChat: @escaping @MainActor () -> Void = {},
        onOpenConversation: ((Conversation) -> Void)? = nil
    ) {
        self.appVersion = appVersion
        self.devicesScreen = devicesScreen
        self.voiceScreen = voiceScreen
        self.onOpenChat = onOpenChat
        self.onOpenConversation = onOpenConversation
        // "search:<text>" opens Settings with that search typed (headless QA of the search).
        if let initialTopic, initialTopic.hasPrefix("search:") {
            _path = State(initialValue: NavigationPath())
            _isSearching = State(initialValue: true)
            _searchText = State(initialValue: String(initialTopic.dropFirst(7)))
        } else {
            _path = State(initialValue: initialTopic.map(Self.path(for:)) ?? NavigationPath())
        }
    }

    public var body: some View {
        NavigationStack(path: $path) {
            ScrollViewReader { proxy in
                OmiFlatList {
                    if isSearching {
                        searchSections
                    } else {
                        hub
                        sections
                    }
                }
                .task { await debugScroll(proxy) }
            }
            .contentMargins(.top, DS.Spacing.xs, for: .scrollContent)
            .omiPage(L("settings"))
            .toolbar(removing: .title)
            .navigationDestination(for: SettingsTopic.self, destination: destination)
            .navigationDestination(for: OmiApp.self) { AppDetailScreen(appID: $0.id, preview: $0) }
            .navigationDestination(for: PersonLink.self) {
                PersonDetailScreen(personID: $0.id, onOpenConversation: onOpenConversation)
            }
            .environment(\.openChat, OpenChatAction(onOpenChat))
            .toolbar { toolbar }
            .task { await settings.loadSubscription() }
            .task { await settings.loadProfile() }
            .task { if settings.people.isEmpty { await settings.loadPeople() } }
            .task { await capabilities.load() }
            .task { await health.load() }
            .task { await reminders.refresh() }
        }
    }

    /// `-omiSettingsScroll bottom` (Debug): scrolls to the end of the list for screenshots.
    private func debugScroll(_ proxy: ScrollViewProxy) async {
        guard DebugLaunch.string("omiSettingsScroll") == "bottom" else { return }
        try? await Task.sleep(for: .seconds(1.5))
        proxy.scrollTo("settings.more", anchor: .bottom)
    }

    @ToolbarContentBuilder
    private var toolbar: some ToolbarContent {
        ToolbarItem(placement: .topBarLeading) {
            Button { dismiss() } label: { Image(systemName: "xmark") }
                .accessibilityLabel(L("close"))
        }
        if !isSearching {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    withAnimation(DS.Motion.gentle) { isSearching = true }
                } label: {
                    Image(systemName: "magnifyingglass")
                }
                .accessibilityLabel(L("nativeSearchSettings"))
                .accessibilityIdentifier("settings.searchButton")
            }
        }
    }

    /// The search field on top (focused), then what matches; picking one opens its screen.
    @ViewBuilder
    private var searchSections: some View {
        Section {
            SettingsSearchField(text: $searchText) {
                withAnimation(DS.Motion.gentle) {
                    searchText = ""
                    isSearching = false
                }
            }
            .plainSettingsRow()
        }
        if !searchText.trimmingCharacters(in: .whitespaces).isEmpty {
            Section {
                SettingsSearchResults(query: searchText) { topic in
                    searchText = ""
                    isSearching = false
                    path = Self.path(for: topic.rawValue)
                }
            }
        }
    }

    /// The profile and the four tiles, on the page itself.
    private var hub: some View {
        Section {
            SettingsProfileHeader(
                onOpenAccount: { path.append(SettingsTopic.account) },
                onUpgrade: { path = Self.path(for: SettingsTopic.planUsage.rawValue) }
            )
            .plainSettingsRow()
            SettingsHubTiles { topic in
                path = Self.path(for: topic.rawValue)
            }
            .plainSettingsRow()
        }
    }

    /// Everything else in one flat list; the rarely used ones under "More".
    @ViewBuilder
    private var sections: some View {
        Section {
            row(.listening)
            row(.memory)
            row(.assistant)
            row(.notifications)
            row(.privacy)
            row(.appearance, value: AppearanceScreen.title(appearance))
            row(.connectAI)
            row(.help)
        }
        Section {
            row(.phoneCalls)
            if developer.isDeveloperMode { row(.developer) }
        } header: {
            OmiSectionLabel(L("nativeSettingsMore"))
        } footer: {
            Text(verbatim: "Omi \(appVersion)")
                .frame(maxWidth: .infinity)
                .padding(.top, DS.Spacing.lg)
                .id("settings.more")
        }
    }

    /// The stack for an `initialTopic` (see `init`).
    static func path(for raw: String) -> NavigationPath {
        var path = NavigationPath()
        let parts = raw.split(separator: "/").map(String.init)
        guard let first = parts.first else { return path }
        for topic in SettingsTopic.path(for: first) {
            path.append(topic)
        }
        for part in parts.dropFirst() {
            if part.hasPrefix("app:") {
                let id = String(part.dropFirst(4))
                path.append(OmiApp(
                    id: id, name: "", description: "", author: nil, imageURL: nil, category: nil, rating: nil, installs: 0, isEnabled: false
                ))
            } else if part.hasPrefix("person:") {
                path.append(PersonLink(id: String(part.dropFirst(7))))
            } else if let topic = SettingsTopic(rawValue: part) {
                path.append(topic)
            }
        }
        return path
    }

    @ViewBuilder
    private func destination(_ topic: SettingsTopic) -> some View {
        switch topic {
        case .account: AccountScreen()
        case .planUsage: PlanUsageScreen()
        case .referral: ReferralScreen(store: settings.makeProfileStore())
        case .devices: devicesScreen
        case .listening: CaptureSettingsScreen()
        case .voices: PeopleScreen(voiceScreen: voiceScreen, onOpenConversation: onOpenConversation)
        case .memory: KnowledgeSummaryScreen()
        case .assistant: AssistantScreen()
        case .apps: CapabilitiesScreen()
        case .connectAI: ConnectAIScreen()
        case .browseApps: AppsBrowserScreen()
        case .phoneCalls: PhoneScreen()
        case .appearance: AppearanceScreen()
        case .notifications: NotificationsScreen()
        case .privacy: PrivacyScreen()
        case .help:
            HelpScreen {
                dismiss()
                session.replayIntroduction()
            }
        case .developer: DeveloperScreen()
        case .vocabulary: VocabularyScreen()
        case .listeningAdvanced: ListeningAdvancedScreen()
        case .voicePicker: VoicePickerScreen()
        case .importHistory: ImportScreen(store: settings.makeImportStore())
        case .whatsNew: WhatsNewScreen(store: settings.makeAnnouncementsStore())
        case .appleHealth: AppleHealthScreen()
        case .webhooks: WebhooksScreen()
        case .logs: DeveloperLogsScreen()
        }
    }

    private func row(_ topic: SettingsTopic, value: String? = nil) -> some View {
        NavigationLink(value: topic) {
            SettingsRowLabel(title: topic.title, systemImage: topic.systemImage, value: value)
        }
        .accessibilityIdentifier("settings.\(topic.rawValue)")
    }
}

enum SettingsTopic: String, Hashable, CaseIterable {
    case account, devices, listening, voices, memory, assistant, apps, connectAI, phoneCalls
    case appearance, notifications, privacy, help, developer
    /// Pushed screens a link or the search can open directly.
    case planUsage, referral, browseApps
    /// Deeper screens, reached through their parent ("listening/vocabulary").
    case vocabulary, listeningAdvanced, voicePicker, importHistory, whatsNew, appleHealth, webhooks, logs

    /// The stack that shows `raw`: a pushed screen opens on top of its parent. Earlier names
    /// ("capture", "capabilities", …) still work for old links and QA scripts.
    static func path(for raw: String) -> [SettingsTopic] {
        let aliases: [String: SettingsTopic] = [
            "capture": .listening, "voiceAndPeople": .voices, "memories": .memory, "capabilities": .apps,
            "notificationsAndDisplay": .notifications, "usage": .planUsage, "fairUse": .planUsage,
        ]
        guard let topic = SettingsTopic(rawValue: raw) ?? aliases[raw] else { return [] }
        switch topic {
        case .planUsage, .referral: return [.account, topic]
        case .browseApps: return [.apps, topic]
        case .vocabulary, .listeningAdvanced: return [.listening, topic]
        case .voicePicker: return [.assistant, topic]
        case .importHistory: return [.memory, topic]
        case .whatsNew: return [.help, topic]
        case .appleHealth: return [.apps, topic]
        case .webhooks, .logs: return [.developer, topic]
        default: return [topic]
        }
    }

    var title: String {
        switch self {
        case .account: L("account")
        case .devices: L("nativeSettingsMyOmi")
        case .listening: L("nativeSettingsListening")
        case .voices: L("nativeSettingsVoices")
        case .memory: L("nativeSettingsMemory")
        case .assistant: L("nativeAssistant")
        case .apps: L("nativeSettingsApps")
        case .connectAI: L("nativeConnectAI")
        case .phoneCalls: L("nativeSettingsPhoneCalls")
        case .appearance: L("appearance")
        case .notifications: L("notifications")
        case .privacy: L("nativeSettingsPrivacy")
        case .help: L("nativeSettingsHelp")
        case .developer: L("nativeDeveloper")
        case .planUsage: L("nativeSettingsPlanUsage")
        case .referral: L("nativeSettingsInviteFriends")
        case .browseApps: L("nativeBrowseApps")
        case .vocabulary: L("nativeSettingsVocabulary")
        case .listeningAdvanced: L("nativeSettingsAdvanced")
        case .voicePicker: L("nativeAssistantVoice")
        case .importHistory: L("nativeSettingsImportHistory")
        case .whatsNew: L("whatsNew")
        case .appleHealth: "Apple Health"
        case .webhooks: L("nativeDevWebhooks")
        case .logs: L("nativeDevLogs")
        }
    }

    var systemImage: String {
        switch self {
        case .account: "person.crop.circle"
        case .devices: "circle.circle"
        case .listening: "waveform"
        case .voices: "person.2"
        case .memory: "brain.head.profile"
        case .assistant: "sparkles"
        case .apps: "square.grid.2x2"
        case .connectAI: "link"
        case .phoneCalls: "phone"
        case .appearance: "circle.lefthalf.filled"
        case .notifications: "bell"
        case .privacy: "hand.raised"
        case .help: "questionmark.circle"
        case .developer: "chevron.left.forwardslash.chevron.right"
        case .planUsage: "chart.bar"
        case .referral: "gift"
        case .browseApps: "magnifyingglass"
        case .vocabulary: "text.book.closed"
        case .listeningAdvanced: "slider.horizontal.3"
        case .voicePicker: "person.wave.2"
        case .importHistory: "square.and.arrow.down"
        case .whatsNew: "gift"
        case .appleHealth: "heart"
        case .webhooks: "arrow.triangle.branch"
        case .logs: "list.bullet.rectangle"
        }
    }
}

/// A person's page in the Settings stack (Voices & people).
struct PersonLink: Hashable {
    let id: String
}

/// The search field the top bar's magnifier reveals: the quiet search capsule of Tasks and
/// Memories, focused at once, a clear button while typing and Cancel beside it.
private struct SettingsSearchField: View {
    @Binding var text: String
    let onCancel: () -> Void
    @FocusState private var focused: Bool

    var body: some View {
        HStack(spacing: DS.Spacing.md) {
            HStack(spacing: DS.Spacing.sm) {
                Image(systemName: "magnifyingglass").foregroundStyle(DS.Palette.inkSecondary)
                TextField(L("nativeSearchSettings"), text: $text)
                    .focused($focused)
                    .submitLabel(.search)
                    .autocorrectionDisabled()
                    .accessibilityIdentifier("settings.search")
                if !text.isEmpty {
                    Button { text = "" } label: {
                        Image(systemName: "xmark.circle.fill").foregroundStyle(DS.Palette.inkTertiary)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(L("close"))
                }
            }
            .font(DS.Typography.body)
            .padding(.horizontal, DS.Spacing.lg)
            .frame(minHeight: DS.Size.searchField)
            .omiSurface(Capsule())
            Button(L("cancel"), action: onCancel)
                .buttonStyle(.plain)
                .foregroundStyle(DS.Palette.ink)
                .accessibilityIdentifier("settings.search.cancel")
        }
        .padding(.top, DS.Spacing.sm)
        .onAppear { if text.isEmpty { focused = true } }
    }
}
