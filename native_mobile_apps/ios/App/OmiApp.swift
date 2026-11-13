import CoreSpotlight
import FirebaseCore
import GoogleSignIn
import OmiCore
import OmiDesign
import OmiService
import SettingsFeature
import SwiftUI

@main
struct OmiApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var environment: AppEnvironment
    @State private var deepLinks: DeepLinkRouter
    @State private var push: PushNotifications
    /// Live Activities and widgets, fed from the stores.
    @State private var extras: ExtrasBridge
    /// Spotlight items and the Home Screen quick actions.
    @State private var system: SystemIntegration
    /// Same key and values as Flutter's `AppearanceProvider` ("light", "dark", "system"). Unset means
    /// dark, the look Omi is known for.
    @AppStorage("flutter.appearanceMode") private var appearanceMode = "dark"
    @Environment(\.scenePhase) private var scenePhase

    init() {
        FirebaseApp.configure()
        let environment = AppEnvironment.live()
        let deepLinks = DeepLinkRouter()
        _environment = State(initialValue: environment)
        _deepLinks = State(initialValue: deepLinks)
        _push = State(initialValue: PushNotifications(api: environment.api, router: deepLinks))
        _extras = State(initialValue: ExtrasBridge(environment: environment))
        #if DEBUG
            // Layout check: the Live Activity's views as PNGs (LiveActivityRenderer).
            if UserDefaults.standard.bool(forKey: "omiRenderLiveActivity") { LiveActivityRenderer.renderAll() }
        #endif
        // --- Siri, Shortcuts, Spotlight, quick actions (begin) ---
        AppIntentsBridge.environment = environment
        AppIntentsBridge.router = deepLinks
        _system = State(initialValue: SystemIntegration(environment: environment))
        // --- Siri, Shortcuts, Spotlight, quick actions (end) ---
        // Background refresh and processing: registered before launch finishes, as iOS requires.
        BackgroundTasks.register(environment.makeBackgroundWork())
        SupportChat.configure()
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(environment)
                .environment(environment.session)
                .environment(environment.conversations)
                .environment(environment.tasks)
                .environment(environment.goals)
                .environment(environment.reminders)
                .environment(environment.memories)
                .environment(environment.chat)
                .environment(environment.voice)
                .environment(environment.agent)
                .environment(environment.capture)
                .environment(environment.devices)
                .environment(environment.diagnosticsReport)
                .environment(environment.firmware)
                .environment(environment.sync)
                .environment(environment.capabilities)
                .environment(environment.settings)
                .environment(environment.voices)
                .environment(environment.developer)
                .environment(environment.log)
                .environment(environment.catalog)
                .environment(environment.taskApps)
                // --- Phone calls ---
                .environment(environment.phoneCalls)
                // --- /Phone calls ---
                // --- Location, Apple Health, naming voices live ---
                .environment(environment.location)
                .environment(environment.health)
                .environment(environment.liveSpeakers)
                .environment(environment.customSTT)
                .environment(deepLinks)
                // Help and feedback offer the support chat only when Intercom is configured.
                .environment(\.supportChat, SupportChat.isConfigured ? SupportChatAction { SupportChat.present() } : nil)
                .preferredColorScheme(colorScheme)
                .onOpenURL { url in
                    // Google's callback first; everything else may be an omi:// or an h.omi.me (universal) link.
                    if !GIDSignIn.sharedInstance.handle(url) { deepLinks.open(DeepLink(url: url) ?? DeepLink(universalLink: url)) }
                }
                // A tap on an Omi item in Spotlight: the item's identifier is its omi:// link.
                .onContinueUserActivity(CSSearchableItemActionType) { activity in
                    let identifier = activity.userInfo?[CSSearchableItemActivityIdentifier] as? String
                    deepLinks.open(identifier.flatMap(URL.init(string:)).flatMap(DeepLink.init(url:)))
                }
                .onChange(of: environment.session.phase, initial: true) { _, phase in
                    push.sessionChanged(phase)
                    SupportChat.sessionChanged(phase)
                }
                // Apple Reminders sync on every return to the app (30 s apart), as Flutter does.
                .onChange(of: scenePhase) { _, phase in
                    if phase == .background { BackgroundTasks.schedule(pendingRecordings: environment.sync.hasPending) }
                    guard phase == .active, case .ready = environment.session.phase else { return }
                    Task {
                        await environment.reminders.refresh()
                        await environment.reminders.syncIfDue()
                    }
                    // Fresh health numbers for the chat while connected (hourly at most).
                    Task { await environment.health.syncIfConnected() }
                }
        }
    }

    private var colorScheme: ColorScheme? {
        switch appearanceMode {
        case "light": .light
        case "system": nil
        default: .dark
        }
    }
}
