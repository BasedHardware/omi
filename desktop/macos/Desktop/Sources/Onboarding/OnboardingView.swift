import AVKit
import AppKit
import OmiTheme
import SceneKit
import SwiftUI

struct OnboardingView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var chatProvider: ChatProvider
  var onComplete: (() -> Void)? = nil
  var exportStepOverride: Int? = nil
  var isExportPreview = false
  @AppStorage("onboardingStep") private var currentStep = 0
  /// Highest step the user has ever reached — a step is "cleared" (answered,
  /// granted, or skipped) once they advance past it. Monotonic and persisted so
  /// it survives the app restart the permission steps trigger. Gates the
  /// clickable progress dots and forward navigation.
  @AppStorage("onboardingFurthestStep") private var furthestStep = 0
  @AppStorage("onboardingPagedIntroMigrationDone") private var hasMigratedPagedIntro = false
  @AppStorage("onboardingVideoStepMigrationDone") private var hasMigratedOnboardingSteps = false
  @AppStorage("onboardingVoiceShortcutStepMigrationDone") private var hasInsertedVoiceShortcutStep =
    false
  @AppStorage("onboardingVoiceInputMergeMigrationDone") private var hasMergedVoiceInputStep = false
  @AppStorage("onboardingNotificationStepRemoved") private var hasRemovedNotificationStep = false
  @AppStorage("onboardingFloatingBarShortcutStepInserted") private
    var hasInsertedFloatingBarShortcutStep = false
  @AppStorage("onboardingTrustStepReordered") private var hasReorderedTrustStep = false
  @AppStorage("onboardingHowDidYouHearStepInserted") private var hasInsertedHowDidYouHearStep =
    false
  @AppStorage("onboardingDataSourcesStepInserted") private var hasInsertedDataSourcesStep = false
  @AppStorage("onboardingExportsStepInserted") private var hasInsertedExportsStep = false
  @AppStorage("onboardingSecondBrainStepInserted") private var hasInsertedSecondBrainStep = false
  @AppStorage("onboardingResearchStepRemoved") private var hasRemovedResearchStep = false
  @AppStorage("onboardingNotificationPermissionStepRemoved") private
    var hasRemovedNotificationPermissionStep = false
  @AppStorage("onboardingBYOKStepInserted") private var hasInsertedBYOKStep = false
  @AppStorage("onboardingBYOKStepRemoved") private var hasRemovedBYOKStep = false
  @StateObject private var introCoordinator = OnboardingPagedIntroCoordinator()
  @StateObject private var graphViewModel = MemoryGraphViewModel()
  @FocusState private var contentFocused: Bool
  /// Static, not @State: SwiftUI can recreate this view mid-flow (parent tree
  /// identity changes), and a per-identity handle would leak the old monitor —
  /// which keeps consuming arrow keys — while installing a second one. One
  /// shared handle means re-install replaces instead of stacking.
  private static var keyNavMonitor: Any?

  let steps = OnboardingFlow.steps

  var body: some View {
    ZStack {
      // Full dark background
      OmiColors.backgroundPrimary
        .ignoresSafeArea()

      Group {
        if appState.hasCompletedOnboarding && !isExportPreview {
          Color.clear
            .onAppear {
              log("OnboardingView: hasCompletedOnboarding=true, starting monitoring")
              if !ProactiveAssistantsPlugin.shared.isMonitoring {
                ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
              }
              if let onComplete = onComplete {
                log("OnboardingView: Calling onComplete handler")
                onComplete()
              } else {
                log(
                  "OnboardingView: No onComplete handler, view will transition via DesktopHomeView")
              }
            }
        } else {
          onboardingContent
        }
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .onAppear {
      OnboardingPagedIntroCoordinator.current = introCoordinator
      if let exportStepOverride {
        currentStep = exportStepOverride
      } else {
        currentStep = OnboardingFlow.migratedStep(
          currentStep: currentStep,
          hasMigratedVideoStep: hasMigratedOnboardingSteps,
          hasInsertedVoiceShortcutStep: hasInsertedVoiceShortcutStep,
          hasMergedVoiceInputStep: hasMergedVoiceInputStep,
          hasRemovedNotificationStep: hasRemovedNotificationStep,
          hasInsertedFloatingBarShortcutStep: hasInsertedFloatingBarShortcutStep,
          hasMigratedPagedIntro: hasMigratedPagedIntro,
          hasReorderedTrustStep: hasReorderedTrustStep,
          hasInsertedHowDidYouHearStep: hasInsertedHowDidYouHearStep,
          hasInsertedDataSourcesStep: hasInsertedDataSourcesStep,
          hasInsertedExportsStep: hasInsertedExportsStep,
          hasInsertedSecondBrainStep: hasInsertedSecondBrainStep,
          hasRemovedResearchStep: hasRemovedResearchStep,
          hasInsertedBYOKStep: hasInsertedBYOKStep,
          hasRemovedBYOKStep: hasRemovedBYOKStep,
          hasRemovedNotificationPermissionStep: hasRemovedNotificationPermissionStep
        )
      }
      hasMigratedPagedIntro = true
      hasMigratedOnboardingSteps = true
      hasInsertedVoiceShortcutStep = true
      hasMergedVoiceInputStep = true
      hasRemovedNotificationStep = true
      hasInsertedFloatingBarShortcutStep = true
      hasReorderedTrustStep = true
      hasInsertedHowDidYouHearStep = true
      hasInsertedDataSourcesStep = true
      hasInsertedExportsStep = true
      hasInsertedSecondBrainStep = false
      hasRemovedResearchStep = true
      hasRemovedNotificationPermissionStep = true
      hasInsertedBYOKStep = true
      hasRemovedBYOKStep = true
      introCoordinator.prepare(appState: appState)
      installKeyNavigationMonitor()
    }
    .onDisappear {
      // Identity churn re-creates this view mid-flow, and the new identity's
      // onAppear may run before this onDisappear — removing here would tear
      // down the monitor it just installed. Only remove once onboarding is
      // actually over; the handler also no-ops after completion.
      if !isExportPreview, appState.hasCompletedOnboarding {
        removeKeyNavigationMonitor()
      }
    }
    .task {
      guard !isExportPreview else { return }
      // Pre-warm the agent bridge before the chat step starts.
      await chatProvider.warmupBridge()
      await graphViewModel.addGraphFromStorage()
      if graphViewModel.isEmpty {
        await graphViewModel.loadGraph()
      }
    }
    .onReceive(NotificationCenter.default.publisher(for: .resetOnboardingRequested)) { _ in
      log("OnboardingView: resetOnboardingRequested — returning to the first onboarding step")
      currentStep = 0
      furthestStep = 0
    }
    .onReceive(
      NotificationCenter.default.publisher(for: .onboardingStepNavigationRequested)
    ) { note in
      guard !isExportPreview, let requested = note.userInfo?["targetStep"] as? Int else { return }
      guard
        let target = OnboardingFlow.validatedNavigationTarget(
          requested, currentStep: currentStep, furthestStep: furthestStep)
      else { return }
      currentStep = target
    }
  }

  private var onboardingContent: some View {
    Group {
      if currentStep == 0 {
        OnboardingWelcomeStepView(
          coordinator: introCoordinator,
          graphViewModel: graphViewModel,
          stepIndex: 0,
          totalSteps: OnboardingFlow.steps.count,
          onContinue: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 0, stepName: "Name")
            currentStep = 1
          },
          onForceComplete: handleOnboardingComplete
        )
      } else if currentStep == 1 {
        OnboardingLanguageStepView(
          coordinator: introCoordinator,
          graphViewModel: graphViewModel,
          stepIndex: 1,
          totalSteps: OnboardingFlow.steps.count,
          onContinue: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 1, stepName: "Language")
            currentStep = 2
          },
          onForceComplete: handleOnboardingComplete
        )
      } else if currentStep == 2 {
        OnboardingHowDidYouHearStepView(
          graphViewModel: graphViewModel,
          stepIndex: 2,
          totalSteps: OnboardingFlow.steps.count,
          onContinue: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 2, stepName: "HowDidYouHear")
            currentStep = 3
          },
          onForceComplete: handleOnboardingComplete
        )
      } else if currentStep == 3 {
        OnboardingTrustStepView(
          coordinator: introCoordinator,
          graphViewModel: graphViewModel,
          stepIndex: 3,
          totalSteps: OnboardingFlow.steps.count,
          onContinue: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 3, stepName: "Trust")
            currentStep = 4
          },
          onForceComplete: handleOnboardingComplete
        )
      } else if currentStep == 4 {
        OnboardingPermissionStepView(
          appState: appState,
          coordinator: introCoordinator,
          graphViewModel: graphViewModel,
          stepIndex: 4,
          totalSteps: OnboardingFlow.steps.count,
          eyebrow: "Permission",
          title: "Let Omi read your screen.",
          description: "Screen Recording lets Omi see what you're working on.",
          permissionType: "screen_recording",
          icon: "display.and.arrow.down",
          reasonTitle: "Screen Recording",
          primaryActionLabel: "Open Screen Recording settings",
          onContinue: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 4, stepName: "ScreenRecording")
            if !AppBuild.usesLazyDevPermissions {
              startMonitoringIfNeeded()
            }
            currentStep = 5
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 4, stepName: "ScreenRecording_Skipped")
            currentStep = 5
          },
          onForceComplete: handleOnboardingComplete
        )
      } else if currentStep == 5 {
        OnboardingPermissionStepView(
          appState: appState,
          coordinator: introCoordinator,
          graphViewModel: graphViewModel,
          stepIndex: 5,
          totalSteps: OnboardingFlow.steps.count,
          eyebrow: "Access",
          title: "Let Omi scan your work.",
          description: "File access lets Omi map your projects and files.",
          permissionType: "full_disk_access",
          icon: "externaldrive.fill.badge.person.crop",
          reasonTitle: "Disk Access",
          primaryActionLabel: "Open Disk Access",
          onContinue: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 5, stepName: "FullDiskAccess")
            currentStep = 6
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 5, stepName: "FullDiskAccess_Skipped")
            currentStep = 6
          },
          onForceComplete: handleOnboardingComplete
        )
      } else if currentStep == 6 {
        OnboardingFileScanStepView(
          appState: appState,
          coordinator: introCoordinator,
          graphViewModel: graphViewModel,
          stepIndex: 6,
          totalSteps: OnboardingFlow.steps.count,
          onContinue: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 6, stepName: "FileScan")
            currentStep = 7
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 6, stepName: "FileScan_Skipped")
            currentStep = 7
          },
          onForceComplete: handleOnboardingComplete
        )
      } else if currentStep == 7 {
        OnboardingPermissionStepView(
          appState: appState,
          coordinator: introCoordinator,
          graphViewModel: graphViewModel,
          stepIndex: 7,
          totalSteps: OnboardingFlow.steps.count,
          eyebrow: "Permission",
          title: "Let Omi use your mic.",
          description: "Microphone lets Omi transcribe meetings and voice notes.",
          permissionType: "microphone",
          icon: "mic.fill",
          reasonTitle: "Microphone",
          primaryActionLabel: "Grant microphone access",
          onContinue: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 7, stepName: "Microphone")
            currentStep = 8
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 7, stepName: "Microphone_Skipped")
            currentStep = 8
          },
          onForceComplete: handleOnboardingComplete
        )
      } else if currentStep == 8 {
        OnboardingPermissionStepView(
          appState: appState,
          coordinator: introCoordinator,
          graphViewModel: graphViewModel,
          stepIndex: 8,
          totalSteps: OnboardingFlow.steps.count,
          eyebrow: "Permission",
          title: "Let Omi see the active app.",
          description: "Accessibility lets Omi know which app is active.",
          permissionType: "accessibility",
          icon: "figure.wave",
          reasonTitle: "Accessibility",
          primaryActionLabel: "Open Accessibility settings",
          onContinue: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 8, stepName: "Accessibility")
            currentStep = 9
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 8, stepName: "Accessibility_Skipped")
            currentStep = 9
          },
          onForceComplete: handleOnboardingComplete
        )
      } else if currentStep == 9 {
        OnboardingPermissionStepView(
          appState: appState,
          coordinator: introCoordinator,
          graphViewModel: graphViewModel,
          stepIndex: 9,
          totalSteps: OnboardingFlow.steps.count,
          eyebrow: "Permission",
          title: "Let Omi act when asked.",
          description: "Automation lets Omi take actions for you.",
          permissionType: "automation",
          icon: "bolt.horizontal.circle.fill",
          reasonTitle: "Automation",
          primaryActionLabel: "Grant automation access",
          onContinue: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 9, stepName: "Automation")
            currentStep = 10
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 9, stepName: "Automation_Skipped")
            currentStep = 10
          },
          onForceComplete: handleOnboardingComplete
        )
      } else if currentStep == 10 {
        OnboardingFloatingBarShortcutStepView(
          appState: appState,
          chatProvider: chatProvider,
          stepIndex: 10,
          totalSteps: OnboardingFlow.steps.count,
          onComplete: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 10, stepName: "FloatingBarShortcut")
            currentStep = 11
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 10, stepName: "FloatingBarShortcut_Skipped")
            currentStep = 11
          },
          onForceComplete: handleOnboardingComplete
        )
      } else if currentStep == 11 {
        OnboardingFloatingBarDemoView(
          appState: appState,
          chatProvider: chatProvider,
          stepIndex: 11,
          totalSteps: OnboardingFlow.steps.count,
          onComplete: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 11, stepName: "FloatingBar")
            currentStep = 12
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 11, stepName: "FloatingBar_Skipped")
            currentStep = 12
          },
          onForceComplete: handleOnboardingComplete
        )
      } else if currentStep == 12 {
        OnboardingVoiceShortcutStepView(
          appState: appState,
          chatProvider: chatProvider,
          stepIndex: 12,
          totalSteps: OnboardingFlow.steps.count,
          onComplete: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 12, stepName: "VoiceShortcut")
            currentStep = 13
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 12, stepName: "VoiceShortcut_Skipped")
            currentStep = 13
          },
          onForceComplete: handleOnboardingComplete
        )
      } else if currentStep == 13 {
        OnboardingVoiceDemoView(
          appState: appState,
          chatProvider: chatProvider,
          stepIndex: 13,
          totalSteps: OnboardingFlow.steps.count,
          onComplete: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 13, stepName: "VoiceDemo")
            currentStep = 14
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 13, stepName: "VoiceDemo_Skipped")
            currentStep = 14
          },
          onForceComplete: handleOnboardingComplete
        )
      } else if currentStep == 14 {
        OnboardingDataSourcesStepView(
          coordinator: introCoordinator,
          graphViewModel: graphViewModel,
          stepIndex: 14,
          totalSteps: OnboardingFlow.steps.count,
          onContinue: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 14, stepName: "DataSources")
            currentStep = 15
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 14, stepName: "DataSources_Skipped")
            currentStep = 15
          },
          onForceComplete: handleOnboardingComplete
        )
      } else if currentStep == 15 {
        OnboardingExportsStepView(
          graphViewModel: graphViewModel,
          stepIndex: 15,
          totalSteps: OnboardingFlow.steps.count,
          summaryText: introCoordinator.connectedContextSummary,
          onContinue: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 15, stepName: "Exports")
            currentStep = 16
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 15, stepName: "Exports_Skipped")
            currentStep = 16
          },
          onForceComplete: handleOnboardingComplete
        )
      } else if currentStep == 16 {
        OnboardingGoalStepView(
          appState: appState,
          coordinator: introCoordinator,
          graphViewModel: graphViewModel,
          stepIndex: 16,
          totalSteps: OnboardingFlow.steps.count,
          onContinue: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 16, stepName: "Goal")
            if !AppBuild.usesLazyDevPermissions, !ProactiveAssistantsPlugin.shared.isMonitoring {
              ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
            }
            currentStep = 17
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 16, stepName: "Goal_Skipped")
            if !AppBuild.usesLazyDevPermissions, !ProactiveAssistantsPlugin.shared.isMonitoring {
              ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
            }
            currentStep = 17
          },
          onForceComplete: handleOnboardingComplete
        )
      } else {
        OnboardingTasksStepView(
          stepIndex: 17,
          totalSteps: OnboardingFlow.steps.count,
          onComplete: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 17, stepName: "Tasks")
            handleOnboardingComplete()
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 17, stepName: "Tasks_Skipped")
            handleOnboardingComplete()
          },
          onForceComplete: handleOnboardingComplete
        )
      }
    }
    .environment(\.onboardingBack, canGoBack ? goBack : nil)
    .environment(\.onboardingJumpTo, isExportPreview ? nil : jumpTo)
    .environment(\.onboardingFurthestStep, isExportPreview ? Int.max : furthestStep)
    .focusable(true)
    .focusEffectDisabled()
    .focused($contentFocused)
    .onAppear {
      contentFocused = true
      recordFrontier(currentStep)
    }
    .onChange(of: currentStep) { _, newStep in
      contentFocused = true
      recordFrontier(newStep)
    }
  }

  /// Back is available on every step past the first, except in the export preview
  /// where the step is pinned by `exportStepOverride`.
  private var canGoBack: Bool {
    currentStep > 0 && !isExportPreview
  }

  private func goBack() {
    guard canGoBack else { return }
    currentStep -= 1
  }

  /// Advance the cleared-step frontier. Monotonic, clamped to the real step
  /// range (a pre-migration index could exceed it), and never written by the
  /// export preview — that pins an arbitrary step and must not mark the real
  /// user's steps as cleared.
  private func recordFrontier(_ step: Int) {
    guard !isExportPreview else { return }
    furthestStep = min(max(furthestStep, step), OnboardingFlow.lastStepIndex)
  }

  /// Jump directly to a step — powers the clickable progress dots. Backward and
  /// already-cleared steps are always reachable; forward jumps may pass over
  /// skippable steps (equivalent to pressing their Skip buttons) but stop at an
  /// unanswered required step. Policy lives in `OnboardingFlow.canJump`.
  private func jumpTo(_ index: Int) {
    guard !isExportPreview else { return }
    guard OnboardingFlow.canJump(to: index, furthestStep: furthestStep) else { return }
    currentStep = index
  }

  /// Arrow-key navigation runs off a local `NSEvent` monitor rather than SwiftUI
  /// `.onKeyPress`, because the "Ask a question" steps take key focus away from the
  /// onboarding window (shortcut steps null the app menu + install their own key
  /// monitor; demo steps hand focus to the floating Ask Omi panel). A monitor sees
  /// the keystroke regardless of which of the app's windows is key.
  private func installKeyNavigationMonitor() {
    // The outer onAppear also runs on the already-completed branch — don't
    // install an arrow monitor for a flow that isn't showing.
    guard !isExportPreview, !appState.hasCompletedOnboarding else { return }
    removeKeyNavigationMonitor()
    Self.keyNavMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
      handleArrowNavigation(event) ? nil : event
    }
  }

  private func removeKeyNavigationMonitor() {
    if let monitor = Self.keyNavMonitor {
      NSEvent.removeMonitor(monitor)
      Self.keyNavMonitor = nil
    }
  }

  /// Returns true when the event was consumed as a back/forward navigation.
  /// Skips plain arrows while the user is typing (any text field, including the
  /// floating Ask Omi bar) so the caret keeps moving instead of navigating.
  ///
  /// Runs inside the NSEvent monitor closure, which holds a detached copy of
  /// this view. Mutating @AppStorage through that copy silently drops the write
  /// on some macOS versions (it never reaches UserDefaults or the mounted
  /// view), so this reads the persisted step state directly and posts the
  /// target step for the mounted view's `.onReceive` to apply.
  private func handleArrowNavigation(_ event: NSEvent) -> Bool {
    guard !isExportPreview else { return false }
    // The monitor may briefly outlive the flow (removal is deferred across
    // identity churn); never swallow arrows once onboarding is done.
    guard !UserDefaults.standard.bool(forKey: .hasCompletedOnboarding) else { return false }
    // Only bare arrows navigate — leave shortcut chords (⌘/⌥/⌃/⇧) to their owners.
    let mods = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
    guard mods.subtracting([.function, .numericPad]).isEmpty else { return false }
    // Typing in the floating bar or any text field owns the arrows.
    if NSApp.keyWindow is FloatingControlBarWindow { return false }
    if NSApp.keyWindow?.firstResponder is NSText { return false }

    let defaults = UserDefaults.standard
    let step = defaults.integer(forKey: .onboardingStep)
    let frontier = defaults.integer(forKey: .onboardingFurthestStep)

    switch OnboardingFlow.arrowNavigation(keyCode: event.keyCode, step: step, furthestStep: frontier)
    {
    case .jump(let target):
      postStepNavigation(target)
      return true
    case .forwardDefaultAction:
      return handleForwardKey() == .handled
    case nil:
      return false
    }
  }

  private func postStepNavigation(_ target: Int) {
    NotificationCenter.default.post(
      name: .onboardingStepNavigationRequested, object: nil, userInfo: ["targetStep": target])
  }

  /// Forward arrow == pressing the step's visible Continue button. Re-issuing the
  /// default-action key (Return) reuses each step's own gating (name/goal required,
  /// demo completion) instead of blindly advancing `currentStep`.
  private func handleForwardKey() -> KeyPress.Result {
    guard let window = NSApp.keyWindow else { return .ignored }
    for phase in [NSEvent.EventType.keyDown, .keyUp] {
      guard
        let event = NSEvent.keyEvent(
          with: phase, location: .zero, modifierFlags: [],
          timestamp: ProcessInfo.processInfo.systemUptime,
          windowNumber: window.windowNumber, context: nil,
          characters: "\r", charactersIgnoringModifiers: "\r",
          isARepeat: false, keyCode: 36)
      else { continue }
      window.postEvent(event, atStart: false)
    }
    return .handled
  }

  /// Complete onboarding — start all services and transition to the app
  private func handleOnboardingComplete() {
    log("OnboardingView: Onboarding complete")
    AnalyticsManager.shared.onboardingCompleted()

    // Stop the AI if it's still running
    chatProvider.stopAgent(owner: .mainChat)

    // Navigate to Tasks page after transition
    UserDefaults.standard.set(true, forKey: "onboardingJustCompleted")
    if !AppBuild.usesLazyDevPermissions {
      UserDefaults.standard.set(true, forKey: "hasCompletedFileIndexing")
    }
    PostOnboardingPromptSuggestions.save(
      OnboardingPromptSuggestionBuilder.build(from: introCoordinator))

    // Clean up onboarding state and persisted chat data
    ChatToolExecutor.onboardingAppState = nil
    OnboardingChatPersistence.clear()
    ChatDraftStore.shared.clear(.onboardingMain)
    ChatDraftStore.shared.clear(.onboardingFloating)
    FloatingControlBarManager.shared.barState?.switchAIDraft(to: .floatingMain)

    if let onComplete = onComplete {
      onComplete()
    }

    // Restore the real chat projection before revealing the product UI.
    Task {
      await chatProvider.finishOnboardingJournal()
      appState.hasCompletedOnboarding = true
    }

    // Start services AFTER UI transition is queued — failures are non-blocking.
    Task {
      await AgentVMService.shared.startPipeline()
      await GoalGenerationService.shared.generateNow()
    }
    if LaunchAtLoginManager.shared.setEnabled(true) {
      AnalyticsManager.shared.launchAtLoginChanged(enabled: true, source: "onboarding_complete")
    }
    if AppBuild.usesLazyDevPermissions {
      AssistantSettings.shared.screenAnalysisEnabled = false
      AssistantSettings.shared.transcriptionEnabled = false
      log("OnboardingView: Lazy dev permissions enabled, skipping monitoring/transcription autostart")
    } else {
      startMonitoringIfNeeded()
      appState.startTranscription()
    }
  }

  private func startMonitoringIfNeeded() {
    AssistantSettings.shared.screenAnalysisEnabled = true
    if !ProactiveAssistantsPlugin.shared.isMonitoring {
      ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
    }
  }
}

struct OnboardingTrustPreviewCard: View {
  var body: some View {
    VStack(spacing: OmiSpacing.xxl) {
      OnboardingVideoView(cornerRadius: OmiChrome.chipRadius)
        .aspectRatio(16.0 / 9.0, contentMode: .fit)
        .frame(maxWidth: .infinity)
        .clipShape(RoundedRectangle(cornerRadius: OmiChrome.controlRadius))
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
            .stroke(OmiColors.backgroundQuaternary.opacity(0.35), lineWidth: 1)
        )

      Rectangle()
        .fill(
          LinearGradient(
            colors: [
              OmiColors.backgroundQuaternary.opacity(0),
              OmiColors.backgroundQuaternary.opacity(0.4),
              OmiColors.backgroundQuaternary.opacity(0),
            ],
            startPoint: .leading,
            endPoint: .trailing
          )
        )
        .frame(height: 1)
        .padding(.horizontal, OmiSpacing.xl)

      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "shield.lefthalf.filled")
          .font(.system(size: 16, weight: .semibold))
          .foregroundColor(OmiColors.textSecondary)
        Text("Trust & Privacy")
          .font(.system(size: 17, weight: .medium))
          .foregroundColor(OmiColors.textSecondary)
          .lineLimit(1)
        Text("omi protects your data")
          .font(.system(size: 15, weight: .regular))
          .foregroundColor(OmiColors.textTertiary)
          .lineLimit(1)
          .minimumScaleFactor(0.85)
      }
      .padding(.top, OmiSpacing.hairline)
      .padding(.bottom, OmiSpacing.xs)
      .frame(maxWidth: .infinity, alignment: .center)

      VStack(spacing: OmiSpacing.sm) {
        trustRow(
          icon: "chevron.left.forwardslash.chevron.right", title: "Open Source", detail: "Code is ")
        trustRow(
          icon: "lock.shield", title: "Encrypted",
          detail: "Cloud sync data is encrypted in transit and at rest.")
        trustRow(
          icon: "externaldrive.badge.person.crop", title: "User-Owned",
          detail: "Primary data stays local and belongs to you.")
      }
      .padding(OmiSpacing.lg)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
          .fill(OmiColors.backgroundTertiary.opacity(0.75))
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
              .stroke(Color.white.opacity(0.08), lineWidth: 1)
          )
      )
    }
    .frame(maxWidth: .infinity)
    .padding(.vertical, OmiSpacing.xxl)
  }

  @ViewBuilder
  private func trustRow(icon: String, title: String, detail: String) -> some View {
    HStack(alignment: .top, spacing: OmiSpacing.sm) {
      Image(systemName: icon)
        .font(.system(size: 14, weight: .semibold))
        .foregroundColor(OmiColors.textSecondary)
        .frame(width: 20, height: 20)

      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text(title)
          .font(.system(size: 13, weight: .semibold))
          .foregroundColor(OmiColors.textPrimary)
        if title == "Open Source" {
          HStack(spacing: 0) {
            Text(detail)
              .foregroundColor(OmiColors.textSecondary)
            if let url = URL(string: "https://github.com/basedhardware/omi/") {
              Link("public", destination: url)
                .foregroundColor(OmiColors.textPrimary)
                .underline()
            }
            Text(" and auditable.")
              .foregroundColor(OmiColors.textSecondary)
          }
          .font(.system(size: 12))
        } else {
          Text(detail)
            .font(.system(size: 12))
            .foregroundColor(OmiColors.textSecondary)
        }
      }
      Spacer()
    }
  }
}

// MARK: - Onboarding Video View

struct OnboardingVideoView: NSViewRepresentable {
  var cornerRadius: CGFloat = 12

  func makeCoordinator() -> Coordinator {
    Coordinator()
  }

  func makeNSView(context: Context) -> AVPlayerView {
    let playerView = AVPlayerView()
    playerView.wantsLayer = true
    playerView.layer?.cornerRadius = cornerRadius
    playerView.layer?.cornerCurve = .continuous
    playerView.layer?.masksToBounds = true
    playerView.videoGravity = .resizeAspect
    if let url = Bundle.resourceBundle.url(forResource: "omi-demo", withExtension: "mp4") {
      let player = AVPlayer(url: url)
      playerView.player = player
      playerView.controlsStyle = .none
      playerView.showsFullScreenToggleButton = false
      playerView.showsSharingServiceButton = false
      player.play()

      NotificationCenter.default.addObserver(
        context.coordinator,
        selector: #selector(Coordinator.playerDidFinishPlaying(_:)),
        name: .AVPlayerItemDidPlayToEndTime,
        object: player.currentItem
      )
      context.coordinator.player = player
    }
    return playerView
  }

  func updateNSView(_ nsView: AVPlayerView, context: Context) {
    nsView.layer?.cornerRadius = cornerRadius
  }

  class Coordinator: NSObject {
    var player: AVPlayer?

    @objc func playerDidFinishPlaying(_ notification: Notification) {
      player?.seek(to: .zero)
      player?.play()
    }
  }
}

// MARK: - Animated GIF View

struct AnimatedGIFView: NSViewRepresentable {
  let gifName: String

  func makeNSView(context: Context) -> NSImageView {
    let imageView = NSImageView()
    imageView.imageScaling = .scaleProportionallyDown
    imageView.animates = true
    imageView.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
    imageView.setContentCompressionResistancePriority(.defaultLow, for: .vertical)

    if let url = Bundle.resourceBundle.url(forResource: gifName, withExtension: "gif"),
      let image = NSImage(contentsOf: url)
    {
      imageView.image = image
    }

    return imageView
  }

  func updateNSView(_ nsView: NSImageView, context: Context) {
    nsView.animates = true
  }
}

// MARK: - Onboarding Privacy Sheet

struct OnboardingPrivacySheet: View {
  @Binding var isPresented: Bool

  var body: some View {
    VStack(spacing: 0) {
      // Header
      HStack {
        Image(systemName: "shield.lefthalf.filled")
          .scaledFont(size: OmiType.subheading)
          .foregroundColor(OmiColors.textSecondary)

        Text("Data & Privacy")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        Button(action: { isPresented = false }) {
          Image(systemName: "xmark.circle.fill")
            .scaledFont(size: OmiType.heading)
            .foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
      }
      .padding(OmiSpacing.xl)

      Divider()

      ScrollView {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          // Encryption
          privacyCard {
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              Label("Encryption", systemImage: "lock.shield")
                .scaledFont(size: OmiType.body, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              HStack(spacing: OmiSpacing.sm) {
                Image(systemName: "checkmark.circle.fill")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(.green)
                Text("Server-side encryption")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textSecondary)
                Text("Active")
                  .scaledFont(size: OmiType.micro, weight: .semibold)
                  .foregroundColor(.green)
                  .padding(.horizontal, OmiSpacing.xxs)
                  .padding(.vertical, OmiSpacing.hairline)
                  .background(Color.green.opacity(0.15))
                  .cornerRadius(OmiChrome.stripRadius)
              }

              Text("Your data is encrypted and stored securely with Google Cloud infrastructure.")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
                .padding(.top, OmiSpacing.hairline)
            }
          }

          // What We Track
          privacyCard {
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              Label("What We Track", systemImage: "list.bullet")
                .scaledFont(size: OmiType.body, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                sheetTrackingItem("Onboarding steps completed")
                sheetTrackingItem("Settings changes")
                sheetTrackingItem("App installations and usage")
                sheetTrackingItem("Device connection status")
                sheetTrackingItem("Transcript processing events")
                sheetTrackingItem("Conversation creation and updates")
                sheetTrackingItem("Memory extraction events")
                sheetTrackingItem("Chat interactions")
                sheetTrackingItem("Speech profile creation")
                sheetTrackingItem("Focus session events")
                sheetTrackingItem("App open/close events")
              }
            }
          }

          // Privacy Guarantees
          privacyCard {
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              Label("Privacy Guarantees", systemImage: "hand.raised.fill")
                .scaledFont(size: OmiType.body, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                sheetBullet("Anonymous tracking with randomly generated IDs")
                sheetBullet("No personal info stored in analytics")
                sheetBullet("Data is never sold or shared with third parties")
                sheetBullet("Opt out of tracking at any time")
              }
            }
          }
        }
        .padding(OmiSpacing.xl)
      }
    }
    .frame(width: 400, height: 480)
    .background(OmiColors.backgroundSecondary)
  }

  private func privacyCard<Content: View>(@ViewBuilder content: () -> Content) -> some View {
    content()
      .padding(OmiSpacing.md)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
          .fill(OmiColors.backgroundTertiary.opacity(0.5))
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .stroke(OmiColors.backgroundQuaternary.opacity(0.3), lineWidth: 1)
          )
      )
  }

  private func sheetTrackingItem(_ text: String) -> some View {
    HStack(spacing: OmiSpacing.xs) {
      Circle()
        .fill(OmiColors.textTertiary.opacity(0.5))
        .frame(width: 3, height: 3)
      Text(text)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(OmiColors.textTertiary)
    }
  }

  private func sheetBullet(_ text: String) -> some View {
    HStack(spacing: OmiSpacing.xs) {
      Image(systemName: "checkmark")
        .scaledFont(size: 8, weight: .bold)
        .foregroundColor(.green)
      Text(text)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(OmiColors.textSecondary)
    }
  }
}
