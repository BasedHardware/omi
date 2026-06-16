import AVKit
import AppKit
import SceneKit
import SwiftUI

struct OnboardingView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var chatProvider: ChatProvider
  var onComplete: (() -> Void)? = nil
  var exportStepOverride: Int? = nil
  var isExportPreview = false
  @AppStorage("onboardingStep") private var currentStep = 0
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
  @StateObject private var introCoordinator = OnboardingPagedIntroCoordinator()
  @StateObject private var graphViewModel = MemoryGraphViewModel()

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
          hasInsertedBYOKStep: hasInsertedBYOKStep
        )
        if !hasRemovedNotificationPermissionStep, currentStep >= 8 {
          currentStep -= 1
        }
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
      introCoordinator.prepare(appState: appState)
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
    }
  }

  private var onboardingContent: some View {
    Group {
      if currentStep == 0 {
        OnboardingWelcomeStepView(
          coordinator: introCoordinator,
          graphViewModel: graphViewModel,
          stepIndex: 0,
          totalSteps: OnboardingFlow.introStepCount,
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
          totalSteps: OnboardingFlow.introStepCount,
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
          totalSteps: OnboardingFlow.introStepCount,
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
          totalSteps: OnboardingFlow.introStepCount,
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
          totalSteps: OnboardingFlow.introStepCount,
          eyebrow: "Permission",
          title: "Let Omi read your screen.",
          description: "Screen Recording lets Omi see what you're working on.",
          permissionType: "screen_recording",
          icon: "display.and.arrow.down",
          reasonTitle: "Screen Recording",
          reasonDetail: "Screen Recording lets Omi see what you're working on.",
          primaryActionLabel: "Open Screen Recording settings",
          requiresRestart: true,
          onContinue: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 4, stepName: "ScreenRecording")
            startMonitoringIfNeeded()
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
          totalSteps: OnboardingFlow.introStepCount,
          eyebrow: "Access",
          title: "Let Omi scan your work.",
          description: "File access lets Omi map your projects and files.",
          permissionType: "full_disk_access",
          icon: "externaldrive.fill.badge.person.crop",
          reasonTitle: "Disk Access",
          reasonDetail: "This lets Omi scan your projects and recent files.",
          primaryActionLabel: "Open Disk Access",
          requiresRestart: false,
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
          totalSteps: OnboardingFlow.introStepCount,
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
          totalSteps: OnboardingFlow.introStepCount,
          eyebrow: "Permission",
          title: "Let Omi use your mic.",
          description: "Microphone lets Omi transcribe meetings.",
          permissionType: "microphone",
          icon: "mic.fill",
          reasonTitle: "Microphone",
          reasonDetail: "This lets Omi transcribe meetings and voice notes.",
          primaryActionLabel: "Grant microphone access",
          requiresRestart: false,
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
          totalSteps: OnboardingFlow.introStepCount,
          eyebrow: "Permission",
          title: "Let Omi see the active app.",
          description: "Accessibility lets Omi know which app is active.",
          permissionType: "accessibility",
          icon: "figure.wave",
          reasonTitle: "Accessibility",
          reasonDetail: "This lets Omi know which app you are using.",
          primaryActionLabel: "Open Accessibility settings",
          requiresRestart: false,
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
          totalSteps: OnboardingFlow.introStepCount,
          eyebrow: "Permission",
          title: "Let Omi act when asked.",
          description: "Automation lets Omi take actions for you.",
          permissionType: "automation",
          icon: "bolt.horizontal.circle.fill",
          reasonTitle: "Automation",
          reasonDetail: "This lets Omi take actions when you ask.",
          primaryActionLabel: "Grant automation access",
          requiresRestart: false,
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
          totalSteps: OnboardingFlow.introStepCount,
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
          totalSteps: OnboardingFlow.introStepCount,
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
          totalSteps: OnboardingFlow.introStepCount,
          onContinue: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 16, stepName: "Goal")
            if !ProactiveAssistantsPlugin.shared.isMonitoring {
              ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
            }
            currentStep = 17
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 16, stepName: "Goal_Skipped")
            if !ProactiveAssistantsPlugin.shared.isMonitoring {
              ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
            }
            currentStep = 17
          },
          onForceComplete: handleOnboardingComplete
        )
      } else if currentStep == 17 {
        OnboardingBYOKStepView(
          graphViewModel: graphViewModel,
          stepIndex: 17,
          totalSteps: OnboardingFlow.introStepCount,
          onContinue: {
            currentStep = 18
          },
          onSkip: {
            currentStep = 18
          },
          onForceComplete: handleOnboardingComplete
        )
      } else {
        OnboardingTasksStepView(
          onComplete: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 18, stepName: "Tasks")
            handleOnboardingComplete()
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 18, stepName: "Tasks_Skipped")
            handleOnboardingComplete()
          },
          onForceComplete: handleOnboardingComplete
        )
      }
    }
  }

  /// Complete onboarding — start all services and transition to the app
  private func handleOnboardingComplete() {
    log("OnboardingView: Onboarding complete")
    AnalyticsManager.shared.onboardingCompleted()

    // Stop the AI if it's still running
    chatProvider.stopAgent()

    // Navigate to Tasks page after transition
    UserDefaults.standard.set(true, forKey: "onboardingJustCompleted")
    UserDefaults.standard.set(true, forKey: "hasCompletedFileIndexing")
    PostOnboardingPromptSuggestions.save(
      OnboardingPromptSuggestionBuilder.build(from: introCoordinator))

    // Clean up onboarding state and persisted chat data
    chatProvider.isOnboarding = false
    OnboardingChatPersistence.clear()

    if let onComplete = onComplete {
      onComplete()
    }

    // Transition UI FIRST — service failures must never block the UI.
    // Setting this synchronously crashes in Button.body.getter, so defer it.
    DispatchQueue.main.async {
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
    startMonitoringIfNeeded()
    appState.startTranscription()

    // Create welcome task
    Task {
      let welcomeDescription = "Run omi for two days to start receiving helpful insights"
      let alreadyExists = await ActionItemStorage.shared.actionItemExists(
        description: welcomeDescription)
      if !alreadyExists {
        await TasksStore.shared.createTask(
          description: welcomeDescription,
          dueAt: Date(),
          priority: "low"
        )
      }
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
    VStack(spacing: 24) {
      OnboardingVideoView(cornerRadius: 14)
        .aspectRatio(16.0 / 9.0, contentMode: .fit)
        .frame(maxWidth: .infinity)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(
          RoundedRectangle(cornerRadius: 16)
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
        .padding(.horizontal, 20)

      HStack(spacing: 8) {
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
      .padding(.top, 2)
      .padding(.bottom, 6)
      .frame(maxWidth: .infinity, alignment: .center)

      VStack(spacing: 10) {
        trustRow(
          icon: "chevron.left.forwardslash.chevron.right", title: "Open Source", detail: "Code is ")
        trustRow(
          icon: "lock.shield", title: "Encrypted",
          detail: "Cloud sync data is encrypted in transit and at rest.")
        trustRow(
          icon: "externaldrive.badge.person.crop", title: "User-Owned",
          detail: "Primary data stays local and belongs to you.")
      }
      .padding(16)
      .background(
        RoundedRectangle(cornerRadius: 16)
          .fill(OmiColors.backgroundTertiary.opacity(0.75))
          .overlay(
            RoundedRectangle(cornerRadius: 16)
              .stroke(Color.white.opacity(0.08), lineWidth: 1)
          )
      )
    }
    .frame(maxWidth: .infinity)
    .padding(.vertical, 24)
  }

  @ViewBuilder
  private func trustRow(icon: String, title: String, detail: String) -> some View {
    HStack(alignment: .top, spacing: 10) {
      Image(systemName: icon)
        .font(.system(size: 14, weight: .semibold))
        .foregroundColor(OmiColors.textSecondary)
        .frame(width: 20, height: 20)

      VStack(alignment: .leading, spacing: 2) {
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
          .scaledFont(size: 16)
          .foregroundColor(OmiColors.textSecondary)

        Text("Data & Privacy")
          .scaledFont(size: 16, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        Button(action: { isPresented = false }) {
          Image(systemName: "xmark.circle.fill")
            .scaledFont(size: 18)
            .foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
      }
      .padding(20)

      Divider()

      ScrollView {
        VStack(alignment: .leading, spacing: 16) {
          // Encryption
          privacyCard {
            VStack(alignment: .leading, spacing: 10) {
              Label("Encryption", systemImage: "lock.shield")
                .scaledFont(size: 13, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              HStack(spacing: 8) {
                Image(systemName: "checkmark.circle.fill")
                  .scaledFont(size: 11)
                  .foregroundColor(.green)
                Text("Server-side encryption")
                  .scaledFont(size: 12)
                  .foregroundColor(OmiColors.textSecondary)
                Text("Active")
                  .scaledFont(size: 10, weight: .semibold)
                  .foregroundColor(.green)
                  .padding(.horizontal, 5)
                  .padding(.vertical, 1)
                  .background(Color.green.opacity(0.15))
                  .cornerRadius(3)
              }

              Text("Your data is encrypted and stored securely with Google Cloud infrastructure.")
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)
                .padding(.top, 2)
            }
          }

          // What We Track
          privacyCard {
            VStack(alignment: .leading, spacing: 8) {
              Label("What We Track", systemImage: "list.bullet")
                .scaledFont(size: 13, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              VStack(alignment: .leading, spacing: 4) {
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
            VStack(alignment: .leading, spacing: 8) {
              Label("Privacy Guarantees", systemImage: "hand.raised.fill")
                .scaledFont(size: 13, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              VStack(alignment: .leading, spacing: 5) {
                sheetBullet("Anonymous tracking with randomly generated IDs")
                sheetBullet("No personal info stored in analytics")
                sheetBullet("Data is never sold or shared with third parties")
                sheetBullet("Opt out of tracking at any time")
              }
            }
          }
        }
        .padding(20)
      }
    }
    .frame(width: 400, height: 480)
    .background(OmiColors.backgroundSecondary)
  }

  private func privacyCard<Content: View>(@ViewBuilder content: () -> Content) -> some View {
    content()
      .padding(14)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(
        RoundedRectangle(cornerRadius: 10)
          .fill(OmiColors.backgroundTertiary.opacity(0.5))
          .overlay(
            RoundedRectangle(cornerRadius: 10)
              .stroke(OmiColors.backgroundQuaternary.opacity(0.3), lineWidth: 1)
          )
      )
  }

  private func sheetTrackingItem(_ text: String) -> some View {
    HStack(spacing: 6) {
      Circle()
        .fill(OmiColors.textTertiary.opacity(0.5))
        .frame(width: 3, height: 3)
      Text(text)
        .scaledFont(size: 11)
        .foregroundColor(OmiColors.textTertiary)
    }
  }

  private func sheetBullet(_ text: String) -> some View {
    HStack(spacing: 6) {
      Image(systemName: "checkmark")
        .scaledFont(size: 8, weight: .bold)
        .foregroundColor(.green)
      Text(text)
        .scaledFont(size: 11)
        .foregroundColor(OmiColors.textSecondary)
    }
  }
}
