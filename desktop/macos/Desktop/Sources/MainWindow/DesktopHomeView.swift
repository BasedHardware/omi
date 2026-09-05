import AppKit
import OmiTheme
import SwiftUI

private struct AnySendableBox: @unchecked Sendable { let value: Any? }

/// Decides whether a persisted capture intent needs its runtime service restored.
///
/// Intent is stored independently from the running services. A fresh launch and a
/// settings sync therefore both need to reconcile the two states instead of using
/// a one-time readiness check as the source of truth.
enum PersistedCaptureLaunchPolicy {
  static func shouldStartTranscription(
    intentEnabled: Bool,
    isTranscribing: Bool,
    micPermissionAuthorized: Bool
  ) -> Bool {
    // Restores run on launch/reactivation/key-load/sync; without a mic grant an
    // attempted start would raise the TCC sheet (the skip-mic loop) or bounce a
    // denied alert. The intent waits for an explicit Listen/Grant action instead.
    intentEnabled && !isTranscribing && micPermissionAuthorized
  }

  static func shouldStartScreenAnalysis(intentEnabled: Bool, isMonitoring: Bool) -> Bool {
    intentEnabled && !isMonitoring
  }
}

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
  private static let pageNavigationAnimation = Animation.easeOut(duration: 0.08)

  @EnvironmentObject private var appState: AppState
  @StateObject private var viewModelContainer = ViewModelContainer()
  /// The Chat-first shell owns typed navigation at the root, never through legacy
  /// sidebar indices. It persists only route/collapse state, not enrollment.
  /// The one navigation owner, shared with the auxiliary Chat surfaces (task
  /// panel, floating/notch) so a content block tapped there routes *this* shell
  /// rather than a second instance nothing renders.
  @ObservedObject private var chatFirstNavigation = ChatFirstShellNavigation.shared
  @ObservedObject private var authState = AuthState.shared
  @ObservedObject private var apiKeyService = APIKeyService.shared
  @ObservedObject private var updatePolicyManager = DesktopUpdatePolicyManager.shared
  @ObservedObject private var accountCutoverControl = AccountCutoverControlManager.shared
  @ObservedObject private var automationPresentationCoordinator =
    DesktopAutomationPresentationCoordinator.shared
  @AppStorage("currentTierLevel") private var currentTierLevel = 0
  @AppStorage("onboardingStep") private var onboardingStep = 0
  @AppStorage("onboardingFurthestStep") private var onboardingFurthestStep = 0
  @AppStorage("onboardingJustCompleted") private var onboardingJustCompleted = false
  @AppStorage(MemoryHubDestination.storageKey) private var memoryDestinationRawValue =
    MemoryHubDestination.memories.rawValue
  /// Reference instant for the top bar's "new since you were last here" counts —
  /// updated to now whenever Omi resigns front (see the didResignActive handler).
  @AppStorage("topBarNewSince") private var topBarNewSinceRaw: Double = 0

  // Settings sidebar state
  @State private var selectedSettingsSection: SettingsContentView.SettingsSection = .general
  @State private var highlightedSettingId: String? = nil
  @State private var showTryAskingPopup = false
  @State private var logoPulse = false
  @State private var lastActivationRefresh = Date.distantPast
  @State private var didScheduleAgentVMProvisioning = false
  @State private var proactiveMonitoringStartGate = RetryableDelayedStartGate()
  @State private var isWaitingForScreenAnalysisKeys = false
  // Anchor for the proactive-monitoring warmup budget. Captured at view
  // creation (≈ launch) so the delay is spent once per session, not once per
  // trigger — see StartupWarmupPolicy.remainingProactiveAssistantsStartDelay.
  @State private var proactiveMonitoringWarmupAnchor = Date()
  @State private var didScheduleConversationWarmup = false
  @State private var initialFileIndexingBackfill = DelayedFileIndexingBackfillState()
  @State private var automationPresentationReadinessGate =
    DesktopAutomationPresentationReadinessGate()
  /// Server-authoritative capability for the one shell. It never decides which
  /// shell mounts — only whether the capability-gated kernel features engage.
  @State private var chatFirstCapability = ChatFirstCapabilitySample()

  // Pre-loaded hero logo to avoid NSImage init crashes during SwiftUI body evaluation
  private static let heroLogoImage: NSImage? = {
    guard let url = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
      let data = try? Data(contentsOf: url)
    else { return nil }
    return NSImage(data: data)
  }()

  private var shouldShowAuthEntryShell: Bool {
    authState.isRestoringAuth || authState.sessionPhase == .recoveryRequired || !authState.isSignedIn
      || !hasCompletedOnboardingAtAuthorityRead
  }

  @ViewBuilder
  private var authEntryShell: some View {
    if authState.isRestoringAuth {
      TransparentWindowStatusPanel {
        VStack(spacing: OmiSpacing.md) {
          ProgressView()
            .controlSize(.small)
            .tint(Ink.secondary)
          Text("Restoring your session…")
            .inkStyle(.prose, color: Ink.secondary)
        }
      }
      .onAppear {
        log("DesktopHomeView: Showing auth loading splash")
      }
    } else if authState.sessionPhase == .recoveryRequired {
      SessionRecoveryView()
        .onAppear {
          log("DesktopHomeView: Showing recoverable auth state")
        }
    } else if !authState.isSignedIn {
      SignInView(authState: authState)
        .onAppear {
          log("DesktopHomeView: Showing SignInView (not signed in)")
        }
    } else if shouldSkipOnboarding() {
      TransparentWindowStatusPanel {
        VStack(spacing: OmiSpacing.md) {
          ProgressView()
            .controlSize(.small)
            .tint(Ink.secondary)
          Text("Finishing setup…")
            .inkStyle(.prose, color: Ink.secondary)
        }
      }
      .onAppear {
        log("DesktopHomeView: --skip-onboarding flag detected, skipping onboarding")
        appState.hasCompletedOnboarding = true
      }
    } else {
      SBOnboardingView(
        appState: appState,
        chatProvider: viewModelContainer.chatProvider,
        importConnectorStatusStore: viewModelContainer.homeStatusStore.connectorStatusStore,
        onComplete: nil
      )
      .onAppear {
        log("DesktopHomeView: Showing SBOnboardingView (signed in, not onboarded)")
      }
    }
  }

  // State 3: Signed in and onboarded.
  private var mainContentPresentation: some View {
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
  }

  private var mainContentStartupLifecycle: some View {
    mainContentPresentation
      .onReceive(NotificationCenter.default.publisher(for: .showUsageLimitPopup)) { notification in
        let reason = notification.userInfo?["reason"] as? String ?? ""
        appState.triggerUsageLimitPopup(reason: reason)
      }
      .onAppear {
        log("DesktopHomeView: Showing mainContent (signed in and onboarded)")

        // The first-use popup is armed by the same guidance policy for every
        // account now that there is one shell.
        if PostOnboardingPromptSuggestions.shouldArmPopup() {
          showTryAskingPopup = true
        }
        updatePolicyManager.refresh(force: true)
        // Permissions and update policy remain reachable while cutover fences
        // product traffic.
        appState.checkAllPermissions()
      }
      .task(id: accountCutoverControl.productShellAdmissionToken) {
        await DesktopHomeSignedInStartup.runProductServicesIfAdmitted(
          appState: appState,
          chatProvider: viewModelContainer.chatProvider,
          scheduleInitialFileIndexing: scheduleInitialFileIndexing,
          restorePersistedCaptureServices: restorePersistedCaptureServices(reason:)
        )
        await DesktopHomeSignedInStartup.loadDataIfAdmitted(
          loadAllData: { await viewModelContainer.loadAllData() },
          scheduleConversationWarmup: scheduleConversationWarmup,
          scheduleAgentVMProvisioning: scheduleAgentVMProvisioning
        )
      }
      // Refresh conversations when app becomes active (e.g. switching back from another app)
      .onReceive(
        NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)
      ) { _ in
        updatePolicyManager.refresh()
        guard AccountCutoverControlManager.shared.isProductShellAdmitted else { return }
        // Cooldown: only refresh conversations if last activation was 60+ seconds ago
        let now = Date()
        if PollingConfig.shouldAllowActivationRefresh(now: now, lastRefresh: lastActivationRefresh) {
          lastActivationRefresh = now
          Task { await appState.refreshConversations() }
        }
        // Reconcile persisted intent after returning from System Settings or
        // after a runtime service stopped while the app was inactive.
        restorePersistedCaptureServices(reason: "app active")
      }
      .onChange(of: apiKeyService.isLoaded) { _, loaded in
        guard loaded, AccountCutoverControlManager.shared.isProductShellAdmitted else { return }
        log("DesktopHomeView: API keys loaded — retrying deferred services")
        restorePersistedCaptureServices(reason: "key load")
      }
      .onReceive(NotificationCenter.default.publisher(for: .assistantSettingsDidSyncFromServer)) { _ in
        guard AccountCutoverControlManager.shared.isProductShellAdmitted else { return }
        reconcileCaptureServicesAfterSettingsSync()
      }
      // Cmd+R: refresh all data (conversations, chat, tasks, memories)
      .onReceive(NotificationCenter.default.publisher(for: .refreshAllData)) { _ in
        guard AccountCutoverControlManager.shared.isProductShellAdmitted else { return }
        Task { await appState.refreshConversations() }
      }
  }

  private var mainContentWithLifecycle: some View {
    mainContentStartupLifecycle
      // On sign-out: reset @AppStorage-backed onboarding flag and stop transcription.
      // hasCompletedOnboarding must be set here (in a View) because @AppStorage
      // on ObservableObject caches internally and ignores UserDefaults.removeObject().
      // Stopping transcription here prevents FOREIGN KEY errors from an old
      // transcription session writing to a new user's database.
      .onReceive(NotificationCenter.default.publisher(for: .userDidSignOut)) { _ in
        log(
          "DesktopHomeView: userDidSignOut — resetting hasCompletedOnboarding and stopping transcription"
        )
        chatFirstCapability.ownerDidChange(to: nil)
        resetSessionScopedStartupWarmups()
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
        resetSessionScopedStartupWarmups()
        appState.hasCompletedOnboarding = false
        onboardingStep = 0
        onboardingFurthestStep = 0
        onboardingJustCompleted = false
        appState.stopTranscription()
      }
      .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
        log("DesktopHomeView: app terminating — cancelling startup warmups")
        resetSessionScopedStartupWarmups()
      }
      // Periodic file re-scan (every 3 hours)
      .task {
        while !Task.isCancelled {
          try? await Task.sleep(for: .seconds(3 * 60 * 60))
          guard !Task.isCancelled else { break }
          guard !AppBuild.usesLazyDevPermissions else { continue }
          guard UserDefaults.standard.bool(forKey: .hasCompletedFileIndexing) else {
            continue
          }
          log("DesktopHomeView: Triggering background file rescan")
          await FileIndexerService.shared.backgroundRescan(
            fullDiskAccessGranted: await appState.refreshFullDiskAccess())
        }
      }
  }

  var body: some View {
    Group {
      if shouldShowAuthEntryShell {
        authEntryShell
      } else {
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
          mainContentWithLifecycle
            // The shell mounts immediately; the capability resolves alongside it and
            // only decides whether capability-gated features engage.
            .task(id: RuntimeOwnerIdentity.currentOwnerId() ?? "missing-owner") {
              await resolveChatFirstCapabilityIfNeeded()
            }

          if !viewModelContainer.isInitialLoadComplete {
            TransparentWindowStatusPanel {
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
                  .inkStyle(.prose, color: Ink.secondary)

                ProgressView()
                  .scaleEffect(0.8)
                  .tint(Ink.secondary)
              }
            }
            .transition(.opacity.animation(OmiMotion.gated(.easeOut(duration: 0.3))))
          }

          if let policy = updatePolicyManager.visiblePolicy, policy.isRequired {
            // The heaviest dim in the app, and the one that most needed bounding: mounted here it is
            // over the whole (invisible) window, so full-bleed it was a black rectangle on the
            // wallpaper. No dismiss gesture — a required update is required — but it still blocks.
            ShellModalScrim(opacity: ShellModalScrimLayout.blocking)
              .zIndex(20)
            DesktopRequiredUpdatePrompt(
              policy: policy,
              onDownload: { updatePolicyManager.openDownload(policy) }
            )
            .zIndex(21)
          } else {
            AccountCutoverBlockingOverlay.host(onOpenDownload: { updatePolicyManager.openDownload($0) })
          }
        }
      }
    }
    .environment(\.colorScheme, .light)  // No window ground since `ShellWindowChrome`; each panel is its own glass.
    .background(ShellWindowAttachment().frame(width: 0, height: 0))
    .frame(minWidth: DesktopWindowLayoutPolicy.width, minHeight: DesktopWindowLayoutPolicy.height)
    .preferredColorScheme(.light)  // Glass is pinned light — see `InkGlass`. Deliberate, not a bug.
    .tint(Ink.accent)
    .onAppear {
      reconcileOnboardingCompletionOwner()
      log(
        "DesktopHomeView: View appeared - isSignedIn=\(authState.isSignedIn), hasCompletedOnboarding=\(appState.hasCompletedOnboarding)"
      )
      // Drive the notch "moments" (live receipts + conversation-end) off real state.
      NotchMomentsCoordinator.shared.start(appState: appState)
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
      reportAutomationState()
      handleAutomationPresentationReadinessChange(viewModelContainer.isInitialLoadComplete)
    }
    .onChange(of: currentTierLevel) { _, _ in
      reportAutomationState()
    }
    .onChange(of: chatFirstNavigation.route) { _, _ in
      // Route nav recreates the content hosting view with default sizingOptions, which
      // resets the window min — re-pin + re-disable to hold the minimum.
      enforceMainWindowMinimumSize()
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
      reconcileOnboardingCompletionOwner()
      chatFirstCapability.ownerDidChange(to: RuntimeOwnerIdentity.currentOwnerId())
      // The provider's owner-bound gate rejects the previous sample for this
      // owner; no replacement sample is persisted or inferred locally.
      reportAutomationState()
    }
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
      enforceMainWindowMinimumSize()
      reportAutomationState()
      // First-run seed so the counter doesn't count the entire backlog as "new".
      seedTopBarNewSinceIfNeeded()
    }
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didResignActiveNotification)) { _ in
      reportAutomationState()
      // Mark the moment Omi went to the background; anything created after this
      // shows in the top bar's "new since you were last here" counter.
      topBarNewSinceRaw = Date().timeIntervalSince1970
    }
    .onReceive(NotificationCenter.default.publisher(for: .desktopAutomationNavigateRequested)) {
      notification in
      handleAutomationNavigation(notification)
    }
    .onReceive(NotificationCenter.default.publisher(for: .navigateToChat)) { _ in
      // The global shortcut / notch "Ask Omi" opens the continuous chat, which
      // is the shell's Chat route. Selecting it is idempotent, so no re-emit
      // loop guard is needed.
      chatFirstNavigation.selectPrimary(.chat)
    }
    // "Continue in Omi" from the floating bar. The one shell has no second chat
    // panel to consume the pending request on its behalf.
    .onReceive(NotificationCenter.default.publisher(for: .openMainChatRequested)) { _ in
      handleMainChatRequest()
    }
  }

  private func reconcileOnboardingCompletionOwner() {
    guard
      OnboardingFlow.reconcileCompletionOwner(
        currentOwnerID: RuntimeOwnerIdentity.currentOwnerId()) == .resetForDifferentOwner
    else { return }

    onboardingStep = 0
    onboardingFurthestStep = 0
    onboardingJustCompleted = false
    appState.hasCompletedOnboarding = false
  }

  private func handleMainChatRequest() {
    guard MainChatNavigationRequestStore.shared.consume() else { return }
    chatFirstNavigation.selectPrimary(.chat, origin: .chatDeeplink)
  }

  private func enforceMainWindowMinimumSize() {
    DispatchQueue.main.async {
      // Appearance belongs to `WindowGlass.wear(_:as:)`; stamping one here unpinned the glass.
      for window in NSApp.windows where window.title.lowercased().hasPrefix("omi") {
        Self.pinShellWindowSizeLimits(window)
        Self.disableMinSizeComputation(in: window)
      }
    }
  }

  /// Re-pin the window min and max on every live resize. SwiftUI's `.automatic` window
  /// resizability periodically recomputes content-size extrema and overwrites the
  /// one-shot pin from `enforceMainWindowMinimumSize()`, after which the window can be
  /// dragged small enough to hide content or wide enough to recreate the invisible
  /// click border. Observing `didResize` and re-pinning keeps AppKit clamping the live
  /// drag. Installed once for the app's lifetime.
  private static var minimumSizeGuardInstalled = false
  private func installMinimumSizeGuardIfNeeded() {
    guard !Self.minimumSizeGuardInstalled else { return }
    Self.minimumSizeGuardInstalled = true
    NotificationCenter.default.addObserver(
      forName: NSWindow.didResizeNotification, object: nil, queue: .main
    ) { notification in
      let objectBox = AnySendableBox(value: notification.object)
      MainActor.assumeIsolated {
        guard let window = objectBox.value as? NSWindow,
          window.title.lowercased().hasPrefix("omi")
        else { return }
        Self.pinShellWindowSizeLimits(window, resizeFrame: false)
      }
    }
  }

  /// Pins the shell between the destination minimum and the visible display frame.
  private static func pinShellWindowSizeLimits(_ window: NSWindow, resizeFrame: Bool = true) {
    let minimumContentSize = DesktopWindowLayoutPolicy.minimumContentSize
    let maximumContentSize = DesktopWindowLayoutPolicy.maximumContentSize(for: window)
    window.contentMinSize = minimumContentSize
    window.minSize = window.frameRect(forContentRect: NSRect(origin: .zero, size: minimumContentSize)).size
    window.contentMaxSize = maximumContentSize
    window.maxSize = window.frameRect(forContentRect: NSRect(origin: .zero, size: maximumContentSize)).size

    guard resizeFrame else { return }
    let currentContentSize = window.contentView?.bounds.size ?? window.contentLayoutRect.size
    var frame = window.frame
    var changed = false
    let widthDelta = max(0, minimumContentSize.width - currentContentSize.width)
    let heightDelta = max(0, minimumContentSize.height - currentContentSize.height)
    if widthDelta > 0 || heightDelta > 0 {
      frame.size.width += widthDelta
      frame.size.height += heightDelta
      frame.origin.y -= heightDelta
      changed = true
    }
    let maxFrameWidth = window.frameRect(
      forContentRect: NSRect(
        origin: .zero,
        size: NSSize(width: maximumContentSize.width, height: currentContentSize.height))
    ).width
    if frame.size.width > maxFrameWidth {
      let extra = frame.size.width - maxFrameWidth
      frame.origin.x += extra / 2
      frame.size.width = maxFrameWidth
      changed = true
    }
    if changed {
      window.setFrame(frame, display: true, animate: false)
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

  private func seedTopBarNewSinceIfNeeded() {
    let currentValue = topBarNewSinceRaw
    guard currentValue == 0 else { return }
    topBarNewSinceRaw = Date().timeIntervalSince1970
  }

  private var currentAppStateLabel: String {
    if authState.isRestoringAuth { return "restoring_auth" }
    if authState.sessionPhase == .recoveryRequired { return "auth_recovery" }
    if !authState.isSignedIn { return "signed_out" }
    if !appState.hasCompletedOnboarding { return "onboarding" }
    return "main"
  }

  /// Preserve the existing AppStorage winner while observing disagreement at
  /// the actual product/onboarding gate. This read still runs when the completed
  /// flag prevents SBOnboardingModel from mounting.
  private var hasCompletedOnboardingAtAuthorityRead: Bool {
    let completed = appState.hasCompletedOnboarding
    guard completed else { return false }
    let savedRaw = UserDefaults.standard.integer(forKey: SBOnboardingModel.resumeStepKey)
    if savedRaw > SBOnboardingModel.Step.promise.rawValue,
      SBOnboardingModel.Step(rawValue: savedRaw) != nil
    {
      DesktopDiagnosticsManager.shared.recordStateAuthoritySignal(
        seam: .onboardingSetupState,
        from: "completed_flag",
        to: "persisted_resume",
        direction: "completed_flag_with_resume_state")
    }
    if viewModelContainer.chatProvider.isOnboarding {
      DesktopDiagnosticsManager.shared.recordStateAuthoritySignal(
        seam: .onboardingSetupState,
        from: "completed_flag",
        to: "setup_journal",
        direction: "completed_flag_with_active_journal")
    }
    return true
  }

  private func reportAutomationState() {
    guard DesktopAutomationLaunchOptions.isEnabled else { return }

    let currentWindow = NSApp.windows.first(where: {
      $0.title.lowercased().hasPrefix("omi") && $0.isVisible
    })
    let chatFirstRoute = chatFirstNavigation.route
    let snapshot = DesktopAutomationSnapshot(
      bridgeEnabled: true,
      bridgePort: DesktopAutomationLaunchOptions.port,
      bundleIdentifier: Bundle.main.bundleIdentifier ?? "unknown",
      appState: currentAppStateLabel,
      selectedTab: chatFirstRoute.title,
      selectedTabIndex: nil,
      selectedSettingsSection: chatFirstRoute == .more(.settings)
        ? selectedSettingsSection.rawValue : nil,
      highlightedSettingId: highlightedSettingId,
      // There is one shell and it renders no Home stage: `DashboardPage` was its
      // only writer and no longer exists. `nil` says exactly that — never a
      // plausible-looking default a flow could wait on forever.
      homeMode: nil,
      // Pinned: the app has one shell. Retained in the snapshot because e2e
      // flows and the navigation-visibility policy read it.
      shellVariant: DesktopAutomationSnapshot.singleShellVariant,
      chatFirstRoute: chatFirstRoute.stableName,
      visibleChatFirstRoute: chatFirstNavigation.visibleRoute?.stableName,
      pendingFocusKind: chatFirstNavigation.pendingFocus?.stableName,
      acknowledgedFocusKind: chatFirstNavigation.lastAcknowledgedFocusKind,
      focusedEntityID: chatFirstNavigation.focusedEntityID,
      isFocusedEntityAcknowledged: chatFirstNavigation.isFocusedEntityAcknowledged,
      showsPrimarySidebar: false,
      isSidebarCollapsed: chatFirstNavigation.isSidebarCollapsed,
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
      floatingBarVoiceDictating: FloatingControlBarManager.shared.automationState.isVoiceDictating,
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
    let activateApp = notification.userInfo?["activateApp"] as? Bool ?? false

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

    if target.lowercased().replacingOccurrences(of: "-", with: "_") == "rewind" {
      navigateToLegacyDestination(.rewind)
      reportAutomationState()
      return
    }

    // `navigate help` used to name a "Help from Founder" page that no shell has
    // mounted for a long time, so the bridge resolved a title and then timed out
    // waiting for it. Settings → About is where getting help from a person
    // actually lives (the Community / Join Discord card), so the name now lands
    // on a destination that exists.
    if ChatFirstRoute.isHelpAutomationTarget(target), settingsSectionRaw == nil {
      selectedSettingsSection = .about
    }
    if let route = ChatFirstRoute.automationVisibilityDestination(named: target) {
      switch route {
      case .more(let page):
        chatFirstNavigation.selectMore(page)
      default:
        chatFirstNavigation.selectPrimary(route)
      }
    }

    reportAutomationState()
  }

  private func handleAutomationPresentationCommand(
    _ command: DesktopAutomationPresentationCommand
  ) {
    if DesktopAutomationWindowPresentation.currentMode != .quiet {
      NSApp.activate()
      if let window = NSApp.windows.first(where: { $0.title.lowercased().hasPrefix("omi") }) {
        window.makeKeyAndOrderFront(nil)
      }
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

  private func resetSessionScopedStartupWarmups() {
    viewModelContainer.resetStartupState()
    didScheduleConversationWarmup = false
    didScheduleAgentVMProvisioning = false
    proactiveMonitoringStartGate.finishAttempt()
    initialFileIndexingBackfill.releaseReservation()
  }

  private func scheduleAgentVMProvisioning() {
    guard !didScheduleAgentVMProvisioning else { return }
    didScheduleAgentVMProvisioning = true

    let scheduled = viewModelContainer.scheduleSessionWarmup(
      id: .agentVMProvisioning,
      delay: StartupWarmupPolicy.agentVMProvisioningDelay,
      onCancel: { didScheduleAgentVMProvisioning = false },
      operation: {
        await AgentVMService.shared.ensureProvisioned()
      })
    if !scheduled { didScheduleAgentVMProvisioning = false }
  }

  private func scheduleConversationWarmup() {
    guard !didScheduleConversationWarmup else { return }
    didScheduleConversationWarmup = true

    let scheduled = viewModelContainer.scheduleSessionWarmup(
      id: .conversationWarmup,
      delay: StartupWarmupPolicy.conversationWarmupDelay,
      onCancel: { didScheduleConversationWarmup = false },
      operation: {
        async let conversations: Void = loadConversationsIfNeeded()
        async let folders: Void = loadFoldersIfNeeded()
        // Warm memories + tasks too so the top bar's new-item counter has data
        // even before those tabs are visited.
        async let memories: Void = viewModelContainer.memoriesViewModel.loadMemoriesIfNeeded()
        async let tasks: Void = viewModelContainer.tasksStore.loadTasksIfNeeded()
        _ = await (conversations, folders, memories, tasks)
      })
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
      userId: UserDefaults.standard.string(forKey: .authUserId))
    let scheduled = viewModelContainer.scheduleSessionWarmup(
      id: .initialFileIndexing,
      delay: StartupWarmupPolicy.initialFileIndexingDelay,
      onCancel: { initialFileIndexingBackfill.releaseReservation() },
      operation: {
        log("DesktopHomeView: Running delayed background file scan for existing user")
        await FileIndexerService.shared.backgroundRescan(
          fullDiskAccessGranted: await appState.refreshFullDiskAccess())
        guard !Task.isCancelled,
          sessionScope.matches(
            currentUserId: UserDefaults.standard.string(forKey: .authUserId),
            isSignedIn: AuthState.shared.isSignedIn)
        else {
          initialFileIndexingBackfill.releaseReservation()
          return
        }
        initialFileIndexingBackfill.markScanCompleted()
        if initialFileIndexingBackfill.shouldMarkComplete {
          UserDefaults.standard.set(true, forKey: .hasCompletedFileIndexing)
          log(
            "DesktopHomeView: Marked existing-user file indexing backfill complete after background scan returned"
          )
        }
      })
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
      onCancel: { proactiveMonitoringStartGate.finishAttempt() },
      operation: {
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
      })
    if !scheduled { proactiveMonitoringStartGate.finishAttempt() }
  }

  private func restorePersistedCaptureServices(reason: String) {
    let settings = AssistantSettings.shared
    // Fresh TCC answer before deciding whether an automatic start is allowed.
    appState.checkMicrophonePermission()
    if PersistedCaptureLaunchPolicy.shouldStartTranscription(
      intentEnabled: settings.audioRecordingMode != .off,
      isTranscribing: appState.isTranscribing,
      micPermissionAuthorized: appState.hasMicrophonePermission
    ) {
      log("DesktopHomeView: Restoring transcription from persisted intent (\(reason))")
      // Local transcription does not require remote API keys. AppState owns the
      // permission and provider checks, so it remains the single start boundary.
      appState.startTranscription(userInitiated: false)
    }

    let plugin = ProactiveAssistantsPlugin.shared
    guard
      PersistedCaptureLaunchPolicy.shouldStartScreenAnalysis(
        intentEnabled: settings.screenAnalysisEnabled,
        isMonitoring: plugin.isMonitoring
      )
    else { return }

    guard APIKeyService.keysAvailable else {
      waitForScreenAnalysisKeys(reason: reason)
      return
    }

    plugin.refreshScreenRecordingPermission()
    guard plugin.hasScreenRecordingPermission else {
      log("DesktopHomeView: Screen recording permission unavailable; retaining capture intent (\(reason))")
      return
    }
    scheduleProactiveMonitoringStart(reason: reason)
  }

  private func waitForScreenAnalysisKeys(reason: String) {
    guard !isWaitingForScreenAnalysisKeys else { return }
    isWaitingForScreenAnalysisKeys = true
    log("DesktopHomeView: Deferring screen analysis until API keys load (\(reason))")
    Task { @MainActor in
      await APIKeyService.shared.waitForKeys()
      isWaitingForScreenAnalysisKeys = false
      guard APIKeyService.keysAvailable else {
        log("DesktopHomeView: API keys remain unavailable; retaining capture intent")
        return
      }
      restorePersistedCaptureServices(reason: "key wait completed")
    }
  }

  private func reconcileCaptureServicesAfterSettingsSync() {
    let plugin = ProactiveAssistantsPlugin.shared
    if !AssistantSettings.shared.screenAnalysisEnabled, plugin.isMonitoring {
      log("DesktopHomeView: Stopping screen analysis after server settings sync")
      plugin.stopMonitoring(reason: .settingsSync)
    }
    restorePersistedCaptureServices(reason: "settings sync")
  }

  private func updateStoreActivityForCurrentShell() {
    viewModelContainer.tasksStore.isActive =
      chatFirstNavigation.route == .tasks || chatFirstNavigation.route == .more(.dashboard)
    viewModelContainer.memoriesViewModel.isActive = chatFirstNavigation.route == .memories
  }

  /// One fresh server read decides the local runtime projection. It does not
  /// decide which shell mounts — there is only one — so the shell is already on
  /// screen while this runs. A failed response, missing owner, stale auth
  /// snapshot, or owner change resolves capability-off: rich blocks still
  /// render, kernel features stay dormant.
  private func resolveChatFirstCapabilityIfNeeded() async {
    guard !chatFirstCapability.isResolved else { return }
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId(),
      let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
    else {
      chatFirstCapability.resolve(
        control: nil,
        requestedOwnerID: nil,
        ownerIsStillCurrent: false
      )
      _ = viewModelContainer.chatProvider.configureChatFirstMainChatCapability(nil)
      log("DesktopHomeView: chat-first capability off — no owner or authorization snapshot at sample time")
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
      chatFirstCapability.resolve(
        control: control,
        requestedOwnerID: ownerID,
        ownerIsStillCurrent: current
      )
    } catch {
      let current =
        RuntimeOwnerIdentity.isAuthorizationCurrent(authorization)
        && RuntimeOwnerIdentity.currentOwnerId() == ownerID
      chatFirstCapability.resolve(
        control: nil,
        requestedOwnerID: ownerID,
        ownerIsStillCurrent: current
      )
      capabilityErrorClass = .unavailable
      log("DesktopHomeView: chat-first control unavailable; capability stays off")
    }

    let projectionConfigured = viewModelContainer.chatProvider.configureChatFirstMainChatCapability(
      chatFirstCapability.projection
    )
    if !projectionConfigured {
      // A pre-existing Main Chat session cannot be retroactively upgraded with
      // dynamic tools. Fail closed to capability-off for this launch; the shell
      // and its content blocks are unaffected.
      chatFirstCapability.failClosed()
      capabilityErrorClass = .projectionRejected
      log("DesktopHomeView: chat-first projection handoff rejected; capability stays off")
    }
    let projection = chatFirstCapability.projection
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
    log(
      "DesktopHomeView: chat-first capability resolved outcome=\(capabilityOutcome) "
        + "generation=\(projection.map { String($0.controlGeneration) } ?? "none")")
    reportAutomationState()
  }

  private func navigateAfterOnboarding() {
    chatFirstNavigation.selectPrimary(.chat)
    log("DesktopHomeView: Onboarding just completed — opening Chat")
  }

  /// Existing menu, keyboard, and automation callers retain their legacy
  /// names. This is the sole root adapter between those callers and typed
  /// Chat-first navigation.
  private func navigateToLegacyDestination(_ item: SidebarNavItem) {
    if item == .permissions {
      selectedSettingsSection = .permissions
      chatFirstNavigation.selectMore(.settings)
      return
    }
    if let destination = MemoryHubDestination.destination(for: item) {
      memoryDestinationRawValue = destination.rawValue
    }
    chatFirstNavigation.selectLegacyDestination(item)
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
      .overlay(alignment: .bottom) {
        // One-time rating ask, due after the user's 3rd question. Remote
        // (admin-authored) prompts render through the same slot; the built-in
        // ask has right of way inside RemotePromptEngine.evaluate().
        RatingPromptBar()
        RemotePromptBar()
      }
      .task(id: RuntimeOwnerIdentity.currentOwnerId() ?? "signed-out") {
        // Re-runs on every owner transition (same pattern as the chat-first
        // capability task): cached prompt state must swap accounts instantly.
        RatingPromptManager.shared.ownerDidChange()
        RemotePromptEngine.shared.ownerDidChange()
        RemotePromptEngine.shared.start()
        await RatingPromptManager.shared.seedFromHistoryIfNeeded()
      }
      .overlay {
        if showTryAskingPopup {
          TryAskingPopupView(
            onTry: { useCase in
              showTryAskingPopup = false
              PostOnboardingPromptSuggestions.consume()
              FirstUseCaseLauncher.launch(useCase)
            },
            onDismiss: {
              showTryAskingPopup = false
              PostOnboardingPromptSuggestions.consume()
            }
          )
        }
      }
  }

  private func mainContentWithNotifications<Content: View>(_ content: Content) -> some View {
    content
      .onReceive(NotificationCenter.default.publisher(for: .showTryAskingPopup)) { _ in
        // The first-use popup belongs to whoever just finished onboarding, and
        // there is now one shell for all of them. `shouldArmPopup` upstream is
        // still the only thing that decides whether it is due.
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
      .onReceive(NotificationCenter.default.publisher(for: .navigateToPlanSettings)) { _ in
        selectedSettingsSection = .planUsage
        highlightedSettingId = "planusage.current"
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
        chatFirstNavigation.selectPrimary(.chat)
      }
      .onReceive(NotificationCenter.default.publisher(for: .navigateToTasks)) { _ in
        navigateToLegacyDestination(.tasks)
      }
      .onReceive(NotificationCenter.default.publisher(for: .navigateToSidebarItem)) { notification in
        if let rawValue = notification.userInfo?["rawValue"] as? Int,
          let item = SidebarNavItem(rawValue: rawValue)
        {
          // A caller that names a hub view has to select it, not just open the hub. `⌘2` is
          // labelled "Conversations" and the hub's remembered view defaults to Memories, so
          // without this the menu item lands you somewhere it did not name. The two automation
          // routes below already did this by hand; the menu and keyboard path did not.
          if let destination = MemoryHubDestination.destination(for: item) {
            memoryDestinationRawValue = destination.rawValue
          }
          // Settings owns pages now, not only preference rows, so a caller that names Settings can
          // name the row it means. Without it a banner could only drop the user on whichever
          // section they last had open.
          if let sectionRaw = notification.userInfo?["settingsSection"] as? String,
            let section = SettingsContentView.SettingsSection.automationMatch(sectionRaw)
          {
            selectedSettingsSection = section
          }
          navigateToLegacyDestination(item)
        }
      }
      .onReceive(NotificationCenter.default.publisher(for: .desktopAutomationOpenMemoryAtlasRequested)) { _ in
        memoryDestinationRawValue = MemoryHubDestination.brainMap.rawValue
        chatFirstNavigation.selectPrimary(.memories)
      }
      .onReceive(NotificationCenter.default.publisher(for: .desktopAutomationOpenConversationRequested)) { _ in
        memoryDestinationRawValue = MemoryHubDestination.conversations.rawValue
        navigateToLegacyDestination(.conversations)
      }
  }

  private func mainContentWithLifecycle<Content: View>(_ content: Content) -> some View {
    content
      .onChange(of: chatFirstNavigation.route) { _, _ in
        updateStoreActivityForCurrentShell()
        reportAutomationState()
      }
      .onChange(of: chatFirstNavigation.visibleRoute) { _, _ in reportAutomationState() }
      .onChange(of: chatFirstNavigation.isSidebarCollapsed) { _, _ in reportAutomationState() }
      .onAppear {
        updateStoreActivityForCurrentShell()
        restorePreChatWindowWidth()
      }
  }

  private var shellContent: some View {
    ChatFirstShell(
      navigation: chatFirstNavigation,
      appState: appState,
      viewModelContainer: viewModelContainer,
      capability: chatFirstCapability.projection,
      selectedSettingsSection: $selectedSettingsSection,
      highlightedSettingID: $highlightedSettingId
    )
  }
}

/// Hosts the standalone Conversations page with its own selection state
/// so tapping a row navigates to the detail view.
struct ConversationsPageHost: View {
  let appState: AppState
  var brainDestination: MemoryHubDestination? = nil
  var onSelectBrainDestination: ((MemoryHubDestination) -> Void)? = nil
  /// Optional exact record supplied by a Chat-first conversation deep-link.
  /// The normal Conversations page still owns list loading and row selection;
  /// this value only seeds selection when a link fetched a record that is not
  /// present in the current page.
  var initialConversation: ServerConversation? = nil
  /// Optional source-specific behavior carried into the canonical detail.
  /// These values never select a second browser or detail presentation.
  var initialCaptureMomentTimestamp: TimeInterval? = nil
  var onCaptureFocusResolved: ((Bool) -> Void)? = nil
  var onDiscussInChat: ((ServerConversation) -> Void)? = nil
  var onOpenLinkedTask: ((String) -> Void)? = nil
  var onSelectionChanged: ((ServerConversation?) -> Void)? = nil
  @State private var selectedConversation: ServerConversation? = nil
  @ObservedObject private var conversationDetailState = ConversationDetailAutomationState.shared

  private var usesAvailableWidth: Bool {
    MemoryHubLayoutPolicy.usesAvailableWidth(
      conversationID: selectedConversation?.id,
      presentedConversationID: conversationDetailState.openConversationId,
      transcriptDrawerOpen: conversationDetailState.transcriptDrawerOpen
    )
  }

  var body: some View {
    ConversationsPage(
      appState: appState,
      selectedConversation: $selectedConversation,
      brainDestination: brainDestination,
      onSelectBrainDestination: onSelectBrainDestination,
      initialCaptureMomentTimestamp: initialCaptureMomentTimestamp,
      onCaptureFocusResolved: onCaptureFocusResolved,
      onDiscussInChat: onDiscussInChat,
      onOpenLinkedTask: onOpenLinkedTask
    )
    .frame(
      maxWidth: brainDestination != nil || usesAvailableWidth
        ? .infinity : MemoryHubLayoutPolicy.readableContentWidth,
      maxHeight: .infinity
    )
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .animation(.easeInOut(duration: 0.22), value: usesAvailableWidth)
    // Owner fencing: an open detail view must not keep showing the previous
    // account's conversation after an in-place account switch.
    .onReceive(NotificationCenter.default.publisher(for: .runtimeOwnerDidChange)) { _ in
      selectedConversation = nil
    }
    .onAppear {
      if let initialConversation {
        selectedConversation = initialConversation
      }
      onSelectionChanged?(selectedConversation)
    }
    .onChange(of: initialConversation?.id) { _, _ in
      selectedConversation = initialConversation
    }
    .onChange(of: selectedConversation?.id) { _, _ in
      onSelectionChanged?(selectedConversation)
    }
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    DesktopHomeView()
      .environmentObject(AppState())
  }
#endif
