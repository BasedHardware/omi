import FirebaseAuth
import FirebaseCore
import OmiSupport
import OmiTheme
import Sentry
import Sparkle
import SwiftUI

// MARK: - Launch Mode
/// Determines which UI to show based on command-line arguments
enum LaunchMode: String {
  case full = "full"  // Normal app with full sidebar
  case rewind = "rewind"  // Rewind-only mode (no sidebar)

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

  @Published private(set) var sessionPhase: AuthSessionPhase
  @Published var isLoading: Bool = false
  @Published var error: String?
  @Published var userEmail: String?

  var isSignedIn: Bool { sessionPhase == .authenticated }
  var isRestoringAuth: Bool { sessionPhase == .restoring }

  private init() {
    BundleEnvironment.loadIfNeeded()

    // Restore auth state from UserDefaults immediately on init (before UI renders)
    let savedSignedIn = UserDefaults.standard.bool(forKey: Self.kAuthIsSignedIn)
    let savedEmail = UserDefaults.standard.string(forKey: Self.kAuthUserEmail)

    if DesktopLocalProfile.isEnabled {
      // Harness-owned emulator auth replaces any persisted cloud session.
      self.sessionPhase = .restoring
      self.userEmail = nil
    } else {
      // `auth_isSignedIn` is only a restore hint. Never expose authenticated UI
      // until AuthService has validated a usable credential for this launch.
      self.sessionPhase = savedSignedIn ? .restoring : .signedOut
      self.userEmail = savedEmail
    }
    NSLog(
      "OMI AuthState: Initialized localProfile=%@ savedSignedIn=%@ email=%@ isRestoringAuth=%@",
      DesktopLocalProfile.isEnabled ? "true" : "false",
      savedSignedIn ? "true" : "false", savedEmail ?? "nil", self.isRestoringAuth ? "true" : "false"
    )
  }

  func update(isSignedIn: Bool, userEmail: String? = nil) {
    transition(to: isSignedIn ? .authenticated : .signedOut)
    self.userEmail = userEmail
  }

  func transition(to phase: AuthSessionPhase) {
    guard sessionPhase != phase else { return }
    sessionPhase = phase
    NSLog("OMI AUTH: session phase -> %@", String(describing: phase))
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

  static let launchMode = LaunchMode.fromCommandLine()

  private var windowTitle: String {
    Self.windowTitle(
      displayName: AppBuild.displayName,
      version: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "",
      launchMode: Self.launchMode,
      isNonProduction: AppBuild.isNonProduction)
  }

  static func windowTitle(displayName: String, version: String, launchMode: LaunchMode, isNonProduction: Bool) -> String
  {
    let baseName = isNonProduction ? displayName : launchMode == .rewind ? "omi Rewind" : UpdateChannel.appDisplayName
    let title = isNonProduction && launchMode == .rewind ? "\(baseName) Rewind" : baseName
    return version.isEmpty ? title : "\(title) v\(version)"
  }

  /// Window size based on launch mode
  private var defaultWindowSize: CGSize {
    Self.launchMode == .rewind ? CGSize(width: 1000, height: 700) : CGSize(width: 1200, height: 800)
  }

  var body: some Scene {
    let _ = Self.registerOpenMainWindowHandler(openWindow)

    // Main desktop window - same view for both modes, sidebar hidden in rewind mode
    return Window(windowTitle, id: "main") {
      DesktopHomeView()
        .environmentObject(appState)
        .withFontScaling()
        .overlay(alignment: .bottomTrailing) { WhatsNewToastOverlay() }
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

      // Sidebar navigation shortcuts: Cmd+1..6 for main pages, Cmd+, for Settings
      CommandGroup(after: .sidebar) {
        Button("Home") {
          NotificationCenter.default.post(
            name: .navigateToSidebarItem, object: nil,
            userInfo: ["rawValue": SidebarNavItem.dashboard.rawValue])
        }
        .keyboardShortcut("1", modifiers: .command)

        Button("Conversations") {
          NotificationCenter.default.post(
            name: .navigateToSidebarItem, object: nil,
            userInfo: ["rawValue": SidebarNavItem.conversations.rawValue])
        }
        .keyboardShortcut("2", modifiers: .command)

        Button("Memories") {
          NotificationCenter.default.post(
            name: .navigateToSidebarItem, object: nil,
            userInfo: ["rawValue": SidebarNavItem.memories.rawValue])
        }
        .keyboardShortcut("3", modifiers: .command)

        Button("Tasks") {
          NotificationCenter.default.post(
            name: .navigateToSidebarItem, object: nil,
            userInfo: ["rawValue": SidebarNavItem.tasks.rawValue])
        }
        .keyboardShortcut("4", modifiers: .command)

        Button("Rewind") {
          NotificationCenter.default.post(
            name: .navigateToSidebarItem, object: nil,
            userInfo: ["rawValue": SidebarNavItem.rewind.rawValue])
        }
        .keyboardShortcut("5", modifiers: .command)

        Button("Apps") {
          NotificationCenter.default.post(
            name: .navigateToSidebarItem, object: nil,
            userInfo: ["rawValue": SidebarNavItem.apps.rawValue])
        }
        .keyboardShortcut("6", modifiers: .command)

        Divider()

        Button("Settings") {
          NotificationCenter.default.post(
            name: .navigateToSidebarItem, object: nil,
            userInfo: ["rawValue": SidebarNavItem.settings.rawValue])
        }
        .keyboardShortcut(",", modifiers: .command)
      }

      CommandGroup(after: .toolbar) {
        Button("Refresh") {
          NotificationCenter.default.post(name: .refreshAllData, object: nil)
        }
        .keyboardShortcut("r", modifiers: .command)
      }
    }

    // Note: Menu bar is now handled by NSStatusBar in AppDelegate.setupMenuBar()
    // for better reliability on macOS Sequoia (SwiftUI MenuBarExtra had rendering issues)
  }

  private static func registerOpenMainWindowHandler(_ openWindow: OpenWindowAction) {
    AppDelegate.openMainWindow = { openWindow(id: "main") }
  }
}

class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate, @unchecked Sendable {
  nonisolated(unsafe) static var openMainWindow: (() -> Void)?
  private nonisolated(unsafe) static var appIsActive = false
  private nonisolated(unsafe) static var mainWindowIsKey = false
  private nonisolated(unsafe) static var lastMainWindowForegroundAt: Date?

  private var sentryHeartbeatTimer: Timer?
  private var globalHotkeyMonitor: Any?
  private var localHotkeyMonitor: Any?
  private var windowObservers: [NSObjectProtocol] = []
  private var userDefaultsObserver: NSObjectProtocol?
  private var statusBarItem: NSStatusItem?
  private var screenCaptureSwitch: NSSwitch?
  private var audioRecordingSwitch: NSSwitch?
  private var relaunchOnLoginSuppressedForOnboarding = false
  private var apiKeyFetchTask: Task<Void, Never>?
  private var floatingBarPlanFetchTask: Task<Void, Never>?
  private var appLifecycleMaintenanceTask: Task<Void, Never>?
  private var didScheduleInitialSettingsSync = false
  private var initialSettingsSyncTask: Task<Void, Never>?

  func applicationWillFinishLaunching(_ notification: Notification) {
    if AuthStorageCanary.isRequested { return }
    // Single-instance guard: a second live copy of the same bundle id + launch mode
    // would race the first against the shared Rewind SQLite DB
    // (~/Library/Application Support/Omi/…) and the bundle-id UserDefaults domain,
    // corrupting state. Enforce here — the earliest delegate callback — so a duplicate
    // exits before any DB open or UserDefaults write in applicationDidFinishLaunching.
    SingleInstanceGuard.enforceSingleInstanceOrExit(
      launchMode: OMIApp.launchMode,
      isExporting: ViewExporter.shouldExport())
  }

  func applicationDidFinishLaunching(_ notification: Notification) {
    if ViewExporter.shouldExport() {
      ViewExporter.run()
      return
    }

    // The release pipeline launches the exact signed artifact in this isolated
    // mode before publication. Run before installer, database, defaults, or
    // background-service startup so the probe has no product side effects.
    if AuthStorageCanary.runIfRequested() { return }

    // Running from the mounted DMG / a translocated mount breaks TCC permissions
    // and Sparkle updates — install to /Applications and relaunch before any
    // services start. Returns true when this process is being replaced.
    if AppInstaller.moveToApplicationsIfNeeded() {
      return
    }

    // Ignore SIGPIPE so broken-pipe writes return errors instead of crashing the app.
    // Without this, writing to a dead FFmpeg stdin or agent-bridge pipe kills the process.
    signal(SIGPIPE, SIG_IGN)

    // Load bundle .env before AuthState/Firebase so local harness env is visible to getenv().
    BundleEnvironment.loadIfNeeded()

    DesktopAutomationBridge.shared.startIfNeeded()
    LocalAgentAPIServer.shared.startIfNeeded()
    publishNamedBundleRuntimeManifest()

    // Strip com.apple.provenance xattrs that macOS adds when Sparkle extracts updates.
    // These break the code signature seal, causing the NEXT update to fail with
    // "An error occurred while running the updater."
    stripProvenanceXattrs()

    log("AppDelegate: applicationDidFinishLaunching started (mode: \(OMIApp.launchMode.rawValue))")
    log("AppDelegate: AuthState.isSignedIn=\(AuthState.shared.isSignedIn)")
    let pendingUpdateRelaunch = UpdateRelaunchWindowPolicy.consumePendingRelaunch()
    let restoreMainWindowAfterUpdateRelaunch = pendingUpdateRelaunch?.restoreMainWindow
    if let restoreMainWindowAfterUpdateRelaunch {
      log(
        "AppDelegate: Sparkle update relaunch detected; restoreMainWindow=\(restoreMainWindowAfterUpdateRelaunch)"
      )
    }

    // Refresh the "Auto" realtime-voice model pick from Artificial Analysis (daily, cached).
    AutoModelSelector.shared.refreshIfStale()

    // After a Sparkle update, show a small "what's new" card in the corner of the
    // main window once. Delayed so the window/overlay exist to render it.
    if restoreMainWindowAfterUpdateRelaunch != false {
      DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
        WhatsNewToast.shared.presentIfUpdated()
      }
    }

    // Proactive notifications are now OFF by default for everyone. Run the one-time
    // migration before any assistant can fire, so existing users are flipped to Off
    // once (they can re-enable in Settings).
    NotificationService.migrateToOffByDefaultIfNeeded()

    // Force macOS to use the correct app icon (bypasses icon cache).
    // Apply squircle mask with proper margins because NSApp.applicationIconImage
    // renders the raw image without macOS auto-masking.
    // Do NOT call NSWorkspace.setIcon(forFile:) — it writes a resource fork onto
    // the .app bundle, which breaks the code signature and prevents Sparkle
    // auto-updates from working ("An error occurred while running the updater").
    if let iconURL = Bundle.resourceBundle.url(forResource: "omi_app_icon", withExtension: "png"),
      let icon = NSImage(contentsOf: iconURL)
    {
      let size = icon.size
      let maskedIcon = NSImage(size: size)
      maskedIcon.lockFocus()
      // Scale content to ~88% with 6% margin on each side (matches macOS Dock icon sizing)
      let margin = size.width * 0.06
      let contentRect = NSRect(
        x: margin, y: margin,
        width: size.width - margin * 2,
        height: size.height - margin * 2)
      // Corner radius ≈ 22.37% of content size
      let radius = contentRect.width * 0.2237
      let path = NSBezierPath(roundedRect: contentRect, xRadius: radius, yRadius: radius)
      path.addClip()
      icon.draw(in: contentRect)
      maskedIcon.unlockFocus()
      NSApp.applicationIconImage = maskedIcon
      if let cfURL = Bundle.main.bundleURL as CFURL? {
        LSRegisterURL(cfURL, true)
      }
      log("AppDelegate: Set application icon with squircle mask")
    }

    // One-time icon cache reset: forces macOS to pick up the new squircle icon.
    // Without this, users who had the old square icon see it cached indefinitely
    // in the Dock, notifications, and Sparkle updater.
    resetIconCacheIfNeeded()

    // Initialize NotificationService early to set up UNUserNotificationCenterDelegate
    // This ensures notifications display properly when app is in foreground
    _ = NotificationService.shared
    NotificationRegistrationRepair.repairOnceForCurrentVersion(reason: "startup_version_registration")

    // Initialize Sparkle auto-updater early so the 10-minute check timer starts at launch
    // Without this, the updater only starts when the user opens Settings or clicks "Check for Updates"
    _ = UpdaterViewModel.shared
    UpdaterViewModel.shared.checkForUpdatesImmediatelyAfterLaunchIfNeeded()

    // Initialize Sentry for crash reporting and error tracking.
    // Non-production bundles keep explicit feedback/error APIs available, but must
    // not install native crash/app-hang handlers: those handlers run in signal
    // context and have caused named dogfood bundles to crash while reporting.
    let isDev = AnalyticsManager.isDevBuild
    SentrySDK.start { options in
      options.dsn =
        "https://bbffa02d948c81ea4dccd36246c7bd20@o4511085999816704.ingest.us.sentry.io/4511086024851456"
      options.debug = false
      options.enableAutoSessionTracking = !isDev
      options.enableCrashHandler = !isDev
      options.enableAppHangTracking = !isDev
      options.enableWatchdogTerminationTracking = !isDev
      options.environment = isDev ? "development" : "production"
      // Disable automatic HTTP client error capture — the SDK creates noisy events
      // for every 4xx/5xx response (e.g. Cloud Run 503 cold starts on /v1/crisp/unread).
      // App code already handles HTTP errors and reports meaningful ones explicitly.
      options.enableCaptureFailedRequests = false
      options.maxBreadcrumbs = 100
      // App-hang detection fires on the main thread stalling. The default 2s threshold
      // flags transient jank (disk/IPC stalls, GC-like dealloc storms) that dominates
      // event volume without being individually actionable. Raise to 3s so only
      // sustained freezes — the ones users actually feel — are reported.
      options.appHangTimeoutInterval = isDev ? 0 : 3.0
      options.beforeSend = { event in
        // The drop decision is extracted to the pure `shouldDropSentryEvent` so the
        // filter list is unit-testable without constructing Sentry events (SET-05).
        let drop = Self.shouldDropSentryEvent(
          isUserReport: event.message?.formatted.hasPrefix("User Report") == true,
          isDev: isDev,
          urlTag: event.tags?["url"],
          messageFormatted: event.message?.formatted,
          exceptions: (event.exceptions ?? []).map { (type: $0.type, value: $0.value) })
        return drop ? nil : event
      }
    }
    log(
      "Sentry initialized (environment: \(isDev ? "development" : "production"), nativeHandlers=\(!isDev))"
    )

    // Initialize Firebase (skipped for local harness — Firebase SDK configure can hang;
    // local dev uses Auth emulator REST + stored tokens instead).
    let plistPath = Bundle.main.path(forResource: "GoogleService-Info", ofType: "plist")

    if DesktopLocalProfile.isEnabled {
      log("Local harness: skipping Firebase SDK configure; bootstrapping Auth emulator via REST")
      AuthState.shared.transition(to: .restoring)
      Task { @MainActor in
        await AuthService.shared.bootstrapLocalHarnessAuthIfNeeded()
      }
      DispatchQueue.main.asyncAfter(deadline: .now() + 10.0) {
        if AuthState.shared.isRestoringAuth {
          log("Local harness auth watchdog: clearing stuck restoring_auth splash")
          AuthState.shared.transition(to: .recoveryRequired)
        }
      }
    } else if let path = plistPath,
      let options = FirebaseOptions(contentsOfFile: path)
    {
      FirebaseApp.configure(options: options)
      Task { @MainActor in
        await AuthService.shared.configure()
      }
    } else {
      log("Firebase configure skipped (plistPath=\(plistPath ?? "nil"))")
    }

    // Initialize analytics (PostHog)
    AnalyticsManager.shared.initialize()
    AnalyticsManager.shared.detectAndReportCrash()
    if let attempt = pendingUpdateRelaunch?.attempt {
      let installedVersion =
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString")
        as? String ?? "unknown"
      let installedBuild =
        Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String
        ?? "unknown"
      if installedBuild == attempt.targetBuild {
        AnalyticsManager.shared.updateInstalled(
          attempt: attempt,
          installedVersion: installedVersion,
          installedBuild: installedBuild
        )
        log("Sparkle: Verified installed update attempt \(attempt.id) at build \(installedBuild)")
      } else {
        AnalyticsManager.shared.updateInstallVerificationFailed(
          attempt: attempt,
          installedVersion: installedVersion,
          installedBuild: installedBuild
        )
        log(
          "Sparkle: Update attempt \(attempt.id) expected build \(attempt.targetBuild), relaunched build \(installedBuild)"
        )
      }
    }
    AnalyticsManager.shared.appLaunched()

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

    // Start resource monitoring (memory, CPU, disk)
    ResourceMonitor.shared.start()

    scheduleAppLifecycleMaintenance()

    // Identify user if already signed in
    if AuthState.shared.isSignedIn {
      AnalyticsManager.shared.identify()
      // Set Sentry user context (now enabled for dev builds too)
      if let email = AuthState.shared.userEmail {
        let sentryUser = Sentry.User()
        sentryUser.email = email
        sentryUser.username =
          AuthService.shared.displayName.isEmpty ? nil : AuthService.shared.displayName
        SentrySDK.setUser(sentryUser)
      }
      // Fetch API keys after first-window warmup settles. First-use paths call waitForKeys().
      scheduleAPIKeyFetch()

      // Fetch subscription plan for floating bar usage limits after the startup warmup settles.
      scheduleFloatingBarPlanFetch()

      // Start trial metadata polling (countdown UI + pre-expiry nudges)
      if let state = AppState.current {
        state.startTrialMetadataRefresh()
        TrialBannerService.shared.start(appState: state)
      }

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

    // One-time migration: Rename app bundle from legacy names to "omi.app"
    migrateAppName()

    updateOnboardingLifecyclePolicy(reason: "launch")
    userDefaultsObserver = NotificationCenter.default.addObserver(
      forName: UserDefaults.didChangeNotification,
      object: nil,
      queue: .main
    ) { [weak self] _ in
      MainActor.assumeIsolated {
        self?.updateOnboardingLifecyclePolicy(reason: "user_defaults_changed")
      }
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

    // Register Carbon-based global shortcuts for floating control bar (Ask Omi)
    GlobalShortcutManager.shared.registerShortcuts()

    // Ensure app always shows in dock as a regular app
    NSApp.setActivationPolicy(.regular)

    // Set up menu bar icon with NSStatusBar (more reliable than SwiftUI MenuBarExtra)
    // Called synchronously on main thread to ensure status item is created before app finishes launching
    Task { @MainActor in
      self.setupMenuBar()
    }

    // Periodic health check: verify menu bar icon is still visible every 30 seconds.
    // Safety net for any edge case (macOS Sequoia bugs, activation policy races) that
    // causes the status bar item to vanish while the process keeps running.
    Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
      MainActor.assumeIsolated {
        guard let self = self else { return }
        let item = self.statusBarItem
        let button = item?.button
        let isPhantom = button != nil && button!.frame.width == 0
        if item?.isVisible != true || button == nil || isPhantom {
          log(
            "AppDelegate: [MENUBAR] Health check: icon missing or phantom (visible=\(item?.isVisible ?? false), button=\(button != nil), frame=\(button?.frame ?? .zero)), recreating"
          )
          self.setupMenuBar()
        }
      }
    }

    startSentryHeartbeat()
    startForegroundTracking()

    // Apply initial main-window policy after SwiftUI has created the window.
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
      log("AppDelegate: Checking windows after 0.2s delay, count=\(NSApp.windows.count)")
      let shouldSuppressMainWindow = restoreMainWindowAfterUpdateRelaunch == false
      if !shouldSuppressMainWindow {
        NSApp.activate()
      }
      var foundOmiWindow = false
      for window in NSApp.windows {
        log("AppDelegate: Window title='\(window.title)', isVisible=\(window.isVisible)")
        if Self.isMainOmiWindow(window) {
          foundOmiWindow = true
          window.appearance = NSAppearance(named: .darkAqua)
          // Ensure fullscreen always creates a dedicated Space
          window.collectionBehavior.insert(.fullScreenPrimary)
          if shouldSuppressMainWindow {
            window.orderOut(nil)
            log("AppDelegate: Main window suppressed after background update relaunch")
          } else {
            window.makeKeyAndOrderFront(nil)
            log("AppDelegate: Main window shown on launch")
          }
        }
      }
      if !foundOmiWindow {
        log("AppDelegate: WARNING - 'Omi' window not found!")
      }
    }

    log("AppDelegate: applicationDidFinishLaunching completed")
  }

  /// Start a timer that records Sentry session breadcrumbs every 5 minutes.
  /// Breadcrumbs preserve observability without creating unresolved Sentry issues (#9191).
  private func startSentryHeartbeat() {
    guard !AnalyticsManager.isDevBuild else { return }
    sentryHeartbeatTimer = Timer.scheduledTimer(withTimeInterval: 300, repeats: true) { _ in
      SentryHeartbeatTelemetry.recordSessionHeartbeat()
      log("Sentry: Session heartbeat breadcrumb recorded")
    }
  }

  private func startForegroundTracking() {
    Self.recordForegroundState()

    let center = NotificationCenter.default
    windowObservers.append(
      center.addObserver(
        forName: NSApplication.didBecomeActiveNotification, object: nil, queue: .main
      ) { _ in
        Self.recordForegroundState()
        Task { @MainActor in
          await AuthSessionCoordinator.shared.ensureValidSessionDebounced(
            trigger: .appBecameActive,
            auth: AuthService.shared
          )
        }
      })
    windowObservers.append(
      center.addObserver(
        forName: NSApplication.didResignActiveNotification, object: nil, queue: .main
      ) { _ in
        Self.recordForegroundState()
      })
    windowObservers.append(
      center.addObserver(
        forName: NSWindow.didBecomeKeyNotification, object: nil, queue: .main
      ) { _ in
        Self.recordForegroundState()
      })
    windowObservers.append(
      center.addObserver(
        forName: NSWindow.didResignKeyNotification, object: nil, queue: .main
      ) { _ in
        Self.recordForegroundState()
      })
  }

  static func shouldRestoreMainWindowAfterUpdateRelaunch() -> Bool {
    let readState = {
      Self.recordForegroundState()
      return UpdateRelaunchWindowPolicy.shouldRestoreMainWindow(
        appIsActive: appIsActive,
        frontmostBundleMatches: frontmostApplicationMatchesBundle(),
        mainWindowIsKey: mainWindowIsKey,
        lastMainWindowForegroundAt: lastMainWindowForegroundAt
      )
    }

    if Thread.isMainThread {
      return readState()
    }

    return DispatchQueue.main.sync(execute: readState)
  }

  private static func recordForegroundState(now: Date = Date()) {
    MainActor.assumeIsolated {
      appIsActive = NSApp.isActive
      mainWindowIsKey = NSApp.keyWindow.map(isMainOmiWindow) ?? false

      if UpdateRelaunchWindowPolicy.shouldRestoreMainWindow(
        appIsActive: appIsActive,
        frontmostBundleMatches: frontmostApplicationMatchesBundle(),
        mainWindowIsKey: mainWindowIsKey,
        lastMainWindowForegroundAt: nil,
        now: now
      ) {
        lastMainWindowForegroundAt = now
      }
    }
  }

  private static func frontmostApplicationMatchesBundle() -> Bool {
    NSWorkspace.shared.frontmostApplication?.bundleIdentifier == Bundle.main.bundleIdentifier
  }

  private static func isMainOmiWindow(_ window: NSWindow) -> Bool {
    MainActor.assumeIsolated { window.title.lowercased().hasPrefix("omi") }
  }

  /// Strip com.apple.provenance extended attributes from our own bundle.
  /// macOS adds these when Sparkle extracts the update ZIP, which breaks the code
  /// signature seal and causes subsequent updates to fail.
  private func stripProvenanceXattrs() {
    let bundlePath = Bundle.main.bundlePath
    DispatchQueue.global(qos: .utility).async {
      // A silent failure here breaks the code-signature seal and causes future
      // Sparkle updates to fail, so surface it (BL-022) instead of dropping it.
      SystemCommand.runLogging(
        "AppDelegate: strip provenance xattrs",
        executable: "/usr/bin/xattr", arguments: ["-cr", bundlePath])
    }
  }

  /// One-time icon cache reset to force macOS to pick up the new squircle icon.
  /// Runs lsregister unregister/register + kills iconservicesagent (auto-restarts).
  /// Includes a safety net to restart the Dock if it crashes during the reset.
  private func resetIconCacheIfNeeded() {
    let key = "hasResetIconCache_v2"
    guard !UserDefaults.standard.bool(forKey: key) else { return }
    UserDefaults.standard.set(true, forKey: key)
    log("AppDelegate: Running one-time icon cache reset")

    let appPath = Bundle.main.bundlePath
    let lsregister =
      "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

    DispatchQueue.global(qos: .utility).async {
      // Best-effort cosmetic maintenance. Capture each step's outcome instead of
      // dropping it with `try?`, but keep it at info level — some steps exit
      // non-zero benignly (e.g. killall when the agent isn't running), so this is
      // not routed through the failure path (BL-022).
      log(
        "Icon cache: lsregister unregister \(SystemCommand.run(executable: lsregister, arguments: ["-u", appPath]).summary)"
      )
      log(
        "Icon cache: lsregister register \(SystemCommand.run(executable: lsregister, arguments: ["-f", appPath]).summary)"
      )
      log(
        "Icon cache: kill iconservicesagent \(SystemCommand.run(executable: "/usr/bin/killall", arguments: ["iconservicesagent"]).summary)"
      )

      // Safety net: verify the Dock is still running after 2 seconds.
      // iconservicesagent restart can occasionally crash the Dock. pgrep exits
      // non-zero when Dock isn't found, which is the signal we branch on.
      Thread.sleep(forTimeInterval: 2.0)
      let dockRunning = SystemCommand.run(
        executable: "/usr/bin/pgrep", arguments: ["-x", "Dock"]
      ).isSuccess

      if !dockRunning {
        // Dock is not running — restart it
        log("AppDelegate: Dock not running after icon cache reset, restarting")
        log(
          "Icon cache: restart Dock \(SystemCommand.run(executable: "/usr/bin/open", arguments: ["-a", "Dock"]).summary)"
        )
      }

      log("AppDelegate: Icon cache reset complete")
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
        log(
          "AppDelegate: [HOTKEY] keyCode=\(keyCode), modifiers=\(modifiers.rawValue) (ctrl=\(modifiers.contains(.control)), opt=\(modifiers.contains(.option)))"
        )
      }

      // Check for Ctrl+Option+R (less likely to conflict with system shortcuts)
      let isCtrlOption = modifiers.contains(.control) && modifiers.contains(.option)
      let isR = keyCode == 15  // R key

      if isCtrlOption && isR {
        log("AppDelegate: [HOTKEY] Rewind hotkey MATCHED (Ctrl+Option+R)")
        DispatchQueue.main.async {
          log("AppDelegate: [HOTKEY] Activating app and posting notification")
          // Bring app to front
          NSApp.activate()
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

    log(
      "AppDelegate: Hotkey monitors registered - global=\(globalHotkeyMonitor != nil), local=\(localHotkeyMonitor != nil)"
    )
    log("AppDelegate: Hotkey is Ctrl+Option+R (⌃⌥R), Ask Omi via Carbon hotkeys")
  }

  // Dock icon is always visible — LSUIElement=false and activation policy stays .regular

  /// Force-refresh the menu bar icon after activation policy changes.
  /// Works around a macOS Sequoia bug where NSStatusBar items vanish
  /// when switching to .accessory activation policy.
  @MainActor private func refreshMenuBarIcon() {
    guard let item = statusBarItem else {
      // Status bar item was lost — recreate it
      log("AppDelegate: [MENUBAR] refreshMenuBarIcon: statusBarItem is nil, recreating")
      setupMenuBar()
      return
    }
    // Re-assert visibility synchronously
    item.isVisible = true
    // Re-apply the icon to force the system to redraw
    if let button = item.button {
      if OMIApp.launchMode == .rewind {
        if let icon = NSImage(
          systemSymbolName: "clock.arrow.circlepath", accessibilityDescription: "omi Rewind")
        {
          icon.isTemplate = true
          button.image = icon
        }
      } else if let iconURL = Bundle.resourceBundle.url(
        forResource: "omi_menu_bar_icon", withExtension: "png"),
        let icon = NSImage(contentsOf: iconURL)
      {
        icon.isTemplate = true
        icon.size = NSSize(width: 18, height: 18)
        button.image = icon
      }
    }
    // Safety net: verify again after a short delay
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
      let button = self?.statusBarItem?.button
      let isPhantom = button != nil && button!.frame.width == 0
      if self?.statusBarItem?.isVisible != true || isPhantom {
        log(
          "AppDelegate: [MENUBAR] Icon still not visible/phantom after refresh (frame=\(button?.frame ?? .zero)), recreating"
        )
        self?.setupMenuBar()
      }
    }
    log("AppDelegate: [MENUBAR] Refreshed status bar item after policy change")
  }

  /// Set up menu bar icon using NSStatusBar (more reliable than SwiftUI MenuBarExtra)
  @MainActor private func setupMenuBar() {
    log(
      "AppDelegate: [MENUBAR] Setting up NSStatusBar menu (macOS \(ProcessInfo.processInfo.operatingSystemVersionString))"
    )
    log(
      "AppDelegate: [MENUBAR] Thread: \(Thread.isMainThread ? "main" : "background"), statusBar items: \(NSStatusBar.system.thickness)"
    )

    // Explicitly remove old status item before creating a new one.
    // Relying on ARC deallocation alone can leave "phantom" items that exist
    // in memory but never render on screen.
    if let old = statusBarItem {
      NSStatusBar.system.removeStatusItem(old)
      statusBarItem = nil
      log("AppDelegate: [MENUBAR] Removed old status bar item before recreating")
    }

    statusBarItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)

    guard let statusBarItem = statusBarItem else {
      log("AppDelegate: [MENUBAR] ERROR - Failed to create status bar item")
      SentrySDK.capture(message: "Failed to create NSStatusItem") { scope in
        scope.setLevel(.error)
        scope.setTag(value: "menu_bar", key: "component")
      }
      return
    }

    log("AppDelegate: [MENUBAR] NSStatusItem created successfully")

    let displayName =
      Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "omi"

    // Set up the button with compact circle mark.
    if let button = statusBarItem.button {
      if OMIApp.launchMode == .rewind {
        // Rewind mode uses SF Symbol
        if let icon = NSImage(
          systemSymbolName: "clock.arrow.circlepath", accessibilityDescription: "omi Rewind")
        {
          icon.isTemplate = true
          button.image = icon
          log("AppDelegate: [MENUBAR] Rewind icon set successfully")
        }
      } else if let iconURL = Bundle.resourceBundle.url(
        forResource: "omi_menu_bar_icon", withExtension: "png"),
        let icon = NSImage(contentsOf: iconURL)
      {
        icon.isTemplate = true
        icon.size = NSSize(width: 18, height: 18)
        button.image = icon
        button.imagePosition = .imageOnly
        log("AppDelegate: [MENUBAR] Omi circle logo set successfully (size: \(icon.size))")
      } else {
        // Fallback to SF Symbol
        if let icon = NSImage(systemSymbolName: "waveform", accessibilityDescription: "omi") {
          icon.isTemplate = true
          button.image = icon
        }
        log("AppDelegate: [MENUBAR] WARNING - Failed to load omi_menu_bar_icon, using fallback")
      }
      button.toolTip = OMIApp.launchMode == .rewind ? "omi Rewind" : displayName
    } else {
      log("AppDelegate: [MENUBAR] WARNING - statusBarItem.button is nil")
    }

    // Create menu
    let menu = NSMenu()

    // Quick toggles for screen capture and audio recording.
    // When paywalled (trial expired / usage limit hit) both render OFF — the
    // features can't run, and tapping a toggle surfaces the upgrade popup.
    let paywalled = AppState.isPaywalledEffective
    let screenCaptureItem = NSMenuItem()
    let screenCaptureView = makeToggleItemView(
      title: "Screen Capture",
      iconName: "rectangle.dashed.badge.record",
      isOn: !paywalled && AssistantSettings.shared.screenAnalysisEnabled
        && ProactiveAssistantsPlugin.shared.isMonitoring,
      action: #selector(screenCaptureToggled(_:))
    )
    screenCaptureItem.view = screenCaptureView
    menu.addItem(screenCaptureItem)

    let audioRecordingItem = NSMenuItem()
    let audioRecordingView = makeToggleItemView(
      title: "Audio Recording",
      iconName: "mic.fill",
      isOn: !paywalled && AssistantSettings.shared.transcriptionEnabled,
      action: #selector(audioRecordingToggled(_:))
    )
    audioRecordingItem.view = audioRecordingView
    menu.addItem(audioRecordingItem)

    menu.addItem(NSMenuItem.separator())

    // Open app item
    let openItem = NSMenuItem(
      title: "Open \(displayName)", action: #selector(openOmiFromMenu), keyEquivalent: "o")
    openItem.target = self
    menu.addItem(openItem)

    menu.addItem(NSMenuItem.separator())

    // Check for Updates
    let updatesItem = NSMenuItem(
      title: "Check for Updates...", action: #selector(checkForUpdates), keyEquivalent: "")
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

      let resetItem = NSMenuItem(
        title: "Reset Onboarding...", action: #selector(resetOnboarding), keyEquivalent: "")
      resetItem.target = self
      menu.addItem(resetItem)

      menu.addItem(NSMenuItem.separator())

      let reportItem = NSMenuItem(
        title: "Report Issue...", action: #selector(reportIssue), keyEquivalent: "")
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
      log(
        "AppDelegate: [MENUBAR] VERIFY - button exists, frame: \(button.frame), isHidden: \(button.isHidden)"
      )
    } else {
      log("AppDelegate: [MENUBAR] VERIFY - WARNING: button is nil after setup!")
    }
  }

  @MainActor @objc private func openOmiFromMenu() {
    AnalyticsManager.shared.menuBarActionClicked(action: "open_omi")
    NSApp.activate()
    var foundWindow = revealMainWindowIfAvailable()
    if !foundWindow {
      Self.openMainWindow?()
      foundWindow = revealMainWindowIfAvailable()
    }
    // Dock icon is always visible; just activate the app
    NSApp.activate()
    if !foundWindow {
      log("AppDelegate: [MENUBAR] WARNING - No Omi window found when opening from menu bar")
    }
  }

  @MainActor private func revealMainWindowIfAvailable() -> Bool {
    for window in NSApp.windows {
      let isRealAppWindow = window.frame.width > 300 && window.frame.height > 200
      let isMenuBarPopover = window.title.hasPrefix("Item-")
      if isRealAppWindow && !isMenuBarPopover {
        window.makeKeyAndOrderFront(nil)
        window.appearance = NSAppearance(named: .darkAqua)
        return true
      }
    }
    return false
  }

  @MainActor @objc private func checkForUpdates() {
    AnalyticsManager.shared.menuBarActionClicked(action: "check_updates")
    UpdaterViewModel.shared.checkForUpdates()
  }

  @MainActor @objc private func resetOnboarding() {
    AnalyticsManager.shared.menuBarActionClicked(action: "reset_onboarding")
    (AppState.current ?? AppState()).resetOnboardingAndRestart()
  }

  @MainActor @objc private func reportIssue() {
    AnalyticsManager.shared.menuBarActionClicked(action: "report_issue")
    FeedbackWindow.show(userEmail: AuthState.shared.userEmail)
  }

  @MainActor @objc private func signOut() {
    AnalyticsManager.shared.menuBarActionClicked(action: "sign_out")
    ProactiveAssistantsPlugin.shared.stopMonitoring()
    Task { @MainActor in
      try? await AuthService.shared.signOut()
    }
  }

  @MainActor @objc private func quitApp() {
    AnalyticsManager.shared.menuBarActionClicked(action: "quit")
    NSApplication.shared.terminate(nil)
  }

  // MARK: - Menu Bar Toggle Items

  /// Create a custom NSView for a menu item with an icon, label, and toggle switch
  @MainActor private func makeToggleItemView(title: String, iconName: String, isOn: Bool, action: Selector)
    -> NSView
  {
    let height: CGFloat = 36
    let width: CGFloat = 260
    let view = NSView(frame: NSRect(x: 0, y: 0, width: width, height: height))

    // Icon — use a fixed-size image with symbol configuration for consistent rendering
    let iconView = NSImageView(frame: NSRect(x: 16, y: 10, width: 16, height: 16))
    let config = NSImage.SymbolConfiguration(pointSize: 13, weight: .medium)
    if let img = NSImage(systemSymbolName: iconName, accessibilityDescription: title)?
      .withSymbolConfiguration(config)
    {
      iconView.image = img
      iconView.contentTintColor = .secondaryLabelColor
    }
    view.addSubview(iconView)

    // Label
    let label = NSTextField(labelWithString: title)
    label.frame = NSRect(x: 40, y: 10, width: 150, height: 16)
    label.font = .systemFont(ofSize: 13)
    label.textColor = .labelColor
    view.addSubview(label)

    // Toggle switch — use .small for consistent rendering across items
    let toggle = NSSwitch()
    toggle.controlSize = .small
    toggle.state = isOn ? .on : .off
    toggle.target = self
    toggle.action = action
    toggle.sizeToFit()
    // Right-aligned position, pinned to right edge even when menu resizes the view
    let toggleX = width - toggle.frame.width - 16
    let toggleY = (height - toggle.frame.height) / 2
    toggle.frame = NSRect(
      x: toggleX, y: toggleY, width: toggle.frame.width, height: toggle.frame.height)
    toggle.autoresizingMask = [.minXMargin]
    view.addSubview(toggle)

    // Store reference for later updates
    if action == #selector(screenCaptureToggled(_:)) {
      screenCaptureSwitch = toggle
    } else if action == #selector(audioRecordingToggled(_:)) {
      audioRecordingSwitch = toggle
    }

    return view
  }

  @MainActor @objc private func screenCaptureToggled(_ sender: NSSwitch) {
    let enabled = sender.state == .on
    log("AppDelegate: [MENUBAR] Screen capture toggled: \(enabled)")
    AnalyticsManager.shared.menuBarActionClicked(
      action: enabled ? "screen_capture_on" : "screen_capture_off")
    AnalyticsManager.shared.settingToggled(setting: "monitoring", enabled: enabled)

    if enabled {
      // Paywall gate: trial expired / usage limit hit. Refuse to enable,
      // revert the toggle, and surface the same upgrade popup as everywhere else.
      if AppState.isPaywalledEffective {
        sender.state = .off
        NotificationCenter.default.post(
          name: .showUsageLimitPopup, object: nil, userInfo: ["reason": "trial_expired"])
        return
      }
      if !ProactiveAssistantsPlugin.shared.hasScreenRecordingPermission {
        // No permission — revert toggle, register + open preferences (PERM-02)
        sender.state = .off
        ScreenCaptureService.requestScreenRecordingAccessAndOpenSettings()
        return
      }
      AssistantSettings.shared.screenAnalysisEnabled = true
      ProactiveAssistantsPlugin.shared.startMonitoring { success, error in
        DispatchQueue.main.async {
          if !success {
            log("AppDelegate: [MENUBAR] Screen capture failed to start: \(error ?? "unknown")")
            sender.state = .off
            AssistantSettings.shared.screenAnalysisEnabled = false
          }
        }
      }
    } else {
      AssistantSettings.shared.screenAnalysisEnabled = false
      ProactiveAssistantsPlugin.shared.stopMonitoring()
    }
  }

  @MainActor @objc private func audioRecordingToggled(_ sender: NSSwitch) {
    let enabled = sender.state == .on
    log("AppDelegate: [MENUBAR] Audio recording toggled: \(enabled)")
    AnalyticsManager.shared.menuBarActionClicked(
      action: enabled ? "audio_recording_on" : "audio_recording_off")
    AnalyticsManager.shared.settingToggled(setting: "transcription", enabled: enabled)

    // Paywall gate: trial expired / usage limit hit. Refuse to enable,
    // revert the toggle, and surface the same upgrade popup as everywhere else.
    if enabled && AppState.isPaywalledEffective {
      sender.state = .off
      NotificationCenter.default.post(
        name: .showUsageLimitPopup, object: nil, userInfo: ["reason": "trial_expired"])
      return
    }

    AssistantSettings.shared.transcriptionEnabled = enabled
    // Request the main view to start/stop transcription (needs AppState)
    NotificationCenter.default.post(
      name: .toggleTranscriptionRequested,
      object: nil,
      userInfo: ["enabled": enabled]
    )
  }

  // MARK: - NSMenuDelegate
  func menuWillOpen(_ menu: NSMenu) {
    log("AppDelegate: [MENUBAR] Menu opened by user")
    AnalyticsManager.shared.menuBarOpened()
    // Refresh toggle states to match current runtime state. When paywalled,
    // force both OFF — the features can't run until the user upgrades.
    let paywalled = AppState.isPaywalledEffective
    screenCaptureSwitch?.state =
      (!paywalled && ProactiveAssistantsPlugin.shared.isMonitoring) ? .on : .off
    audioRecordingSwitch?.state =
      (!paywalled && AssistantSettings.shared.transcriptionEnabled) ? .on : .off
  }

  func menuDidClose(_ menu: NSMenu) {
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
      MainActor.assumeIsolated {
        for window in NSApp.windows where self.isMenuPopupWindow(window) && window.isVisible {
          log("AppDelegate: [MENUBAR] Cleaning up lingering menu popup window: \(window.frame)")
          window.orderOut(nil)
        }
      }
    }
  }

  private func isMenuPopupWindow(_ window: NSWindow) -> Bool {
    // AppKit menu popup windows use private classes/titles like "NSPopupMenuWindow" and "Item-0".
    MainActor.assumeIsolated {
      window.title.hasPrefix("Item-") && window.className.contains("PopupMenuWindow")
    }
  }

  func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
    let shouldTerminate = !UserDefaults.standard.bool(forKey: "hasCompletedOnboarding")
    if shouldTerminate {
      log(
        "AppDelegate: Last onboarding window closed — terminating instead of keeping a background menu bar process"
      )
    }
    return shouldTerminate
  }

  func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
    // Always try to show the main Omi window when dock icon is clicked
    for window in sender.windows where window.title.hasPrefix("Omi") {
      if window.isMiniaturized {
        window.deminiaturize(nil)
      }
      window.makeKeyAndOrderFront(nil)
      sender.activate(ignoringOtherApps: true)
      log("AppDelegate: Restored Omi window from dock click (wasVisible=\(flag))")
      return false
    }
    return true
  }

  /// Publish only token-free local diagnostics for a running named dev bundle.
  /// The agent-facing doctor reads endpoint URLs from the loopback health route,
  /// not from this durable file.
  private func publishNamedBundleRuntimeManifest() {
    guard DesktopLocalProfile.isNamedDevelopmentBundle,
      let bundleID = Bundle.main.bundleIdentifier
    else { return }

    let manifest = DesktopDevRuntimeManifest(
      bundleIdentifier: bundleID,
      processID: ProcessInfo.processInfo.processIdentifier,
      startedAt: Date(),
      appPath: Bundle.main.bundleURL.path,
      profileRoot: DesktopLocalProfile.applicationSupportURL().path,
      logPath: omiLogFilePath(),
      automationPort: Int(DesktopAutomationLaunchOptions.port))
    do {
      try DesktopDevRuntimeManifestStore.write(
        manifest,
        in: DesktopLocalProfile.applicationSupportURL())
      log("AppDelegate: Published named-bundle runtime manifest")
    } catch {
      logError("AppDelegate: Failed to publish named-bundle runtime manifest", error: error)
    }
  }

  func applicationWillTerminate(_ notification: Notification) {
    // Mark clean exit so crash detection works on next launch
    UserDefaults.standard.set(true, forKey: "lastSessionCleanExit")

    // Remove window observers
    for observer in windowObservers {
      NotificationCenter.default.removeObserver(observer)
    }
    windowObservers.removeAll()
    if let observer = userDefaultsObserver {
      NotificationCenter.default.removeObserver(observer)
      userDefaultsObserver = nil
    }
    // Remove hotkey monitors
    if let monitor = globalHotkeyMonitor {
      NSEvent.removeMonitor(monitor)
      globalHotkeyMonitor = nil
    }
    if let monitor = localHotkeyMonitor {
      NSEvent.removeMonitor(monitor)
      localHotkeyMonitor = nil
    }
    // Remove floating bar shortcuts
    GlobalShortcutManager.shared.unregisterShortcuts()

    // Stop push-to-talk
    PushToTalkManager.shared.cleanup()

    // Stop heartbeat timer
    sentryHeartbeatTimer?.invalidate()
    sentryHeartbeatTimer = nil

    apiKeyFetchTask?.cancel()
    apiKeyFetchTask = nil
    floatingBarPlanFetchTask?.cancel()
    floatingBarPlanFetchTask = nil
    appLifecycleMaintenanceTask?.cancel()
    appLifecycleMaintenanceTask = nil
    initialSettingsSyncTask?.cancel()
    initialSettingsSyncTask = nil

    // Stop transcription retry service
    TranscriptionRetryService.shared.stop()

    // Stop recurring task scheduler
    RecurringTaskScheduler.shared.stop()

    // Finalize the active Rewind MP4 chunk while the app is still alive.
    // AVAssetWriter files are not readable until finishWriting writes the trailer.
    let didFlushRewind = RewindShutdownFlush.flush(timeout: 5, context: "AppDelegate")

    // Mark clean shutdown only after Rewind finalized its active MP4 chunk.
    if didFlushRewind {
      RewindDatabase.markCleanShutdown()
    }

    // Report final resources before termination
    ResourceMonitor.shared.reportResourcesNow(context: "app_terminating")
    ResourceMonitor.shared.stop()

    if !AnalyticsManager.isDevBuild {
      let breadcrumb = Breadcrumb(level: .info, category: "lifecycle")
      breadcrumb.message = "App Terminating"
      SentrySDK.addBreadcrumb(breadcrumb)
    }
  }

  @objc func handleGetURLEvent(
    _ event: NSAppleEventDescriptor, withReplyEvent replyEvent: NSAppleEventDescriptor
  ) {
    guard
      let urlString = event.paramDescriptor(forKeyword: AEKeyword(keyDirectObject))?.stringValue,
      let url = URL(string: urlString)
    else {
      return
    }

    NSLog("OMI AppDelegate: Received URL event: %@", urlString)

    Task { @MainActor in
      AuthService.shared.handleOAuthCallback(url: url)
      // Bring app to foreground after OAuth redirect — Safari stays in front otherwise.
      // NSApp.activate() alone doesn't switch macOS Spaces; ordering a window front does.
      NSApp.activate()
      if let window = NSApp.windows.first(where: { $0.isVisible && !$0.isMiniaturized })
        ?? NSApp.windows.first(where: { !$0.isMiniaturized })
      {
        window.makeKeyAndOrderFront(nil)
        window.orderFrontRegardless()
      }
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

  private func updateOnboardingLifecyclePolicy(reason: String) {
    // Only the production/beta bundle (com.omi.computer-macos) should relaunch on login.
    // Dev and named test bundles must always opt out — otherwise every local build that was
    // open at shutdown gets relaunched on the next restart, swarming the screen with dev apps.
    MainActor.assumeIsolated {
      guard AppBuild.isProductionBundle else {
        guard !relaunchOnLoginSuppressedForOnboarding else { return }
        NSApp.disableRelaunchOnLogin()
        relaunchOnLoginSuppressedForOnboarding = true
        log("AppDelegate: Disabled relaunch on login for non-production bundle (\(reason))")
        return
      }

      let hasCompletedOnboarding = UserDefaults.standard.bool(forKey: DefaultsKey.hasCompletedOnboarding.rawValue)

      if hasCompletedOnboarding {
        guard relaunchOnLoginSuppressedForOnboarding else { return }
        NSApp.enableRelaunchOnLogin()
        relaunchOnLoginSuppressedForOnboarding = false
        log("AppDelegate: Re-enabled relaunch on login after onboarding completed (\(reason))")
        return
      }

      guard !relaunchOnLoginSuppressedForOnboarding else { return }
      NSApp.disableRelaunchOnLogin()
      relaunchOnLoginSuppressedForOnboarding = true
      log("AppDelegate: Disabled relaunch on login while onboarding is incomplete (\(reason))")
    }
  }

  private func migrateAppName() {
    // No rename migration — APFS is case-insensitive so "omi.app" and "Omi.app"
    // collide. Renaming the running app also breaks Dock pins and Spotlight indexing.
    // The app ships as "omi.app" for new installs; existing users keep their current
    // bundle name and get updates in-place via Sparkle.

    // Clean up stale legacy bundles (never the running app)
    cleanupLegacyAppBundles()
  }

  private func cleanupLegacyAppBundles() {
    let currentPath = Bundle.main.bundlePath
    let oldAppPaths = [
      "/Applications/Omi Computer.app",
      NSHomeDirectory() + "/Applications/Omi Computer.app",
    ]

    for oldPath in oldAppPaths {
      // Never delete the running app
      guard oldPath != currentPath else { continue }
      guard FileManager.default.fileExists(atPath: oldPath) else { continue }

      log("Found old app at \(oldPath), cleaning up...")

      // Kill the old app if it's running
      let running = NSRunningApplication.runningApplications(
        withBundleIdentifier: "com.omi.computer-macos")
      for app in running {
        guard app.processIdentifier != ProcessInfo.processInfo.processIdentifier else { continue }
        log("Terminating old Omi Computer process (PID \(app.processIdentifier))")
        app.forceTerminate()
      }

      // Wait briefly for termination, then delete
      DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + 1.0) {
        do {
          try FileManager.default.removeItem(atPath: oldPath)
          log("Deleted old app at \(oldPath)")
        } catch {
          log("Failed to delete old app: \(error.localizedDescription)")
          // Try moving to trash as fallback
          do {
            try FileManager.default.trashItem(
              at: URL(fileURLWithPath: oldPath), resultingItemURL: nil)
            log("Moved old app to trash")
          } catch {
            log("Failed to trash old app: \(error.localizedDescription)")
          }
        }
      }
    }
  }

  private func scheduleFloatingBarPlanFetch() {
    floatingBarPlanFetchTask?.cancel()
    floatingBarPlanFetchTask = Task {
      let delay = StartupWarmupPolicy.floatingBarPlanFetchDelay
      if delay > 0 {
        try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
      }
      guard !Task.isCancelled else { return }
      guard await AuthState.shared.isSignedIn else { return }
      await FloatingBarUsageLimiter.shared.fetchPlan()
    }
  }

  private func scheduleAPIKeyFetch() {
    apiKeyFetchTask?.cancel()
    apiKeyFetchTask = Task {
      let delay = StartupWarmupPolicy.apiKeyFetchDelay
      if delay > 0 {
        try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
      }
      guard !Task.isCancelled else { return }
      guard await AuthState.shared.isSignedIn else { return }
      log("AppDelegate: Starting delayed API key fetch")
      await APIKeyService.shared.waitForKeys()
    }
  }

  private func scheduleAppLifecycleMaintenance() {
    appLifecycleMaintenanceTask?.cancel()
    appLifecycleMaintenanceTask = Task {
      let recoveryDelay = StartupWarmupPolicy.transcriptionRetryRecoveryDelay
      if recoveryDelay > 0 {
        try? await Task.sleep(nanoseconds: UInt64(recoveryDelay * 1_000_000_000))
      }
      guard !Task.isCancelled else { return }

      await measurePerfAsync("AppDelegate: Transcription retry recovery") {
        await TranscriptionRetryService.shared.recoverPendingTranscriptions()
        await MainActor.run {
          TranscriptionRetryService.shared.start()
        }
      }

      // Legacy recurring-task investigations silently started agent work and
      // could create durable continuity without an explicit user action. Keep
      // the compatibility service stopped; contextual resurfacing owns future
      // proactive entry points without silently launching work.
    }
  }

  func applicationDidBecomeActive(_ notification: Notification) {
    guard didScheduleInitialSettingsSync else {
      scheduleInitialSettingsSync()
      return
    }

    // Sync remote assistant settings so server-side changes take effect promptly
    Task { await SettingsSyncManager.shared.syncFromServer() }
  }

  private func scheduleInitialSettingsSync() {
    didScheduleInitialSettingsSync = true
    initialSettingsSyncTask?.cancel()
    initialSettingsSyncTask = Task {
      let delay = StartupWarmupPolicy.initialSettingsSyncDelay
      if delay > 0 {
        try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
      }
      guard !Task.isCancelled else { return }
      await SettingsSyncManager.shared.syncFromServer()
    }
  }
}

extension AppDelegate {
  /// Pure Sentry `beforeSend` triage (SET-05): decides whether an event must be
  /// dropped (`beforeSend` returns nil). Extracted from the SDK closure so the drop
  /// list is unit-testable; it takes only the event fields the closure inspects, so
  /// no Sentry `Event` needs constructing in tests. Keep in lockstep with the
  /// `options.beforeSend` closure in `applicationDidFinishLaunching`.
  static func shouldDropSentryEvent(
    isUserReport: Bool,
    isDev: Bool,
    urlTag: String?,
    messageFormatted: String?,
    exceptions: [(type: String, value: String)]
  ) -> Bool {
    // Always keep user feedback (dev + prod).
    if isUserReport { return false }
    // Never send other events from dev builds — they pollute production Sentry data.
    if isDev { return true }
    // Drop HTTP errors targeting dev/local URLs — noise when tunnels or local backends are down.
    if let urlTag,
      urlTag.contains("localhost") || urlTag.contains("127.0.0.1")
        || urlTag.contains("trycloudflare.com")
    {
      return true
    }
    // Drop transient network/socket errors captured as exceptions (offline, timeouts,
    // dropped connections, cancellations) — not actionable, dominate event volume.
    let transientNetworkCodes: [(domain: String, codes: [String])] = [
      ("NSURLErrorDomain", ["-999", "-1001", "-1003", "-1004", "-1005", "-1009", "-1011", "-1020"]),
      ("NSPOSIXErrorDomain", ["54", "57", "89"]),
    ]
    if exceptions.contains(where: { exc in
      transientNetworkCodes.contains { entry in
        exc.type == entry.domain
          && entry.codes.contains { exc.value.contains("Code=\($0)") || exc.value.contains("Code: \($0)") }
      }
    }) {
      return true
    }
    // Drop backend Gemini key-expiry/auth failures — server-side key rotation, not a
    // per-client bug; one bad key otherwise floods Sentry with one event per request.
    if let lower = messageFormatted?.lowercased(),
      lower.contains("api key expired") || lower.contains("renew the api key")
        || lower.contains("api_key_invalid")
        || lower.contains("ai service authentication error")
        || lower.contains("invalid_auth")
    {
      return true
    }
    // Drop AuthError.notSignedIn — transient refresh failure; the 30s timer retries.
    if exceptions.contains(where: {
      $0.type == "Omi_Computer.AuthError" && $0.value.contains("notSignedIn")
    }) {
      return true
    }
    return false
  }
}
