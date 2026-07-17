import AppKit
import OmiTheme
import SwiftUI

private struct AnySendableBox: @unchecked Sendable { let value: Any? }

// MARK: - NSHostingView sizingOptions access

/// Protocol to access sizingOptions on any NSHostingView<Content> regardless of the generic parameter.
/// NSHostingView is generic so we can't cast to it without knowing Content.
/// This protocol + extension lets us access sizingOptions through existential dispatch.
@MainActor
private protocol HostingSizingConfigurable: AnyObject {
  var sizingOptions: NSHostingSizingOptions { get set }
}
extension NSHostingView: HostingSizingConfigurable {}

struct DesktopHomeView: View {
  private let minimumWindowWidth: CGFloat = 1200
  private let minimumWindowHeight: CGFloat = 680
  private static let pageNavigationAnimation = Animation.easeOut(duration: 0.08)

  @EnvironmentObject private var appState: AppState
  @StateObject private var viewModelContainer = ViewModelContainer()
  /// The cohort shell owns typed navigation at the root, never through legacy
  /// sidebar indices. It persists only route/collapse state, not enrollment.
  @StateObject private var chatFirstNavigation = ChatFirstShellNavigation()
  @ObservedObject private var authState = AuthState.shared
  @ObservedObject private var apiKeyService = APIKeyService.shared
  @ObservedObject private var updatePolicyManager = DesktopUpdatePolicyManager.shared
  @ObservedObject private var automationPresentationCoordinator =
    DesktopAutomationPresentationCoordinator.shared
  @State private var selectedIndex: Int = {
    if OMIApp.launchMode == .rewind { return SidebarNavItem.rewind.rawValue }
    let tier = UserDefaults.standard.integer(forKey: "currentTierLevel")
    return SidebarNavItem.dashboard.rawValue
  }()
  @State private var isSidebarCollapsed: Bool = true
  @AppStorage("currentTierLevel") private var currentTierLevel = 0
  @AppStorage("onboardingStep") private var onboardingStep = 0
  @AppStorage("onboardingJustCompleted") private var onboardingJustCompleted = false
  @AppStorage("useLegacyHomeDesign") private var useLegacyHomeDesign = false

  // Settings sidebar state
  @State private var selectedSettingsSection: SettingsContentView.SettingsSection = .general
  @State private var highlightedSettingId: String? = nil
  @State private var showTryAskingPopup = false
  @State private var previousIndexBeforeSettings: Int = 0
  @State private var logoPulse = false
  @State private var lastActivationRefresh = Date.distantPast
  @State private var didScheduleAgentVMProvisioning = false
  @State private var proactiveMonitoringStartGate = RetryableDelayedStartGate()
  // Anchor for the proactive-monitoring warmup budget. Captured at view
  // creation (≈ launch) so the delay is spent once per session, not once per
  // trigger — see StartupWarmupPolicy.remainingProactiveAssistantsStartDelay.
  @State private var proactiveMonitoringWarmupAnchor = Date()
  @State private var didScheduleConversationWarmup = false
  @State private var initialFileIndexingBackfill = DelayedFileIndexingBackfillState()
  @State private var automationPresentationReadinessGate =
    DesktopAutomationPresentationReadinessGate()
  @State private var chatFirstCapabilitySample = ChatFirstShellCapabilitySample()

  // Pre-loaded hero logo to avoid NSImage init crashes during SwiftUI body evaluation
  private static let heroLogoImage: NSImage? = {
    guard let url = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
      let data = try? Data(contentsOf: url)
    else { return nil }
    return NSImage(data: data)
  }()

  /// Whether we're currently viewing the settings page
  private var isInSettings: Bool {
    selectedIndex == SidebarNavItem.settings.rawValue
  }

  var body: some View {
    Group {
      if authState.isRestoringAuth {
        // State 0: Restoring auth session - show loading
        VStack(spacing: OmiSpacing.lg) {
          if let nsImage = Self.heroLogoImage {
            Image(nsImage: nsImage)
              .resizable()
              .scaledToFit()
              .frame(width: 64, height: 64)
          }
          ProgressView()
            .scaleEffect(0.8)
            .tint(.white.opacity(0.6))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onAppear {
          log("DesktopHomeView: Showing auth loading splash")
        }
      } else if authState.sessionPhase == .recoveryRequired {
        SessionRecoveryView()
          .onAppear {
            log("DesktopHomeView: Showing recoverable auth state")
          }
      } else if !authState.isSignedIn {
        // State 1: Not signed in - show sign in
        SignInView(authState: authState)
          .onAppear {
            log("DesktopHomeView: Showing SignInView (not signed in)")
          }
      } else if !appState.hasCompletedOnboarding {
        // State 2: Signed in but onboarding not complete
        if shouldSkipOnboarding() {
          Color.clear.onAppear {
            log("DesktopHomeView: --skip-onboarding flag detected, skipping onboarding")
            appState.hasCompletedOnboarding = true
          }
        } else {
          OnboardingView(
            appState: appState, chatProvider: viewModelContainer.chatProvider, onComplete: nil
          )
          .onAppear {
            log("DesktopHomeView: Showing OnboardingView (signed in, not onboarded)")
          }
        }
      } else if case .unresolved = chatFirstCapabilitySample.variant {
        // Do not flash the legacy shell while the server-authoritative cohort
        // sample is in flight. No Main Chat resolution or startup warmup runs
        // until this settles to an immutable session choice.
        ChatFirstCapabilityLoadingView()
          .task(id: RuntimeOwnerIdentity.currentOwnerId() ?? "missing-owner") {
            await resolveChatFirstCapabilityIfNeeded()
          }
      } else {
        // State 3: Signed in and onboarded with a fixed shell choice.
        ZStack {
          // After onboarding completes, navigate to Tasks page
          Color.clear
            .frame(width: 0, height: 0)
            .onAppear {
              if UserDefaults.standard.bool(forKey: "onboardingJustCompleted") {
                UserDefaults.standard.removeObject(forKey: "onboardingJustCompleted")
                navigateAfterOnboarding()
              }
            }
          mainContent
            .opacity(viewModelContainer.isInitialLoadComplete ? 1 : 0)
            .overlay {
              if appState.showUsageLimitPopup {
                UsageLimitPopupView(
                  reason: appState.usageLimitReason,
                  onUpgrade: {
                    appState.showUsageLimitPopup = false
                    selectedSettingsSection = .planUsage
                    // Plan and Usage now lives below Account on the merged
                    // "Account & Plan" page — scroll straight to the plan card.
                    highlightedSettingId = "planusage.current"
                    OmiMotion.withGated(Self.pageNavigationAnimation) {
                      navigateToLegacyDestination(.settings)
                    }
                  },
                  onDismiss: {
                    appState.showUsageLimitPopup = false
                  },
                  onBringYourOwnKeys: {
                    appState.showUsageLimitPopup = false
                    selectedSettingsSection = .advanced
                    OmiMotion.withGated(Self.pageNavigationAnimation) {
                      navigateToLegacyDestination(.settings)
                    }
                  }
                )
              }
            }
            .overlay(alignment: .top) {
              if let policy = updatePolicyManager.visiblePolicy, !policy.isRequired {
                DesktopUpdatePolicyBanner(
                  policy: policy,
                  onDownload: { updatePolicyManager.openDownload(policy) },
                  onDismiss: { updatePolicyManager.dismiss(policy) }
                )
                .padding(.top, OmiSpacing.md)
                .padding(.horizontal, OmiSpacing.xl)
                .transition(.move(edge: .top).combined(with: .opacity))
              }
            }
            .onReceive(NotificationCenter.default.publisher(for: .showUsageLimitPopup)) { notification in
              let reason = notification.userInfo?["reason"] as? String ?? ""
              appState.triggerUsageLimitPopup(reason: reason)
            }
            .onAppear {
              log("DesktopHomeView: Showing mainContent (signed in and onboarded)")
              updatePolicyManager.refresh(force: true)
              // Check all permissions on launch
              appState.checkAllPermissions()

              // For existing users who haven't indexed files yet, run a background scan
              if !AppBuild.usesLazyDevPermissions
                && !UserDefaults.standard.bool(forKey: "hasCompletedFileIndexing")
              {
                scheduleInitialFileIndexing()
              }

              let settings = AssistantSettings.shared

              // Auto-start transcription if enabled in settings.
              // If API keys aren't loaded yet, onChange below retries.
              if settings.transcriptionEnabled && !appState.isTranscribing {
                if APIKeyService.keysAvailable {
                  log("DesktopHomeView: Auto-starting transcription")
                  appState.startTranscription()
                } else {
                  log("DesktopHomeView: Deferring transcription — API keys not yet loaded")
                  Task { await APIKeyService.shared.waitForKeys() }
                }
              } else if !settings.transcriptionEnabled {
                log("DesktopHomeView: Transcription disabled in settings, skipping auto-start")
              }

              // Migration: one-time reset for users whose screenAnalysisEnabled
              // was incorrectly set to false by a bug in syncMonitoringState() that
              // persisted false whenever monitoring stopped for any reason.
              // v2: re-run because the root cause (syncMonitoringState disabling the
              // setting) was only fixed in this release, so v1 users got re-broken.
              let migrationKey = "screenAnalysisAutoStartFixed_v2"
              if !UserDefaults.standard.bool(forKey: migrationKey) {
                UserDefaults.standard.set(true, forKey: "screenAnalysisEnabled")
                AssistantSettings.shared.screenAnalysisEnabled = true
                UserDefaults.standard.set(true, forKey: migrationKey)
                log(
                  "DesktopHomeView: Applied screenAnalysisAutoStart v2 migration — reset to enabled"
                )
                // Push true to server so syncFromServer() doesn't revert it
                Task { await SettingsSyncManager.shared.syncToServer() }
              }

              // Start proactive assistants monitoring if enabled in settings.
              // If API keys aren't loaded yet, this may fail — onChange below retries.
              if settings.screenAnalysisEnabled {
                if APIKeyService.keysAvailable {
                  scheduleProactiveMonitoringStart(reason: "launch")
                } else {
                  log(
                    "DesktopHomeView: Deferring screen analysis — API keys not yet loaded"
                  )
                }
              } else {
                log("DesktopHomeView: Screen analysis disabled in settings, skipping auto-start")
              }

              // Start Crisp chat in background for notifications, scoped to the signed-in user
              CrispManager.shared.start(
                initialPollDelay: StartupWarmupPolicy.crispInitialPollDelay,
                sessionUserId: UserDefaults.standard.string(forKey: "auth_userId")
              )

              // Set up floating control bar. Product invariant: normal signed-in
              // launches must show the enabled bar immediately; hide-until-PTT is
              // only for explicit onboarding/demo/minimal-mode contexts.
              FloatingControlBarManager.shared.setup(
                appState: appState, chatProvider: viewModelContainer.chatProvider)
              FloatingControlBarManager.shared.presentForLaunch(context: .normalSignedInDesktop)

              // Set up push-to-talk voice input
              if let barState = FloatingControlBarManager.shared.barState {
                PushToTalkManager.shared.setup(barState: barState)
              }
            }
            .task {
              // Trigger eager data loading when main content appears
              await viewModelContainer.loadAllData()
              scheduleConversationWarmup()
              scheduleAgentVMProvisioning()
            }
            // Refresh conversations when app becomes active (e.g. switching back from another app)
            .onReceive(
              NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)
            ) { _ in
              // Cooldown: only refresh conversations if last activation was 60+ seconds ago
              let now = Date()
              if PollingConfig.shouldAllowActivationRefresh(now: now, lastRefresh: lastActivationRefresh) {
                lastActivationRefresh = now
                Task { await appState.refreshConversations() }
              }
              updatePolicyManager.refresh()
              // Auto-start monitoring when returning to app if screen analysis is enabled
              // but monitoring is not running. Handles the case where the user granted
              // screen recording permission in System Settings and switched back.
              let plugin = ProactiveAssistantsPlugin.shared
              if AssistantSettings.shared.screenAnalysisEnabled && !plugin.isMonitoring {
                plugin.refreshScreenRecordingPermission()
                if plugin.hasScreenRecordingPermission {
                  log("DesktopHomeView: Permission available on app active — scheduling monitoring")
                  scheduleProactiveMonitoringStart(reason: "app active")
                }
              }
            }
            .onChange(of: apiKeyService.isLoaded) { _, loaded in
              guard loaded else { return }
              log("DesktopHomeView: API keys loaded — retrying deferred services")
              // Retry transcription
              if AssistantSettings.shared.transcriptionEnabled && !appState.isTranscribing {
                log("DesktopHomeView: Starting deferred transcription")
                appState.startTranscription()
              }
              // Retry screen analysis
              let plugin = ProactiveAssistantsPlugin.shared
              if AssistantSettings.shared.screenAnalysisEnabled && !plugin.isMonitoring {
                scheduleProactiveMonitoringStart(reason: "key load")
              }
            }
            // Cmd+R: refresh all data (conversations, chat, tasks, memories)
            .onReceive(NotificationCenter.default.publisher(for: .refreshAllData)) { _ in
              Task { await appState.refreshConversations() }
            }
            // On sign-out: reset @AppStorage-backed onboarding flag and stop transcription.
            // hasCompletedOnboarding must be set here (in a View) because @AppStorage
            // on ObservableObject caches internally and ignores UserDefaults.removeObject().
            // Stopping transcription here prevents FOREIGN KEY errors from an old
            // transcription session writing to a new user's database.
            .onReceive(NotificationCenter.default.publisher(for: .userDidSignOut)) { _ in
              log(
                "DesktopHomeView: userDidSignOut — resetting hasCompletedOnboarding and stopping transcription"
              )
              chatFirstCapabilitySample.ownerDidChange(to: nil)
              resetSessionScopedStartupWarmups(preserveCrispReadState: false)
              appState.conversationRepository.reset()
              appState.folders = []
              appState.selectedFolderId = nil
              appState.selectedDateFilter = nil
              appState.showStarredOnly = false
              appState.totalConversationsCount = nil
              appState.conversationsError = nil
              appState.isLoadingConversations = false
              appState.isLoadingFolders = false
              appState.hasCompletedOnboarding = false
              appState.stopTranscription()
            }
            .onReceive(NotificationCenter.default.publisher(for: .resetOnboardingRequested)) { _ in
              log(
                "DesktopHomeView: resetOnboardingRequested — clearing live onboarding state for current app"
              )
              resetSessionScopedStartupWarmups(preserveCrispReadState: false)
              appState.hasCompletedOnboarding = false
              onboardingStep = 0
              onboardingJustCompleted = false
              appState.stopTranscription()
            }
            .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
              log("DesktopHomeView: app terminating — cancelling startup warmups")
              resetSessionScopedStartupWarmups(preserveCrispReadState: true)
            }
            // Handle transcription toggle from menu bar
            .onReceive(NotificationCenter.default.publisher(for: .toggleTranscriptionRequested)) {
              notification in
              if let enabled = notification.userInfo?["enabled"] as? Bool {
                log("DesktopHomeView: Menu bar toggled transcription: \(enabled)")
                if enabled {
                  appState.startTranscription()
                } else {
                  appState.stopTranscription()
                }
              }
            }
            // Periodic file re-scan (every 3 hours)
            .task {
              while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(3 * 60 * 60))
                guard !Task.isCancelled else { break }
                guard !AppBuild.usesLazyDevPermissions else { continue }
                guard UserDefaults.standard.bool(forKey: "hasCompletedFileIndexing") else {
                  continue
                }
                log("DesktopHomeView: Triggering background file rescan")
                await FileIndexerService.shared.backgroundRescan()
              }
            }
            .onReceive(NotificationCenter.default.publisher(for: .triggerFileIndexing)) { _ in
              // Background rescan — no loading screen needed
              Task {
                log(
                  "DesktopHomeView: File indexing triggered from settings, running background rescan"
                )
                await FileIndexerService.shared.backgroundRescan()
              }
            }

          if !viewModelContainer.isInitialLoadComplete {
            VStack(spacing: OmiSpacing.xxl) {
              if let nsImage = Self.heroLogoImage {
                Image(nsImage: nsImage)
                  .resizable()
                  .scaledToFit()
                  .frame(width: 72, height: 72)
                  .scaleEffect(logoPulse ? 1.08 : 1.0)
                  .opacity(logoPulse ? 1.0 : 0.7)
                  .omiAnimation(
                    .easeInOut(duration: 1.2).repeatForever(autoreverses: true),
                    value: logoPulse
                  )
                  .onAppear { logoPulse = true }
              }

              Text(viewModelContainer.initStatusMessage)
                .scaledFont(size: OmiType.body, weight: .medium)
                .foregroundColor(OmiColors.textTertiary)

              ProgressView()
                .scaleEffect(0.8)
                .tint(OmiColors.accent.opacity(0.6))
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(OmiColors.backgroundPrimary)
            .transition(.opacity.animation(OmiMotion.gated(.easeOut(duration: 0.3))))
          }

          if let policy = updatePolicyManager.visiblePolicy, policy.isRequired {
            Color.black.opacity(0.62)
              .ignoresSafeArea()
              .zIndex(20)
            DesktopRequiredUpdatePrompt(
              policy: policy,
              onDownload: { updatePolicyManager.openDownload(policy) }
            )
            .zIndex(21)
          }
        }
      }
    }
    .background(OmiColors.backgroundPrimary)
    .frame(minWidth: minimumWindowWidth, minHeight: minimumWindowHeight)
    .preferredColorScheme(.dark)
    .tint(OmiColors.accent)
    .onAppear {
      log(
        "DesktopHomeView: View appeared - isSignedIn=\(authState.isSignedIn), hasCompletedOnboarding=\(appState.hasCompletedOnboarding)"
      )
      // Force dark appearance and disable minSize computation on NSHostingView.
      // By default, every @Published change triggers
      // updateWindowContentSizeExtremaIfNecessary() → minSize() → sizeThatFits()
      // which traverses the ENTIRE view tree (~200 samples per window per trigger).
      // Removing .minSize from sizingOptions prevents this full-tree traversal.
      // The window's min size is enforced at the AppKit level instead.
      enforceMainWindowMinimumSize()
      // SwiftUI's automatic resizability later re-derives the window min from content
      // extrema and resets our pin, after which the window can be dragged small enough
      // to hide content. Re-pin on every live resize so AppKit keeps clamping the drag.
      installMinimumSizeGuardIfNeeded()
      // Redirect if current page isn't visible at current tier
      redirectIfPageHidden()
      reportAutomationState()
      handleAutomationPresentationReadinessChange(viewModelContainer.isInitialLoadComplete)
    }
    .onChange(of: currentTierLevel) { _, _ in
      redirectIfPageHidden()
      reportAutomationState()
    }
    .onChange(of: selectedIndex) { _, _ in
      // Page nav recreates the content hosting view with default sizingOptions, which
      // resets the window min — re-pin + re-disable to hold the minimum.
      enforceMainWindowMinimumSize()
      reportAutomationState()
    }
    .onChange(of: automationPresentationCoordinator.activeCommand?.generation) { _, _ in
      guard
        let command = automationPresentationReadinessGate.commandForConsumption(
          automationPresentationCoordinator.activeCommand)
      else { return }
      handleAutomationPresentationCommand(command)
    }
    .onChange(of: viewModelContainer.isInitialLoadComplete) { _, isReady in
      handleAutomationPresentationReadinessChange(isReady)
    }
    .onChange(of: selectedSettingsSection) { _, _ in reportAutomationState() }
    .onChange(of: highlightedSettingId) { _, _ in reportAutomationState() }
    .onChange(of: authState.isSignedIn) { _, _ in reportAutomationState() }
    .onChange(of: authState.isRestoringAuth) { _, _ in reportAutomationState() }
    .onChange(of: appState.hasCompletedOnboarding) { _, _ in reportAutomationState() }
    .onReceive(NotificationCenter.default.publisher(for: .runtimeOwnerDidChange)) { _ in
      chatFirstCapabilitySample.ownerDidChange(to: RuntimeOwnerIdentity.currentOwnerId())
      // The provider's owner-bound gate rejects the previous sample for this
      // owner; no replacement sample is persisted or inferred locally.
      reportAutomationState()
    }
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
      enforceMainWindowMinimumSize()
      reportAutomationState()
    }
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didResignActiveNotification)) { _ in
      reportAutomationState()
    }
    .onReceive(NotificationCenter.default.publisher(for: .desktopAutomationNavigateRequested)) {
      notification in
      handleAutomationNavigation(notification)
    }
  }

  private func enforceMainWindowMinimumSize() {
    let minimumContentSize = NSSize(width: minimumWindowWidth, height: minimumWindowHeight)
    DispatchQueue.main.async {
      for window in NSApp.windows where window.title.lowercased().hasPrefix("omi") {
        window.appearance = NSAppearance(named: .darkAqua)
        window.contentMinSize = minimumContentSize
        window.minSize = window.frameRect(forContentRect: NSRect(origin: .zero, size: minimumContentSize)).size

        let currentContentSize = window.contentView?.bounds.size ?? window.contentLayoutRect.size
        let widthDelta = max(0, minimumContentSize.width - currentContentSize.width)
        let heightDelta = max(0, minimumContentSize.height - currentContentSize.height)
        if widthDelta > 0 || heightDelta > 0 {
          var frame = window.frame
          frame.size.width += widthDelta
          frame.size.height += heightDelta
          frame.origin.y -= heightDelta
          window.setFrame(frame, display: true, animate: false)
        }

        // Remove .minSize from hosting view's sizingOptions.
        // Search contentView itself + all descendants.
        Self.disableMinSizeComputation(in: window)
      }
    }
  }

  /// Re-pin the window minimum on every live resize. SwiftUI's `.automatic` window
  /// resizability periodically recomputes content-size extrema and overwrites the
  /// one-shot pin from `enforceMainWindowMinimumSize()`, after which the window can be
  /// dragged small enough to hide content. Observing `didResize` and re-pinning keeps
  /// AppKit clamping the live drag at the minimum. Installed once for the app's lifetime.
  private static var minimumSizeGuardInstalled = false
  private func installMinimumSizeGuardIfNeeded() {
    guard !Self.minimumSizeGuardInstalled else { return }
    Self.minimumSizeGuardInstalled = true
    let minimumContentSize = NSSize(width: minimumWindowWidth, height: minimumWindowHeight)
    NotificationCenter.default.addObserver(
      forName: NSWindow.didResizeNotification, object: nil, queue: .main
    ) { notification in
      let objectBox = AnySendableBox(value: notification.object)
      MainActor.assumeIsolated {
        guard let window = objectBox.value as? NSWindow,
          window.title.lowercased().hasPrefix("omi")
        else { return }
        let frameMin = window.frameRect(
          forContentRect: NSRect(origin: .zero, size: minimumContentSize)
        ).size
        if window.contentMinSize != minimumContentSize { window.contentMinSize = minimumContentSize }
        if window.minSize != frameMin { window.minSize = frameMin }
      }
    }
  }

  /// Recursively find all NSHostingViews in a window and set sizingOptions to [],
  /// disabling ALL size computations to prevent full-tree sizeThatFits() traversals.
  /// Window min/max sizes are enforced at the AppKit level via NSWindow.minSize instead.
  /// NOTE: ClickThroughHostingView is excluded because it wraps the sidebar and needs
  /// intrinsicContentSize for SwiftUI's .fixedSize() layout to compute the correct width.
  private static func disableMinSizeComputation(in window: NSWindow) {
    func visit(_ view: NSView) {
      if let hosting = view as? any HostingSizingConfigurable {
        // Skip ClickThroughHostingView — it's an NSViewRepresentable boundary
        // that needs intrinsicContentSize for the sidebar's .fixedSize() to work.
        let typeName = String(describing: type(of: view))
        guard !typeName.contains("ClickThroughHostingView") else {
          // Still visit children
          for subview in view.subviews { visit(subview) }
          return
        }
        let before = hosting.sizingOptions
        if before != [] {
          hosting.sizingOptions = []
        }
      }
      for subview in view.subviews {
        visit(subview)
      }
    }
    if let contentView = window.contentView {
      visit(contentView)
    }
  }

  /// Redirect to conversations if current page isn't visible at the current tier level
  private func redirectIfPageHidden() {
    guard !usesChatFirstShell else { return }
    // Tier 0 or tier 6+ shows everything — no redirect needed
    guard currentTierLevel > 0 && currentTierLevel < 6 else { return }
    // Don't redirect from settings/permissions/help pages
    let nonMainPages: Set<Int> = [
      SidebarNavItem.settings.rawValue, SidebarNavItem.permissions.rawValue,
      SidebarNavItem.help.rawValue,
    ]
    guard !nonMainPages.contains(selectedIndex) else { return }

    var visibleRawValues: Set<Int> = [
      SidebarNavItem.dashboard.rawValue, SidebarNavItem.rewind.rawValue,
    ]
    if currentTierLevel >= 2 { visibleRawValues.insert(SidebarNavItem.memories.rawValue) }
    if currentTierLevel >= 3 { visibleRawValues.insert(SidebarNavItem.tasks.rawValue) }
    // Conversations replaced Chat in the sidebar; tier 1 unlocks it.
    if currentTierLevel >= 1 { visibleRawValues.insert(SidebarNavItem.conversations.rawValue) }

    if !visibleRawValues.contains(selectedIndex) {
      selectedIndex = SidebarNavItem.dashboard.rawValue
    }
  }

  /// Whether to hide the sidebar (rewind mode)
  private var hideSidebar: Bool {
    OMIApp.launchMode == .rewind
  }

  private var showsPrimarySidebar: Bool {
    !usesChatFirstShell && useLegacyHomeDesign && !hideSidebar
  }

  private var currentAppStateLabel: String {
    if authState.isRestoringAuth { return "restoring_auth" }
    if authState.sessionPhase == .recoveryRequired { return "auth_recovery" }
    if !authState.isSignedIn { return "signed_out" }
    if !appState.hasCompletedOnboarding { return "onboarding" }
    return "main"
  }

  private func reportAutomationState() {
    guard DesktopAutomationLaunchOptions.isEnabled else { return }

    let currentWindow = NSApp.windows.first(where: {
      $0.title.lowercased().hasPrefix("omi") && $0.isVisible
    })
    let onDashboard = selectedIndex == SidebarNavItem.dashboard.rawValue
    let priorHomeMode = DesktopAutomationStateStore.shared.current().homeMode
    let chatFirstRoute = usesChatFirstShell ? chatFirstNavigation.route : nil
    let snapshot = DesktopAutomationSnapshot(
      bridgeEnabled: true,
      bridgePort: DesktopAutomationLaunchOptions.port,
      bundleIdentifier: Bundle.main.bundleIdentifier ?? "unknown",
      appState: currentAppStateLabel,
      selectedTab: chatFirstRoute?.title ?? SidebarNavItem(rawValue: selectedIndex)?.title,
      selectedTabIndex: usesChatFirstShell ? nil : selectedIndex,
      selectedSettingsSection: usesChatFirstShell
        ? (chatFirstRoute == .more(.settings) ? selectedSettingsSection.rawValue : nil)
        : (isInSettings ? selectedSettingsSection.rawValue : nil),
      highlightedSettingId: highlightedSettingId,
      usesLegacyHomeDesign: !usesChatFirstShell && useLegacyHomeDesign,
      homeMode: !usesChatFirstShell && onDashboard && !useLegacyHomeDesign ? (priorHomeMode ?? "hub") : nil,
      shellVariant: chatFirstCapabilitySample.variant.stableName,
      chatFirstRoute: chatFirstRoute?.stableName,
      visibleChatFirstRoute: usesChatFirstShell ? chatFirstNavigation.visibleRoute?.stableName : nil,
      pendingFocusKind: chatFirstNavigation.pendingFocus?.stableName,
      acknowledgedFocusKind: chatFirstNavigation.lastAcknowledgedFocusKind,
      focusedEntityID: chatFirstNavigation.focusedEntityID,
      isFocusedEntityAcknowledged: chatFirstNavigation.isFocusedEntityAcknowledged,
      showsPrimarySidebar: showsPrimarySidebar,
      isSidebarCollapsed: usesChatFirstShell
        ? chatFirstNavigation.isSidebarCollapsed : isSidebarCollapsed,
      hasCompletedOnboarding: appState.hasCompletedOnboarding,
      isSignedIn: authState.isSignedIn,
      isRestoringAuth: authState.isRestoringAuth,
      isAppActive: NSApp.isActive,
      mainWindowTitle: currentWindow?.title,
      floatingBarVisible: FloatingControlBarManager.shared.automationState.isVisible,
      askOmiOpen: FloatingControlBarManager.shared.automationState.isAskOmiOpen,
      askOmiFocused: FloatingControlBarManager.shared.automationState.isAskOmiFocused,
      floatingBarFrame: FloatingControlBarManager.shared.automationState.frame,
      floatingBarVoiceListening: FloatingControlBarManager.shared.automationState.isVoiceListening,
      floatingBarVoiceResponseActive: FloatingControlBarManager.shared.automationState.isVoiceResponseActive,
      floatingBarUsesNotchIsland: FloatingControlBarManager.shared.automationState.usesNotchIsland,
      updatedAt: ISO8601DateFormatter().string(from: Date())
    )

    DesktopAutomationStateStore.shared.update(snapshot)
  }

  private func handleAutomationNavigation(_ notification: Notification) {
    guard DesktopAutomationLaunchOptions.isEnabled else { return }
    guard let target = notification.userInfo?["target"] as? String else { return }

    let settingsSectionRaw = notification.userInfo?["settingsSection"] as? String
    let settingId = notification.userInfo?["highlightedSettingId"] as? String
    let activateApp = notification.userInfo?["activateApp"] as? Bool ?? true

    if activateApp {
      NSApp.activate()
      if let window = NSApp.windows.first(where: { $0.title.lowercased().hasPrefix("omi") }) {
        window.makeKeyAndOrderFront(nil)
      }
    }

    if let sectionRaw = settingsSectionRaw {
      // Tolerant match (SET-01): omi-ctl sends the caller's casing verbatim (docs use
      // lowercase, raw values are Title Case), so a strict rawValue init silently left
      // navigation on General for every sub-section command.
      if let section = SettingsContentView.SettingsSection.automationMatch(sectionRaw) {
        selectedSettingsSection = section
      } else {
        log("AutomationNavigation: unknown settings section '\(sectionRaw)'")
      }
    }
    highlightedSettingId = settingId

    if usesChatFirstShell,
      let route = ChatFirstRoute.primaryAutomationDestination(named: target)
    {
      chatFirstNavigation.selectPrimary(route)
    } else if let item = resolvedAutomationTarget(target) {
      navigateToLegacyDestination(item)
    }

    reportAutomationState()
  }

  private func handleAutomationPresentationCommand(
    _ command: DesktopAutomationPresentationCommand
  ) {
    NSApp.activate()
    if let window = NSApp.windows.first(where: { $0.title.lowercased().hasPrefix("omi") }) {
      window.makeKeyAndOrderFront(nil)
    }
    navigateToLegacyDestination(.apps)
    reportAutomationState()
  }

  private func handleAutomationPresentationReadinessChange(_ isReady: Bool) {
    guard
      let command = automationPresentationReadinessGate.transition(
        to: isReady,
        activeCommand: automationPresentationCoordinator.activeCommand)
    else { return }
    handleAutomationPresentationCommand(command)
  }

  private func resolvedAutomationTarget(_ target: String) -> SidebarNavItem? {
    let normalized = target.lowercased().replacingOccurrences(of: "-", with: "_")
    switch normalized {
    case "dashboard", "home":
      return .dashboard
    case "conversations":
      return .conversations
    case "chat":
      return .chat
    case "memories":
      return .memories
    case "tasks":
      return .tasks
    case "focus":
      return .focus
    case "insight":
      return .insight
    case "rewind":
      return .rewind
    case "apps", "integrations":
      return .apps
    case "settings":
      return .settings
    case "permissions":
      return .permissions
    case "help":
      return .help
    default:
      return nil
    }
  }

  /// Update store auto-refresh based on which page is visible
  /// On launch, if the user quit with the task chat panel open, macOS restores the
  /// expanded window frame but the chat panel itself is not shown. Shrink the window
  /// back to its pre-chat width so the layout isn't unexpectedly wide.
  private func restorePreChatWindowWidth() {
    let key = "tasksPreChatWindowWidth"
    let saved = UserDefaults.standard.double(forKey: key)
    guard saved > 0 else { return }
    // Reset the persisted value immediately so TasksPage won't double-shrink
    UserDefaults.standard.set(Double(0), forKey: key)
    // Delay slightly so the window is fully visible
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
      guard let window = NSApp.windows.first(where: { $0.title.hasPrefix("Omi") && $0.isVisible })
      else { return }
      var frame = window.frame
      frame.size.width = saved
      window.setFrame(frame, display: true)
    }
  }

  private func resetSessionScopedStartupWarmups(preserveCrispReadState: Bool) {
    viewModelContainer.resetStartupState()
    didScheduleConversationWarmup = false
    didScheduleAgentVMProvisioning = false
    proactiveMonitoringStartGate.finishAttempt()
    initialFileIndexingBackfill.releaseReservation()
    CrispManager.shared.stop(preserveReadState: preserveCrispReadState)
  }

  private func scheduleAgentVMProvisioning() {
    guard !didScheduleAgentVMProvisioning else { return }
    didScheduleAgentVMProvisioning = true

    let scheduled = viewModelContainer.scheduleSessionWarmup(
      id: .agentVMProvisioning,
      delay: StartupWarmupPolicy.agentVMProvisioningDelay,
      onCancel: { didScheduleAgentVMProvisioning = false }
    ) {
      await AgentVMService.shared.ensureProvisioned()
    }
    if !scheduled { didScheduleAgentVMProvisioning = false }
  }

  private func scheduleConversationWarmup() {
    guard !didScheduleConversationWarmup else { return }
    didScheduleConversationWarmup = true

    let scheduled = viewModelContainer.scheduleSessionWarmup(
      id: .conversationWarmup,
      delay: StartupWarmupPolicy.conversationWarmupDelay,
      onCancel: { didScheduleConversationWarmup = false }
    ) {
      async let conversations: Void = loadConversationsIfNeeded()
      async let folders: Void = loadFoldersIfNeeded()
      _ = await (conversations, folders)
    }
    if !scheduled { didScheduleConversationWarmup = false }
  }

  private func loadConversationsIfNeeded() async {
    guard appState.conversations.isEmpty else { return }
    await appState.loadConversations()
  }

  private func loadFoldersIfNeeded() async {
    guard appState.folders.isEmpty else { return }
    await appState.loadFolders()
  }

  private func scheduleInitialFileIndexing() {
    guard
      initialFileIndexingBackfill.reserveIfNeeded(
        hasCompletedBackfill: UserDefaults.standard.bool(forKey: "hasCompletedFileIndexing"))
    else { return }

    let sessionScope = StartupWarmupSessionScope(
      userId: UserDefaults.standard.string(forKey: "auth_userId"))
    let scheduled = viewModelContainer.scheduleSessionWarmup(
      id: .initialFileIndexing,
      delay: StartupWarmupPolicy.initialFileIndexingDelay,
      onCancel: { initialFileIndexingBackfill.releaseReservation() }
    ) {
      log("DesktopHomeView: Running delayed background file scan for existing user")
      await FileIndexerService.shared.backgroundRescan()
      guard !Task.isCancelled,
        sessionScope.matches(
          currentUserId: UserDefaults.standard.string(forKey: "auth_userId"),
          isSignedIn: AuthState.shared.isSignedIn)
      else {
        initialFileIndexingBackfill.releaseReservation()
        return
      }
      initialFileIndexingBackfill.markScanCompleted()
      if initialFileIndexingBackfill.shouldMarkComplete {
        UserDefaults.standard.set(true, forKey: "hasCompletedFileIndexing")
        log(
          "DesktopHomeView: Marked existing-user file indexing backfill complete after background scan returned"
        )
      }
    }
    if !scheduled { initialFileIndexingBackfill.releaseReservation() }
  }

  private func scheduleProactiveMonitoringStart(reason: String) {
    guard proactiveMonitoringStartGate.reserve() else { return }

    let delay = StartupWarmupPolicy.remainingProactiveAssistantsStartDelay(
      elapsedSinceLaunch: Date().timeIntervalSince(proactiveMonitoringWarmupAnchor))
    log(
      "DesktopHomeView: Scheduling screen analysis start in \(String(format: "%.1f", delay))s (\(reason))"
    )
    let scheduled = viewModelContainer.scheduleSessionWarmup(
      id: .proactiveAssistantsStart,
      delay: delay,
      onCancel: { proactiveMonitoringStartGate.finishAttempt() }
    ) {
      let plugin = ProactiveAssistantsPlugin.shared
      guard AssistantSettings.shared.screenAnalysisEnabled, !plugin.isMonitoring else {
        proactiveMonitoringStartGate.finishAttempt()
        return
      }
      guard APIKeyService.keysAvailable else {
        proactiveMonitoringStartGate.finishAttempt()
        log("DesktopHomeView: Screen analysis still deferred after \(reason) — API keys not yet loaded")
        return
      }

      plugin.startMonitoring { success, error in
        Task { @MainActor in
          proactiveMonitoringStartGate.finishAttempt()
          if success {
            log("DesktopHomeView: Screen analysis started (\(reason), delayed)")
          } else {
            log(
              "DesktopHomeView: Screen analysis failed to start (\(reason)): \(error ?? "unknown") — setting remains enabled for next launch"
            )
          }
        }
      }
    }
    if !scheduled { proactiveMonitoringStartGate.finishAttempt() }
  }

  private func updateStoreActivity(for index: Int) {
    viewModelContainer.tasksStore.isActive =
      index == SidebarNavItem.dashboard.rawValue || index == SidebarNavItem.tasks.rawValue
    viewModelContainer.memoriesViewModel.isActive =
      index == SidebarNavItem.memories.rawValue
  }

  private var usesChatFirstShell: Bool {
    if case .chatFirst = chatFirstCapabilitySample.variant { return true }
    return false
  }

  private func updateStoreActivityForCurrentShell() {
    guard usesChatFirstShell else {
      updateStoreActivity(for: selectedIndex)
      return
    }
    viewModelContainer.tasksStore.isActive =
      chatFirstNavigation.route == .tasks || chatFirstNavigation.route == .more(.dashboard)
    viewModelContainer.memoriesViewModel.isActive = chatFirstNavigation.route == .memories
  }

  /// One fresh server read decides both the shell and the local runtime
  /// projection. A failed response, missing owner, stale auth snapshot, or
  /// owner change resolves legacy; there is no cached local enablement.
  private func resolveChatFirstCapabilityIfNeeded() async {
    guard case .unresolved = chatFirstCapabilitySample.variant else { return }
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId(),
      let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
    else {
      chatFirstCapabilitySample.resolve(
        control: nil,
        requestedOwnerID: nil,
        ownerIsStillCurrent: false
      )
      _ = viewModelContainer.chatProvider.configureChatFirstMainChatCapability(nil)
      AnalyticsManager.shared.chatFirst(
        .capabilityResolution(
          outcome: .unavailable,
          generationBucket: .none,
          errorClass: .ownerChanged
        )
      )
      reportAutomationState()
      return
    }

    var capabilityErrorClass: ChatFirstAnalyticsEvent.CapabilityErrorClass = .none
    do {
      let control = try await APIClient.shared.getCandidateWorkflowControl(
        expectedOwnerId: ownerID,
        authorizationSnapshot: authorization
      )
      let current =
        RuntimeOwnerIdentity.isAuthorizationCurrent(authorization)
        && RuntimeOwnerIdentity.currentOwnerId() == ownerID
      chatFirstCapabilitySample.resolve(
        control: control,
        requestedOwnerID: ownerID,
        ownerIsStillCurrent: current
      )
    } catch {
      let current =
        RuntimeOwnerIdentity.isAuthorizationCurrent(authorization)
        && RuntimeOwnerIdentity.currentOwnerId() == ownerID
      chatFirstCapabilitySample.resolve(
        control: nil,
        requestedOwnerID: ownerID,
        ownerIsStillCurrent: current
      )
      capabilityErrorClass = .unavailable
      log("DesktopHomeView: chat-first control unavailable; using legacy shell")
    }

    let projectionConfigured = viewModelContainer.chatProvider.configureChatFirstMainChatCapability(
      chatFirstCapabilitySample.variant.projection
    )
    if !projectionConfigured {
      // A pre-existing Main Chat session cannot be retroactively upgraded with
      // dynamic tools. Keep this launch on the byte-equivalent legacy path.
      chatFirstCapabilitySample.failClosed()
      capabilityErrorClass = .projectionRejected
      log("DesktopHomeView: chat-first projection handoff rejected; using legacy shell")
    }
    let projection = chatFirstCapabilitySample.variant.projection
    let capabilityOutcome: ChatFirstAnalyticsEvent.CapabilityOutcome
    if capabilityErrorClass == .projectionRejected {
      capabilityOutcome = .projectionRejected
    } else if capabilityErrorClass == .unavailable {
      capabilityOutcome = .unavailable
    } else if projection != nil {
      capabilityOutcome = .enabled
    } else {
      capabilityOutcome = .disabled
    }
    AnalyticsManager.shared.chatFirst(
      .capabilityResolution(
        outcome: capabilityOutcome,
        generationBucket: .bucket(for: projection?.controlGeneration),
        errorClass: capabilityErrorClass
      )
    )
    reportAutomationState()
  }

  private func navigateAfterOnboarding() {
    if usesChatFirstShell {
      chatFirstNavigation.selectPrimary(.chat)
      log("DesktopHomeView: Onboarding just completed — opening Chat")
    } else {
      selectedIndex = SidebarNavItem.dashboard.rawValue
      log("DesktopHomeView: Onboarding just completed — navigating to Dashboard")
    }
  }

  /// Existing menu, keyboard, and automation callers retain their legacy
  /// names. This is the sole root adapter between those callers and typed
  /// cohort navigation.
  private func navigateToLegacyDestination(_ item: SidebarNavItem) {
    if usesChatFirstShell {
      chatFirstNavigation.selectLegacyDestination(item)
    } else {
      selectedIndex = item.rawValue
    }
  }

  private var mainContent: some View {
    mainContentWithLifecycle(
      mainContentWithNotifications(
        mainContentWithOverlays(shellContent)
      )
    )
  }

  /// Keep the type checker from attempting to infer every shell, overlay, and
  /// event subscription in one expression. The functions deliberately retain
  /// the existing modifier order; they are only compile-time seams.
  private func mainContentWithOverlays<Content: View>(_ content: Content) -> some View {
    content
      .overlay {
        // Goal completion celebration overlay
        GoalCelebrationView()
      }
      .overlay {
        if showTryAskingPopup {
          let suggestions = PostOnboardingPromptSuggestions.suggestions()
          if !suggestions.isEmpty {
            TryAskingPopupView(
              suggestions: suggestions,
              onAsk: { suggestion in
                showTryAskingPopup = false
                PostOnboardingPromptSuggestions.shouldShowPopup = false
                FloatingControlBarManager.shared.openAIInputWithQuery(suggestion)
              },
              onDismiss: {
                showTryAskingPopup = false
                PostOnboardingPromptSuggestions.shouldShowPopup = false
                PostOnboardingPromptSuggestions.isDismissed = true
              }
            )
          }
        }
      }
  }

  private func mainContentWithNotifications<Content: View>(_ content: Content) -> some View {
    content
      .onReceive(NotificationCenter.default.publisher(for: .showTryAskingPopup)) { _ in
        showTryAskingPopup = true
      }
      .onReceive(NotificationCenter.default.publisher(for: .navigateToRewindSettings)) { _ in
        selectedSettingsSection = .rewind
        navigateToLegacyDestination(.settings)
      }
      .onReceive(NotificationCenter.default.publisher(for: .navigateToDeviceSettings)) { _ in
        if let url = URL(string: "https://www.omi.me") {
          NSWorkspace.shared.open(url)
        }
      }
      .onReceive(NotificationCenter.default.publisher(for: .navigateToTaskSettings)) { _ in
        selectedSettingsSection = .advanced
        navigateToLegacyDestination(.settings)
      }
      .onReceive(NotificationCenter.default.publisher(for: .navigateToFloatingBarSettings)) { _ in
        selectedSettingsSection = .floatingBar
        navigateToLegacyDestination(.settings)
      }
      .onReceive(NotificationCenter.default.publisher(for: .navigateToAIChatSettings)) { _ in
        selectedSettingsSection = .advanced
        navigateToLegacyDestination(.settings)
      }
      .onReceive(NotificationCenter.default.publisher(for: .navigateToRewind)) { _ in
        log("DesktopHomeView: Received navigateToRewind notification")
        navigateToLegacyDestination(.rewind)
      }
      .onReceive(NotificationCenter.default.publisher(for: .navigateToRewindNotes)) { _ in
        navigateToLegacyDestination(.rewind)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
          NotificationCenter.default.post(name: .expandRewindTranscript, object: nil)
        }
      }
      .onReceive(NotificationCenter.default.publisher(for: .navigateToChat)) { _ in
        if usesChatFirstShell {
          chatFirstNavigation.selectPrimary(.chat)
        } else {
          // Legacy Home owns the historic Chat notification contract.
          selectedIndex = SidebarNavItem.dashboard.rawValue
        }
      }
      .onReceive(NotificationCenter.default.publisher(for: .navigateToTasks)) { _ in
        navigateToLegacyDestination(.tasks)
      }
      .onReceive(NotificationCenter.default.publisher(for: .navigateToSidebarItem)) { notification in
        if let rawValue = notification.userInfo?["rawValue"] as? Int,
          let item = SidebarNavItem(rawValue: rawValue)
        {
          navigateToLegacyDestination(item)
        }
      }
  }

  private func mainContentWithLifecycle<Content: View>(_ content: Content) -> some View {
    content
      .onChange(of: selectedIndex) { oldValue, newValue in
        if newValue == SidebarNavItem.settings.rawValue
          && oldValue != SidebarNavItem.settings.rawValue
        {
          previousIndexBeforeSettings = oldValue
        }
        updateStoreActivity(for: newValue)
      }
      .onChange(of: chatFirstNavigation.route) { _, _ in
        updateStoreActivityForCurrentShell()
        reportAutomationState()
      }
      .onChange(of: chatFirstNavigation.visibleRoute) { _, _ in reportAutomationState() }
      .onChange(of: chatFirstNavigation.isSidebarCollapsed) { _, _ in reportAutomationState() }
      .onChange(of: useLegacyHomeDesign) { _, newValue in
        OmiMotion.withGated(.easeInOut(duration: 0.2)) {
          isSidebarCollapsed = !newValue
        }
      }
      .onAppear {
        if case .legacy = chatFirstCapabilitySample.variant {
          isSidebarCollapsed = !useLegacyHomeDesign
        }
        updateStoreActivityForCurrentShell()
        restorePreChatWindowWidth()
      }
  }

  /// Keep the legacy HStack out of the chat-first branch's SwiftUI generic
  /// expression. The runtime choice is already immutable for this app session;
  /// this is only an erased rendering boundary, not a second state owner.
  private var shellContent: AnyView {
    if case .chatFirst(let capability) = chatFirstCapabilitySample.variant {
      return AnyView(
        ChatFirstShell(
          navigation: chatFirstNavigation,
          appState: appState,
          viewModelContainer: viewModelContainer,
          capability: capability,
          selectedSettingsSection: $selectedSettingsSection,
          highlightedSettingID: $highlightedSettingId
        )
      )
    }
    return AnyView(legacyMainContent)
  }

  private var legacyMainContent: some View {
    HStack(spacing: 0) {
      // Sidebar slot: settings sidebar overlays main sidebar
      // IMPORTANT: SidebarView is kept alive (but hidden) when in settings to prevent
      // EXC_BAD_ACCESS crash in SwiftUI's tooltip system. When the view is conditionally
      // removed, its .help() tooltip graph nodes get invalidated, but the macOS tooltip
      // tracking system still tries to evaluate them during window key state changes.
      if isInSettings {
        ZStack {
          if showsPrimarySidebar {
            SidebarView(
              selectedIndex: $selectedIndex,
              isCollapsed: $isSidebarCollapsed,
              appState: appState
            )
            .opacity(0)
            .allowsHitTesting(false)
          }

          SettingsSidebar(
            selectedSection: $selectedSettingsSection,
            highlightedSettingId: $highlightedSettingId,
            onBack: {
              OmiMotion.withGated(Self.pageNavigationAnimation) {
                selectedIndex =
                  previousIndexBeforeSettings == SidebarNavItem.settings.rawValue
                  ? SidebarNavItem.dashboard.rawValue
                  : previousIndexBeforeSettings
              }
            }
          )
        }
        .fixedSize(horizontal: true, vertical: false)
        .clipped()
      } else if showsPrimarySidebar {
        ZStack {
          if showsPrimarySidebar {
            SidebarView(
              selectedIndex: $selectedIndex,
              isCollapsed: $isSidebarCollapsed,
              appState: appState
            )
            .opacity(isInSettings ? 0 : 1)
            .allowsHitTesting(!isInSettings)
          }

        }
        .fixedSize(horizontal: true, vertical: false)
        .clipped()
      }

      // Main content area with rounded container
      ZStack {
        // Content container background
        RoundedRectangle(cornerRadius: OmiChrome.windowRadius, style: .continuous)
          .fill(
            LinearGradient(
              colors: [
                OmiColors.backgroundSecondary.opacity(0.96),
                OmiColors.backgroundPrimary.opacity(0.96),
              ],
              startPoint: .topLeading,
              endPoint: .bottomTrailing
            )
          )
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.windowRadius, style: .continuous)
              .stroke(OmiColors.border.opacity(0.22), lineWidth: 1)
          )
          .shadow(color: .black.opacity(0.22), radius: 26, x: 0, y: 14)

        // Page content - switch recreates views on tab change
        // Extracted into a separate struct so that pages like TasksPage
        // are not re-rendered when AppState publishes unrelated changes.
        VStack(spacing: 0) {
          // Settings has its own Back affordance in SettingsSidebar, so skip the
          // redundant Home chrome there.
          if !useLegacyHomeDesign && selectedIndex != SidebarNavItem.dashboard.rawValue
            && !isInSettings
          {
            PageChromeBar(
              onHome: {
                selectedIndex = SidebarNavItem.dashboard.rawValue
              }
            )
            .padding(.horizontal, OmiSpacing.lg)
            .padding(.top, OmiSpacing.md)
            .padding(.bottom, OmiSpacing.xxs)
          }

          PageContentView(
            selectedIndex: selectedIndex,
            appState: appState,
            viewModelContainer: viewModelContainer,
            selectedSettingsSection: $selectedSettingsSection,
            highlightedSettingId: $highlightedSettingId,
            selectedTabIndex: $selectedIndex
          )
        }
        .onExitCommand {
          navigateHomeOnEscapeIfNeeded()
        }
        .clipShape(RoundedRectangle(cornerRadius: OmiChrome.windowRadius, style: .continuous))
      }
      .padding(OmiSpacing.md)
    }
  }

  private func navigateHomeOnEscapeIfNeeded() {
    if usesChatFirstShell {
      guard chatFirstNavigation.route != .chat else { return }
      OmiMotion.withGated(Self.pageNavigationAnimation) {
        chatFirstNavigation.selectPrimary(.chat)
      }
      return
    }
    guard !useLegacyHomeDesign else { return }
    guard let item = SidebarNavItem(rawValue: selectedIndex) else { return }
    guard [.conversations, .memories, .tasks, .rewind].contains(item) else { return }
    OmiMotion.withGated(Self.pageNavigationAnimation) {
      selectedIndex = SidebarNavItem.dashboard.rawValue
    }
  }
}

private struct ChatFirstCapabilityLoadingView: View {
  var body: some View {
    VStack(spacing: OmiSpacing.md) {
      ProgressView()
        .controlSize(.small)
      Text("Preparing Omi…")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundStyle(OmiColors.textSecondary)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(OmiColors.backgroundPrimary)
    .accessibilityElement(children: .combine)
    .accessibilityLabel("Preparing Omi")
  }
}

private struct PageChromeBar: View {
  let onHome: () -> Void

  var body: some View {
    HStack(spacing: OmiSpacing.sm) {
      PageChromeButton(title: "Home", systemImage: "house.fill", action: onHome)
      Spacer()
    }
    .frame(height: 34)
  }
}

private struct PageChromeButton: View {
  let title: String
  let systemImage: String
  let action: () -> Void
  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: systemImage)
          .scaledFont(size: OmiType.caption, weight: .semibold)
        Text(title)
          .scaledFont(size: OmiType.caption, weight: .semibold)
      }
      .foregroundStyle(isHovering ? OmiColors.textPrimary : OmiColors.textSecondary)
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.xs)
      .background(
        Capsule(style: .continuous)
          .fill(.ultraThinMaterial)
      )
      .overlay(
        Capsule(style: .continuous)
          .stroke(isHovering ? OmiColors.success.opacity(0.34) : OmiColors.border.opacity(0.4), lineWidth: 1)
      )
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .help(title)
    .accessibilityLabel(title)
  }
}

/// Isolated page content switch — does NOT observe AppState or ViewModelContainer
/// as @ObservedObject, so pages like TasksPage won't re-render when unrelated
/// AppState properties (conversations, permissions, etc.) change.
private struct PageContentView: View {
  let selectedIndex: Int
  let appState: AppState
  let viewModelContainer: ViewModelContainer
  @Binding var selectedSettingsSection: SettingsContentView.SettingsSection
  @Binding var highlightedSettingId: String?
  @Binding var selectedTabIndex: Int

  var body: some View {
    Group {
      switch selectedIndex {
      case 0:
        DashboardPage(
          viewModel: viewModelContainer.dashboardViewModel,
          homeStatusStore: viewModelContainer.homeStatusStore,
          appState: appState,
          appProvider: viewModelContainer.appProvider,
          chatProvider: viewModelContainer.chatProvider,
          memoriesViewModel: viewModelContainer.memoriesViewModel,
          taskChatCoordinator: viewModelContainer.taskChatCoordinator,
          selectedIndex: $selectedTabIndex)
      case 1:
        ConversationsPageHost(appState: appState)
      case 2:
        ChatPage(
          appProvider: viewModelContainer.appProvider, chatProvider: viewModelContainer.chatProvider
        )
      case 3:
        MemoriesPage(
          viewModel: viewModelContainer.memoriesViewModel,
          graphViewModel: viewModelContainer.memoryGraphViewModel)
      case 4:
        TasksPage(
          viewModel: viewModelContainer.tasksViewModel,
          chatCoordinator: viewModelContainer.taskChatCoordinator,
          chatProvider: viewModelContainer.chatProvider)
      case 5:
        FocusPage()
      case 6:
        InsightPage()
      case 7:
        RewindPage(appState: appState)
      case 8:
        AppsPage(
          appProvider: viewModelContainer.appProvider,
          appState: appState,
          connectorStatusStore: viewModelContainer.homeStatusStore.connectorStatusStore,
          handlesAutomationPresentations: viewModelContainer.isInitialLoadComplete)
      case 9:
        SettingsPage(
          appState: appState,
          selectedSection: $selectedSettingsSection,
          highlightedSettingId: $highlightedSettingId,
          chatProvider: viewModelContainer.chatProvider
        )
      case 10:
        PermissionsPage(appState: appState)
      case 12:
        HelpPage()
      default:
        DashboardPage(
          viewModel: viewModelContainer.dashboardViewModel,
          homeStatusStore: viewModelContainer.homeStatusStore,
          appState: appState,
          appProvider: viewModelContainer.appProvider,
          chatProvider: viewModelContainer.chatProvider,
          memoriesViewModel: viewModelContainer.memoriesViewModel,
          taskChatCoordinator: viewModelContainer.taskChatCoordinator,
          selectedIndex: $selectedTabIndex)
      }
    }
  }
}

/// Hosts the standalone Conversations page with its own selection state
/// so tapping a row navigates to the detail view.
private struct ConversationsPageHost: View {
  let appState: AppState
  @State private var selectedConversation: ServerConversation? = nil

  var body: some View {
    ConversationsPage(appState: appState, selectedConversation: $selectedConversation)
      // Owner fencing: an open detail view must not keep showing the previous
      // account's conversation after an in-place account switch.
      .onReceive(NotificationCenter.default.publisher(for: .runtimeOwnerDidChange)) { _ in
        selectedConversation = nil
      }
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    DesktopHomeView()
      .environmentObject(AppState())
  }
#endif
