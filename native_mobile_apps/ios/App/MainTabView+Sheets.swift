import AgentFeature
import DeviceFeature
import OmiCore
import OmiDesign
import OmiPersistence
import OmiService
import OnboardingFeature
import SettingsFeature
import SwiftUI
import TasksFeature

/// The shell's sheets and the routing that opens them (links, chat follow-ups, Omi's runs).
extension MainTabView {
    func presentingSheets(_ content: some View) -> some View {
        content
            .sheet(isPresented: $showsSettings) {
                SettingsScreen(
                    appVersion: environment.configuration.appVersion,
                    devicesScreen: AnyView(DeviceScreen(tutorial: buttonTutorial)),
                    voiceScreen: AnyView(VoiceProfileScreen(
                        voice: environment.makeVoiceIntro(),
                        source: environment.devices.connection == .connected ? .device : .phone,
                        language: environment.preferences.string(.userPrimaryLanguage) ?? "en"
                    )),
                    initialTopic: settingsTopic,
                    onOpenChat: {
                        afterSettings = true
                        showsSettings = false
                    },
                    onOpenConversation: { showsSettings = false; path.append(Route.conversation($0)) }
                )
            }
            .onChange(of: showsSettings) { _, shown in
                // An app page's "Chat with…": the chat opens once Settings has closed.
                if !shown, afterSettings {
                    afterSettings = false
                    showsAgent = true
                }
            }
            .sheet(isPresented: $showsRecordWith) { RecordWithSheet() }
            .sheet(isPresented: $showsDevice) { deviceSheet }
            .sheet(isPresented: $showsNewTask) { NewTaskSheet() }
            .sheet(isPresented: $showsSiriTip) { SiriTipSheet() }
            .modifier(IntroductionPresenter(showsSettings: $showsSettings, settingsTopic: $settingsTopic))
            .sheet(item: $detailTask) { TaskDetailSheet(task: $0, onHandOver: handOver) }
            .sheet(item: $handOverTask) { task in
                HandOverSheet(task: task, conversationTitle: conversationTitle(for: task))
            }
            .sheet(item: $linkedApp) { AppLinkScreen(appID: $0.id) }
            .task(opensDebugSheets)
    }

    /// The Omi's page as a sheet from Home, with its own way out.
    private var deviceSheet: some View {
        NavigationStack {
            DeviceScreen(tutorial: buttonTutorial)
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) { Button(L("done")) { showsDevice = false } }
                }
        }
    }

    /// -omiShowRecordWith / -omiShowSiriTip / -omiShowNewTask: once the shell has settled.
    private func opensDebugSheets() async {
        let options = DebugLaunchOptions.current
        // -omiAllTasks YES (or the old -omiTab tasks) pushes the full task list from Home.
        if UserDefaults.standard.bool(forKey: "omiAllTasks") || options.initialTab == "tasks", path.isEmpty {
            path.append(Route.allTasks)
        }
        guard options.showsRecordWith || options.showsSiriTip || options.showsNewTask else { return }
        try? await Task.sleep(for: .milliseconds(900))
        (showsRecordWith, showsSiriTip, showsNewTask) = (options.showsRecordWith, options.showsSiriTip, options.showsNewTask)
    }

    /// My Devices › How to use your Omi: the onboarding button lessons, reopened.
    var buttonTutorial: AnyView {
        AnyView(OmiButtonTutorialScreen(tutorial: environment.buttonTutorial).environment(environment.voice))
    }

    func handOver(_ task: ActionItem) {
        handOverTask = task
    }

    func openPendingLink() async {
        guard let link = deepLinks.take() else { return }
        let destination = await DeepLinkRouter.destination(for: link, in: environment)
        showsSettings = false
        showsDevice = false
        showsAgent = false
        handOverTask = nil
        detailTask = nil
        showsNewTask = false
        linkedApp = nil
        showsSiriTip = false
        path = NavigationPath()
        switch destination {
        case let .route(route):
            tab = .home
            path.append(route)
        case let .tab(target): tab = target
        case let .handOver(task): handOverTask = task
        case let .task(task): detailTask = task
        case .chat: showsAgent = true
        case .device: showsDevice = true
        case let .chatDraft(text): (chatDraft, showsAgent) = (text, true)
        case .newTask: (tab, showsNewTask) = (.home, true)
        case .record: if !environment.capture.isLive { await environment.capture.startPhone() }
        case .account: (settingsTopic, showsSettings) = ("account", true)
        case let .app(id): linkedApp = LinkedApp(id: id)
        }
    }

    func openRun(_ taskID: String) {
        handOverTask = environment.tasks.tasks.first { $0.id == taskID }
    }

    func conversationTitle(for task: ActionItem) -> String? {
        task.conversationID.flatMap { id in environment.conversations.conversations.first { $0.id == id }?.title }
    }
}

/// The app introduction replayed from Help, over Home; and the Settings section it (or the one at
/// the end of onboarding) asked to open ("Choose how often").
struct IntroductionPresenter: ViewModifier {
    @Environment(SessionStore.self) private var session
    @Binding var showsSettings: Bool
    @Binding var settingsTopic: String?

    func body(content: Content) -> some View {
        content
            .fullScreenCover(isPresented: Binding(get: { session.showsIntroduction }, set: { if !$0 { session.introductionFinished() } })) {
                IntroTourScreen { topic in
                    session.settingsAfterIntroduction = topic
                    session.introductionFinished()
                }
            }
            .onChange(of: session.showsIntroduction, initial: true) { _, _ in openRequestedSettings() }
            .onChange(of: session.settingsAfterIntroduction) { _, _ in openRequestedSettings() }
            .task {
                #if DEBUG
                    // -omiShowIntroduction YES: Help › Replay introduction, headless.
                    guard UserDefaults.standard.bool(forKey: "omiShowIntroduction") else { return }
                    try? await Task.sleep(for: .milliseconds(900))
                    session.replayIntroduction()
                #endif
            }
    }

    private func openRequestedSettings() {
        guard !session.showsIntroduction, let topic = session.settingsAfterIntroduction else { return }
        session.settingsAfterIntroduction = nil
        Task {
            // After the cover (or the onboarding cross-fade) is gone; a sheet presented during it is dropped.
            try? await Task.sleep(for: .milliseconds(700))
            settingsTopic = topic
            showsSettings = true
        }
    }
}
