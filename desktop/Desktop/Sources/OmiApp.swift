import SwiftUI
import FirebaseCore
import FirebaseAuth
import Mixpanel
import Sentry
import Sparkle

// MARK: - Launch Mode
/// Determines which UI to show based on command-line arguments
enum LaunchMode: String {
    case full = "full"       // Normal app with full sidebar
    case rewind = "rewind"   // Rewind-only mode (no sidebar)

    static func fromCommandLine() -> LaunchMode {
        // Check for --mode=rewind argument
        for arg in CommandLine.arguments {
            if arg == "--mode=rewind" {
                NSLog("OMI LaunchMode: Detected rewind mode from command line")
                return .rewind
            }
        }
        return .full
    }
}

// MARK: - Dev Flags
/// Check for --skip-onboarding flag to bypass onboarding during development
func shouldSkipOnboarding() -> Bool {
    return CommandLine.arguments.contains("--skip-onboarding")
}

// Simple observable state without Firebase types
@MainActor
class AuthState: ObservableObject {
    static let shared = AuthState()

    // UserDefaults keys (must match AuthService)
    private static let kAuthIsSignedIn = "auth_isSignedIn"
    private static let kAuthUserEmail = "auth_userEmail"
    private static let kAuthUserId = "auth_userId"

    @Published var isSignedIn: Bool
    @Published var isLoading: Bool = false
    @Published var isRestoringAuth: Bool = true
    @Published var error: String?
    @Published var userEmail: String?

    private init() {
        // Restore auth state from UserDefaults immediately on init (before UI renders)
        let savedSignedIn = UserDefaults.standard.bool(forKey: Self.kAuthIsSignedIn)
        let savedEmail = UserDefaults.standard.string(forKey: Self.kAuthUserEmail)
        self.isSignedIn = savedSignedIn
        self.userEmail = savedEmail
        // Show loading splash while Firebase restores session (only if user was previously signed in)
        self.isRestoringAuth = savedSignedIn
        NSLog("OMI AuthState: Initialized with savedSignedIn=%@, email=%@, isRestoringAuth=%@",
              savedSignedIn ? "true" : "false", savedEmail ?? "nil", self.isRestoringAuth ? "true" : "false")
    }

    func update(isSignedIn: Bool, userEmail: String? = nil) {
        self.isSignedIn = isSignedIn
        self.userEmail = userEmail
    }

    /// Get the user's Firebase UID from UserDefaults (fallback when Firebase SDK auth fails)
    var userId: String? {
        UserDefaults.standard.string(forKey: Self.kAuthUserId)
    }
}

@main
struct OMIApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var appState = AppState()
    @StateObject private var authState = AuthState.shared
    @Environment(\.openWindow) private var openWindow

    /// Launch mode determined at startup from command-line arguments
    static let launchMode = LaunchMode.fromCommandLine()

    /// Window title with version number (different for rewind mode)
    private var windowTitle: String {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? ""
        let displayName = Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "Omi"
        let baseName = Self.launchMode == .rewind ? "Omi Rewind" : displayName
        return version.isEmpty ? baseName : "\(baseName) v\(version)"
    }

    /// Window size based on launch mode
    private var defaultWindowSize: CGSize {
        Self.launchMode == .rewind ? CGSize(width: 1000, height: 700) : CGSize(width: 1200, height: 800)
    }

    var body: some Scene {
        // Main desktop window - same view for both modes, sidebar hidden in rewind mode
        Window(windowTitle, id: "main") {
            DesktopHomeView()
                .withFontScaling()
                .onAppear {
                    log("OmiApp: Main window content appeared (mode: \(Self.launchMode.rawValue))")
                }
        }
        .windowStyle(.titleBar)
        .defaultSize(width: defaultWindowSize.width, height: defaultWindowSize.height)
        .commands {
            CommandGroup(after: .textFormatting) {
                Button("Increase Font Size") {
                    let s = FontScaleSettings.shared
                    s.scale = min(2.0, round((s.scale + 0.05) * 20) / 20)
                }
                .keyboardShortcut("+", modifiers: .command)

                Button("Decrease Font Size") {
                    let s = FontScaleSettings.shared
                    s.scale = max(0.5, round((s.scale - 0.05) * 20) / 20)
                }
                .keyboardShortcut("-", modifiers: .command)

                Button("Reset Font Size") {
                    FontScaleSettings.shared.resetToDefault()
                }
                .keyboardShortcut("0", modifiers: .command)

                Divider()

                Button("Reset Window Size") {
                    resetWindowToDefaultSize()
                }
            }
        }

        // Note: Menu bar is now handled by NSStatusBar in AppDelegate.setupMenuBar()
        // for better reliability on macOS Sequoia (SwiftUI MenuBarExtra had rendering issues)
    }
}

class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    private var sentryHeartbeatTimer: Timer?
    private var globalHotkeyMonitor: Any?
    private var localHotkeyMonitor: Any?
    private var windowObservers: [NSObjectProtocol] = []
    private var statusBarItem: NSStatusItem?
    private var toggleBarObserver: NSObjectProtocol?

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Ignore SIGPIPE so broken-pipe writes return errors instead of crashing the app.
        // Without this, writing to a dead FFmpeg stdin or agent-bridge pipe kills the process.
        signal(SIGPIPE, SIG_IGN)

        log("AppDelegate: applicationDidFinishLaunching started (mode: \(OMIApp.launchMode.rawValue))")
        log("AppDelegate: AuthState.isSignedIn=\(AuthState.shared.isSignedIn)")

        // Force macOS to use the correct app icon (bypasses icon cache)
        if let iconURL = Bundle.main.url(forResource: "OmiIcon", withExtension: "icns"),
           let icon = NSImage(contentsOf: iconURL) {
            NSApp.applicationIconImage = icon
            // Also update the on-disk registration
            let appURL = Bundle.main.bundleURL
            NSWorkspace.shared.setIcon(icon, forFile: appURL.path, options: [])
            if let cfURL = appURL as CFURL? {
                LSRegisterURL(cfURL, true)
            }
            log("AppDelegate: Set application icon from OmiIcon.icns")
        }

        // Initialize NotificationService early to set up UNUserNotificationCenterDelegate
        // This ensures notifications display properly when app is in foreground
        _ = NotificationService.shared

        // Initialize Sparkle auto-updater early so the 10-minute check timer starts at launch
        // Without this, the updater only starts when the user opens Settings or clicks "Check for Updates"
        _ = UpdaterViewModel.shared

        // Initialize Sentry for crash reporting and error tracking (including dev builds)
        let isDev = AnalyticsManager.isDevBuild
        SentrySDK.start { options in
            options.dsn = "https://8f700584deda57b26041ff015539c8c1@o4507617161314304.ingest.us.sentry.io/4510790686277632"
            options.debug = false
            options.enableAutoSessionTracking = true
            options.environment = isDev ? "development" : "production"
            // Disable automatic HTTP client error capture — the SDK creates noisy events
            // for every 4xx/5xx response (e.g. Cloud Run 503 cold starts on /v1/crisp/unread).
            // App code already handles HTTP errors and reports meaningful ones explicitly.
            options.enableCaptureFailedRequests = false
            options.maxBreadcrumbs = 100
            options.beforeSend = { event in
                // Filter out HTTP errors targeting the dev tunnel — noise when the tunnel is down
                if let urlTag = event.tags?["url"], urlTag.contains("m13v.com") {
                    return nil
                }
                // Filter out NSURLErrorCancelled (-999) — these are intentional cancellations
                // (e.g. proactive assistants cancelling in-flight Gemini requests on context switch)
                if let exceptions = event.exceptions, exceptions.contains(where: { exc in
                    exc.type == "NSURLErrorDomain" && exc.value.contains("Code=-999") ||
                    exc.type == "NSURLErrorDomain" && exc.value.contains("Code: -999")
                }) {
                    return nil
                }
                return event
            }
        }
        log("Sentry initialized (environment: \(isDev ? "development" : "production"))")

        // Initialize Firebase
        let plistPath = Bundle.main.path(forResource: "GoogleService-Info", ofType: "plist")

        if let path = plistPath,
           let options = FirebaseOptions(contentsOfFile: path) {
            FirebaseApp.configure(options: options)
            AuthService.shared.configure()
        }

        // Initialize analytics (MixPanel + PostHog)
        AnalyticsManager.shared.initialize()
        AnalyticsManager.shared.appLaunched()
        AnalyticsManager.shared.trackDisplayInfo()

        // Tier gating: migrate old boolean key to new 6-tier system
        TierManager.migrateExistingUsersIfNeeded()

        // All users get all features (tier 0 = show all)
        // Note: hasLaunchedBefore is also set by trackFirstLaunchIfNeeded(), but that
        // skips dev builds. Set it here too so tier doesn't reset on every dev launch.
        if !UserDefaults.standard.bool(forKey: "hasLaunchedBefore") {
            UserDefaults.standard.set(true, forKey: "hasLaunchedBefore")
            UserDefaults.standard.set(0, forKey: "currentTierLevel")
            UserDefaults.standard.set(0, forKey: "lastSeenTierLevel")
            UserDefaults.standard.set(true, forKey: "userShowAllFeatures")
        }

        AnalyticsManager.shared.trackFirstLaunchIfNeeded()

        // Set per-user database path before any async tasks can trigger DB initialization.
        // This is synchronous and must happen before TierManager / TranscriptionRetryService.
        let userId = UserDefaults.standard.string(forKey: "auth_userId")
        RewindDatabase.currentUserId = (userId?.isEmpty == false) ? userId : "anonymous"

        // Start resource monitoring (memory, CPU, disk)
        ResourceMonitor.shared.start()

        // Recover any pending/failed transcription sessions from previous runs
        Task {
            await TranscriptionRetryService.shared.recoverPendingTranscriptions()
            TranscriptionRetryService.shared.start()
        }

        // Identify user if already signed in
        if AuthState.shared.isSignedIn {
            AnalyticsManager.shared.identify()
            // Set Sentry user context (now enabled for dev builds too)
            if let email = AuthState.shared.userEmail {
                let sentryUser = Sentry.User()
                sentryUser.email = email
                sentryUser.username = AuthService.shared.displayName.isEmpty ? nil : AuthService.shared.displayName
                SentrySDK.setUser(sentryUser)
            }
            // Fetch conversations on startup
            AuthService.shared.fetchConversations()

            // Check tier eligibility (at most once per day)
            Task {
                await TierManager.shared.checkTierIfNeeded()
            }

            // Report comprehensive settings state (at most once per day)
            AnalyticsManager.shared.reportAllSettingsIfNeeded()

            // File indexing now runs through FileIndexingView UI (user consent required)
            // No background scan — prevents race condition where scan finishes before UI listens
        }

        // One-time migration: Enable launch at login for existing users who haven't set it
        migrateLaunchAtLoginDefault()

        // One-time migration: Rename app bundle from "Omi Computer.app" to "Omi Beta.app"
        migrateAppNameToBeta()

        // Track launch at login status once per app launch
        Task { @MainActor in
            let isEnabled = LaunchAtLoginManager.shared.isEnabled
            AnalyticsManager.shared.launchAtLoginStatusChecked(enabled: isEnabled)
        }

        // Register for Apple Events to handle URL scheme
        NSAppleEventManager.shared().setEventHandler(
            self,
            andSelector: #selector(handleGetURLEvent(_:withReplyEvent:)),
            forEventClass: AEEventClass(kInternetEventClass),
            andEventID: AEEventID(kAEGetURL)
        )

        // Register global hotkey for Rewind (Cmd+Shift+Space)
        setupGlobalHotkeys()

        // Register Carbon-based global shortcuts for floating control bar (Cmd+\)
        GlobalShortcutManager.shared.registerShortcuts()
        toggleBarObserver = NotificationCenter.default.addObserver(
            forName: GlobalShortcutManager.toggleFloatingBarNotification,
            object: nil,
            queue: .main
        ) { _ in
            Task { @MainActor in
                FloatingControlBarManager.shared.toggle()
            }
        }

        // Set up dock icon visibility based on window state
        setupDockIconObservers()

        // Set up menu bar icon with NSStatusBar (more reliable than SwiftUI MenuBarExtra)
        // Called synchronously on main thread to ensure status item is created before app finishes launching
        Task { @MainActor in
            self.setupMenuBar()
        }

        // Start Sentry heartbeat timer (every 5 minutes) to capture breadcrumbs periodically
        startSentryHeartbeat()

        // Activate app and show main window after a brief delay
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
            log("AppDelegate: Checking windows after 0.2s delay, count=\(NSApp.windows.count)")
            NSApp.activate(ignoringOtherApps: true)
            var foundOmiWindow = false
            for window in NSApp.windows {
                log("AppDelegate: Window title='\(window.title)', isVisible=\(window.isVisible)")
                if window.title.hasPrefix("Omi") {
                    foundOmiWindow = true
                    window.makeKeyAndOrderFront(nil)
                    window.appearance = NSAppearance(named: .darkAqua)
                    // Ensure fullscreen always creates a dedicated Space
                    window.collectionBehavior.insert(.fullScreenPrimary)
                    // Show dock icon when main window is visible
                    NSApp.setActivationPolicy(.regular)
                    log("AppDelegate: Dock icon shown on launch")
                }
            }
            if !foundOmiWindow {
                log("AppDelegate: WARNING - 'Omi' window not found!")
            }
        }

        log("AppDelegate: applicationDidFinishLaunching completed")
    }

    /// Start a timer that sends Sentry session snapshots every 5 minutes
    /// This ensures we have breadcrumbs captured even without errors
    private func startSentryHeartbeat() {
        // Now runs in dev builds too since Sentry is always initialized
        sentryHeartbeatTimer = Timer.scheduledTimer(withTimeInterval: 300, repeats: true) { _ in
            // Capture a session heartbeat event with current breadcrumbs
            SentrySDK.capture(message: "Session Heartbeat") { scope in
                scope.setLevel(.info)
                scope.setTag(value: "heartbeat", key: "event_type")
            }
            log("Sentry: Session heartbeat captured")
        }
    }

    /// Set up global keyboard shortcuts
    private func setupGlobalHotkeys() {
        // Handler for Ctrl+Option+R -> Open Rewind
        let hotkeyHandler: (NSEvent) -> NSEvent? = { event in
            let modifiers = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
            let keyCode = event.keyCode

            // Log modifier key presses for debugging
            if modifiers.contains(.control) || modifiers.contains(.option) {
                log("AppDelegate: [HOTKEY] keyCode=\(keyCode), modifiers=\(modifiers.rawValue) (ctrl=\(modifiers.contains(.control)), opt=\(modifiers.contains(.option)))")
            }

            // Check for Ctrl+Option+R (less likely to conflict with system shortcuts)
            let isCtrlOption = modifiers.contains(.control) && modifiers.contains(.option)
            let isR = keyCode == 15 // R key

            if isCtrlOption && isR {
                log("AppDelegate: [HOTKEY] Rewind hotkey MATCHED (Ctrl+Option+R)")
                DispatchQueue.main.async {
                    log("AppDelegate: [HOTKEY] Activating app and posting notification")
                    // Bring app to front
                    NSApp.activate(ignoringOtherApps: true)
                    // Find and show main window
                    for window in NSApp.windows {
                        if window.title.hasPrefix("Omi") {
                            window.makeKeyAndOrderFront(nil)
                            break
                        }
                    }
                    // Post notification to navigate to Rewind
                    NotificationCenter.default.post(name: .navigateToRewind, object: nil)
                    log("AppDelegate: [HOTKEY] Posted navigateToRewind notification")
                }
            }
            return event
        }

        // Ask Omi shortcut is registered via Carbon RegisterEventHotKey in
        // GlobalShortcutManager (works regardless of accessibility permission state).

        // Global monitor - for when OTHER apps are focused (Ctrl+Option+R only)
        globalHotkeyMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { event in
            _ = hotkeyHandler(event)
        }

        // Local monitor - for when THIS app is focused (Ctrl+Option+R only)
        localHotkeyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            return hotkeyHandler(event)
        }

        log("AppDelegate: Hotkey monitors registered - global=\(globalHotkeyMonitor != nil), local=\(localHotkeyMonitor != nil)")
        log("AppDelegate: Hotkey is Ctrl+Option+R (⌃⌥R), Ask Omi + Cmd+\\ via Carbon hotkeys")
    }

    /// Set up observers to show/hide dock icon when main window appears/disappears
    private func setupDockIconObservers() {
        // Show dock icon when a window becomes visible
        let showObserver = NotificationCenter.default.addObserver(
            forName: NSWindow.didBecomeKeyNotification,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let window = notification.object as? NSWindow,
                  window.title.hasPrefix("Omi") else { return }
            self?.showDockIcon()
        }
        windowObservers.append(showObserver)

        // Hide dock icon when window closes (check if any Omi windows remain)
        let closeObserver = NotificationCenter.default.addObserver(
            forName: NSWindow.willCloseNotification,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let window = notification.object as? NSWindow,
                  window.title.hasPrefix("Omi") else { return }
            // Delay check to allow window to fully close
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                self?.checkAndHideDockIconIfNeeded()
            }
        }
        windowObservers.append(closeObserver)

        // Also hide dock icon when window is minimized
        let minimizeObserver = NotificationCenter.default.addObserver(
            forName: NSWindow.didMiniaturizeNotification,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let window = notification.object as? NSWindow,
                  window.title.hasPrefix("Omi") else { return }
            self?.checkAndHideDockIconIfNeeded()
        }
        windowObservers.append(minimizeObserver)

        // Show dock icon when window is restored from minimize
        let deminiaturizeObserver = NotificationCenter.default.addObserver(
            forName: NSWindow.didDeminiaturizeNotification,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let window = notification.object as? NSWindow,
                  window.title.hasPrefix("Omi") else { return }
            self?.showDockIcon()
        }
        windowObservers.append(deminiaturizeObserver)

        log("AppDelegate: Dock icon observers set up")
    }

    /// Show the app icon in the Dock
    private func showDockIcon() {
        if NSApp.activationPolicy() != .regular {
            NSApp.setActivationPolicy(.regular)
            log("AppDelegate: Dock icon shown")
        }
    }

    /// Hide the app icon from the Dock (if no Omi windows are visible)
    private func checkAndHideDockIconIfNeeded() {
        // Check if any Omi windows are still visible (not minimized, not closed)
        let hasVisibleOmiWindow = NSApp.windows.contains { window in
            window.title.hasPrefix("Omi") && window.isVisible && !window.isMiniaturized
        }

        if !hasVisibleOmiWindow && NSApp.activationPolicy() != .accessory {
            NSApp.setActivationPolicy(.accessory)
            log("AppDelegate: Dock icon hidden (no visible Omi windows)")
            // Workaround for macOS Sequoia bug: switching to .accessory can cause
            // NSStatusBar items to disappear. Force-refresh the status bar item.
            refreshMenuBarIcon()
        }
    }

    /// Force-refresh the menu bar icon after activation policy changes.
    /// Works around a macOS Sequoia bug where NSStatusBar items vanish
    /// when switching to .accessory activation policy.
    private func refreshMenuBarIcon() {
        guard let statusBarItem = statusBarItem else { return }
        statusBarItem.isVisible = false
        DispatchQueue.main.async {
            statusBarItem.isVisible = true
            log("AppDelegate: [MENUBAR] Refreshed status bar item after policy change")
        }
    }

    /// Set up menu bar icon using NSStatusBar (more reliable than SwiftUI MenuBarExtra)
    @MainActor private func setupMenuBar() {
        log("AppDelegate: [MENUBAR] Setting up NSStatusBar menu (macOS \(ProcessInfo.processInfo.operatingSystemVersionString))")
        log("AppDelegate: [MENUBAR] Thread: \(Thread.isMainThread ? "main" : "background"), statusBar items: \(NSStatusBar.system.thickness)")

        statusBarItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)

        guard let statusBarItem = statusBarItem else {
            log("AppDelegate: [MENUBAR] ERROR - Failed to create status bar item")
            SentrySDK.capture(message: "Failed to create NSStatusItem") { scope in
                scope.setLevel(.error)
                scope.setTag(value: "menu_bar", key: "component")
            }
            return
        }

        log("AppDelegate: [MENUBAR] NSStatusItem created successfully")

        let displayName = Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "Omi"

        // Set up the button with icon
        if let button = statusBarItem.button {
            if OMIApp.launchMode == .rewind {
                // Rewind mode uses SF Symbol
                if let icon = NSImage(systemSymbolName: "clock.arrow.circlepath", accessibilityDescription: "Omi Rewind") {
                    icon.isTemplate = true
                    button.image = icon
                    log("AppDelegate: [MENUBAR] Rewind icon set successfully")
                }
            } else if let iconURL = Bundle.resourceBundle.url(forResource: "app_launcher_icon", withExtension: "png"),
                      let icon = NSImage(contentsOf: iconURL) {
                icon.isTemplate = true
                icon.size = NSSize(width: 18, height: 18)
                button.image = icon
                log("AppDelegate: [MENUBAR] Custom app_launcher_icon set successfully")
            } else {
                // Fallback to SF Symbol
                if let icon = NSImage(systemSymbolName: "waveform.circle.fill", accessibilityDescription: "Omi") {
                    icon.isTemplate = true
                    button.image = icon
                }
                log("AppDelegate: [MENUBAR] WARNING - Failed to load app_launcher_icon, using fallback")
            }
            button.toolTip = OMIApp.launchMode == .rewind ? "Omi Rewind" : displayName
        } else {
            log("AppDelegate: [MENUBAR] WARNING - statusBarItem.button is nil")
        }

        // Create menu
        let menu = NSMenu()

        // Open app item
        let openItem = NSMenuItem(title: "Open \(displayName)", action: #selector(openOmiFromMenu), keyEquivalent: "o")
        openItem.target = self
        menu.addItem(openItem)

        menu.addItem(NSMenuItem.separator())

        // Check for Updates
        let updatesItem = NSMenuItem(title: "Check for Updates...", action: #selector(checkForUpdates), keyEquivalent: "")
        updatesItem.target = self
        menu.addItem(updatesItem)

        menu.addItem(NSMenuItem.separator())

        // Sign out / User info
        if AuthState.shared.isSignedIn {
            if let email = AuthState.shared.userEmail {
                let emailItem = NSMenuItem(title: "Signed in as \(email)", action: nil, keyEquivalent: "")
                emailItem.isEnabled = false
                menu.addItem(emailItem)
                menu.addItem(NSMenuItem.separator())
            }

            let resetItem = NSMenuItem(title: "Reset Onboarding...", action: #selector(resetOnboarding), keyEquivalent: "")
            resetItem.target = self
            menu.addItem(resetItem)

            menu.addItem(NSMenuItem.separator())

            let reportItem = NSMenuItem(title: "Report Issue...", action: #selector(reportIssue), keyEquivalent: "")
            reportItem.target = self
            menu.addItem(reportItem)

            menu.addItem(NSMenuItem.separator())

            let signOutItem = NSMenuItem(title: "Sign Out", action: #selector(signOut), keyEquivalent: "")
            signOutItem.target = self
            menu.addItem(signOutItem)
        } else {
            let notSignedInItem = NSMenuItem(title: "Not signed in", action: nil, keyEquivalent: "")
            notSignedInItem.isEnabled = false
            menu.addItem(notSignedInItem)
        }

        menu.addItem(NSMenuItem.separator())

        // Quit item
        let quitItem = NSMenuItem(title: "Quit", action: #selector(quitApp), keyEquivalent: "q")
        quitItem.target = self
        menu.addItem(quitItem)

        statusBarItem.menu = menu
        menu.delegate = self
        log("AppDelegate: [MENUBAR] Menu bar setup completed - icon visible in status bar")

        // Verify the status item is valid
        if let button = statusBarItem.button {
            log("AppDelegate: [MENUBAR] VERIFY - button exists, frame: \(button.frame), isHidden: \(button.isHidden)")
        } else {
            log("AppDelegate: [MENUBAR] VERIFY - WARNING: button is nil after setup!")
        }
    }

    @MainActor @objc private func openOmiFromMenu() {
        AnalyticsManager.shared.menuBarActionClicked(action: "open_omi")
        NSApp.activate(ignoringOtherApps: true)
        var foundWindow = false
        for window in NSApp.windows {
            if window.title.hasPrefix("Omi") {
                foundWindow = true
                window.makeKeyAndOrderFront(nil)
                window.appearance = NSAppearance(named: .darkAqua)
            }
        }
        // Restore dock icon when opening from menu bar
        showDockIcon()
        if !foundWindow {
            log("AppDelegate: [MENUBAR] WARNING - No Omi window found when opening from menu bar")
        }
    }

    @MainActor @objc private func checkForUpdates() {
        AnalyticsManager.shared.menuBarActionClicked(action: "check_updates")
        UpdaterViewModel.shared.checkForUpdates()
    }

    @MainActor @objc private func resetOnboarding() {
        AnalyticsManager.shared.menuBarActionClicked(action: "reset_onboarding")
        AppState().resetOnboardingAndRestart()
    }

    @MainActor @objc private func reportIssue() {
        AnalyticsManager.shared.menuBarActionClicked(action: "report_issue")
        FeedbackWindow.show(userEmail: AuthState.shared.userEmail)
    }

    @MainActor @objc private func signOut() {
        AnalyticsManager.shared.menuBarActionClicked(action: "sign_out")
        ProactiveAssistantsPlugin.shared.stopMonitoring()
        try? AuthService.shared.signOut()
    }

    @MainActor @objc private func quitApp() {
        AnalyticsManager.shared.menuBarActionClicked(action: "quit")
        NSApplication.shared.terminate(nil)
    }

    // MARK: - NSMenuDelegate
    func menuWillOpen(_ menu: NSMenu) {
        log("AppDelegate: [MENUBAR] Menu opened by user")
        AnalyticsManager.shared.menuBarOpened()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        // Keep app running in menu bar when all windows are closed
        return false
    }

    func applicationWillTerminate(_ notification: Notification) {
        // Remove window observers
        for observer in windowObservers {
            NotificationCenter.default.removeObserver(observer)
        }
        windowObservers.removeAll()
        // Remove hotkey monitors
        if let monitor = globalHotkeyMonitor {
            NSEvent.removeMonitor(monitor)
            globalHotkeyMonitor = nil
        }
        if let monitor = localHotkeyMonitor {
            NSEvent.removeMonitor(monitor)
            localHotkeyMonitor = nil
        }
        // Remove floating bar observers and shortcuts
        if let observer = toggleBarObserver {
            NotificationCenter.default.removeObserver(observer)
            toggleBarObserver = nil
        }
        GlobalShortcutManager.shared.unregisterShortcuts()

        // Stop push-to-talk
        PushToTalkManager.shared.cleanup()

        // Stop heartbeat timer
        sentryHeartbeatTimer?.invalidate()
        sentryHeartbeatTimer = nil

        // Stop transcription retry service
        TranscriptionRetryService.shared.stop()

        // Mark clean shutdown so next launch skips expensive DB integrity check
        RewindDatabase.markCleanShutdown()

        // Report final resources before termination
        ResourceMonitor.shared.reportResourcesNow(context: "app_terminating")
        ResourceMonitor.shared.stop()

        // Capture final session snapshot before termination (now enabled for dev builds too)
        SentrySDK.capture(message: "App Terminating") { scope in
            scope.setLevel(.info)
            scope.setTag(value: "lifecycle", key: "event_type")
        }
    }

    @objc func handleGetURLEvent(_ event: NSAppleEventDescriptor, withReplyEvent replyEvent: NSAppleEventDescriptor) {
        guard let urlString = event.paramDescriptor(forKeyword: AEKeyword(keyDirectObject))?.stringValue,
              let url = URL(string: urlString) else {
            return
        }

        NSLog("OMI AppDelegate: Received URL event: %@", urlString)

        Task { @MainActor in
            AuthService.shared.handleOAuthCallback(url: url)
        }
    }

    /// One-time migration to enable launch at login for existing users
    /// Only runs once, and only enables if user hasn't explicitly set a preference
    private func migrateLaunchAtLoginDefault() {
        let migrationKey = "didMigrateLaunchAtLoginV1"

        // Skip if migration already done
        guard !UserDefaults.standard.bool(forKey: migrationKey) else {
            return
        }

        // Mark migration as done (do this first to ensure it only runs once)
        UserDefaults.standard.set(true, forKey: migrationKey)

        // Only enable for users who have completed onboarding (existing users)
        // New users will get this enabled at the end of onboarding
        let hasCompletedOnboarding = UserDefaults.standard.bool(forKey: "hasCompletedOnboarding")
        guard hasCompletedOnboarding else {
            log("LaunchAtLogin migration: Skipped - user hasn't completed onboarding yet")
            return
        }

        // Check current status - only enable if not already registered
        // This respects users who may have explicitly disabled it via System Settings
        Task { @MainActor in
            let manager = LaunchAtLoginManager.shared
            if !manager.isEnabled {
                let success = manager.setEnabled(true)
                log("LaunchAtLogin migration: Enabled for existing user (success: \(success))")
                if success {
                    AnalyticsManager.shared.launchAtLoginChanged(enabled: true, source: "migration")
                }
            } else {
                log("LaunchAtLogin migration: Already enabled, skipping")
            }
        }
    }

    private func migrateAppNameToBeta() {
        let currentPath = Bundle.main.bundlePath

        // Case 1: Running as "Omi Computer.app" — rename self to "Omi Beta.app"
        if currentPath.hasSuffix("Omi Computer.app") {
            let key = "didMigrateAppNameToBetaV1"
            guard !UserDefaults.standard.bool(forKey: key) else { return }
            UserDefaults.standard.set(true, forKey: key)

            let dir = (currentPath as NSString).deletingLastPathComponent
            let newPath = dir + "/Omi Beta.app"
            guard !FileManager.default.fileExists(atPath: newPath) else { return }

            do {
                try FileManager.default.moveItem(atPath: currentPath, toPath: newPath)
                log("App rename migration: moved to \(newPath)")

                // Re-register with Launch Services and relaunch from new path (off main thread)
                DispatchQueue.global(qos: .utility).async {
                    let lsregister = Process()
                    lsregister.executableURL = URL(fileURLWithPath:
                        "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister")
                    lsregister.arguments = ["-f", newPath]
                    try? lsregister.run()
                    lsregister.waitUntilExit()

                    // Relaunch from new path
                    let relaunch = Process()
                    relaunch.executableURL = URL(fileURLWithPath: "/usr/bin/open")
                    relaunch.arguments = [newPath]
                    try? relaunch.run()

                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                        NSApp.terminate(nil)
                    }
                }
            } catch {
                log("App rename migration failed: \(error.localizedDescription)")
            }
            return
        }

        // Case 2: Running as "Omi Beta.app" — kill and delete old "Omi Computer.app" if it exists
        cleanupOldOmiComputerApp()
    }

    private func cleanupOldOmiComputerApp() {
        let oldAppPaths = [
            "/Applications/Omi Computer.app",
            NSHomeDirectory() + "/Applications/Omi Computer.app",
        ]

        for oldPath in oldAppPaths {
            guard FileManager.default.fileExists(atPath: oldPath) else { continue }

            log("Found old Omi Computer.app at \(oldPath), cleaning up...")

            // Kill the old app if it's running
            let running = NSRunningApplication.runningApplications(withBundleIdentifier: "com.omi.computer-macos")
            for app in running {
                guard app.processIdentifier != ProcessInfo.processInfo.processIdentifier else { continue }
                log("Terminating old Omi Computer process (PID \(app.processIdentifier))")
                app.forceTerminate()
            }

            // Wait briefly for termination, then delete
            DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + 1.0) {
                do {
                    try FileManager.default.removeItem(atPath: oldPath)
                    log("Deleted old Omi Computer.app at \(oldPath)")
                } catch {
                    log("Failed to delete old Omi Computer.app: \(error.localizedDescription)")
                    // Try moving to trash as fallback
                    do {
                        try FileManager.default.trashItem(at: URL(fileURLWithPath: oldPath), resultingItemURL: nil)
                        log("Moved old Omi Computer.app to trash")
                    } catch {
                        log("Failed to trash old Omi Computer.app: \(error.localizedDescription)")
                    }
                }
            }
        }
    }

    func applicationDidBecomeActive(_ notification: Notification) {
        AnalyticsManager.shared.appBecameActive()
        // Sync remote assistant settings so server-side changes take effect promptly
        Task { await SettingsSyncManager.shared.syncFromServer() }
    }

    func applicationWillResignActive(_ notification: Notification) {
        AnalyticsManager.shared.appResignedActive()
    }
}
