import AVKit
import AppKit
import SceneKit
import SwiftUI

struct OnboardingView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var chatProvider: ChatProvider
  var onComplete: (() -> Void)? = nil
  @AppStorage("onboardingStep") private var currentStep = 0
  @AppStorage("onboardingVideoStepMigrationDone") private var hasMigratedOnboardingSteps = false
  @AppStorage("onboardingVoiceShortcutStepMigrationDone") private var hasInsertedVoiceShortcutStep =
    false
  @AppStorage("onboardingVoiceInputMergeMigrationDone") private var hasMergedVoiceInputStep = false
  @AppStorage("onboardingNotificationStepRemoved") private var hasRemovedNotificationStep = false
  @StateObject private var graphViewModel = MemoryGraphViewModel()
  @State private var graphHasData = false
  @State private var showTrustPreview = true

  let steps = OnboardingFlow.steps

  var body: some View {
    ZStack {
      // Full dark background
      OmiColors.backgroundPrimary
        .ignoresSafeArea()

      Group {
        if appState.hasCompletedOnboarding {
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
      currentStep = OnboardingFlow.migratedStep(
        currentStep: currentStep,
        hasMigratedVideoStep: hasMigratedOnboardingSteps,
        hasInsertedVoiceShortcutStep: hasInsertedVoiceShortcutStep,
        hasMergedVoiceInputStep: hasMergedVoiceInputStep,
        hasRemovedNotificationStep: hasRemovedNotificationStep
      )
      hasMigratedOnboardingSteps = true
      hasInsertedVoiceShortcutStep = true
      hasMergedVoiceInputStep = true
      hasRemovedNotificationStep = true
    }
    .task {
      // Pre-warm the ACP bridge before the chat step starts.
      await chatProvider.warmupBridge()
    }
    .onReceive(NotificationCenter.default.publisher(for: .resetOnboardingRequested)) { _ in
      log("OnboardingView: resetOnboardingRequested — returning to chat step for current app")
      currentStep = 0
    }
  }

  private var onboardingContent: some View {
    Group {
      if currentStep == 0 {
        // Step 0: Interactive AI Chat + Live Knowledge Graph
        HStack(spacing: 0) {
          OnboardingChatView(
            appState: appState,
            chatProvider: chatProvider,
            graphViewModel: graphViewModel,
            onComplete: {
              AnalyticsManager.shared.onboardingStepCompleted(step: 0, stepName: "Chat")
              // Start screen capture early so Rewind tab has screenshots by the time
              // the user finishes onboarding (permissions are granted during chat step)
              if !ProactiveAssistantsPlugin.shared.isMonitoring {
                ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
              }
              currentStep = 1
            },
            onSkip: {
              if !ProactiveAssistantsPlugin.shared.isMonitoring {
                ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
              }
              currentStep = 1
            }
          )
          .frame(maxWidth: .infinity, maxHeight: .infinity)

          // Right pane: Knowledge graph (dark background, graph appears when data arrives)
          ZStack {
            OmiColors.backgroundSecondary.ignoresSafeArea()

            if graphHasData && !showTrustPreview {
              MemoryGraphSceneView(viewModel: graphViewModel)
                .ignoresSafeArea()
                .transition(.opacity)
            }

            if showTrustPreview {
              OnboardingTrustPreviewCard()
                .padding(.horizontal, 48)
                .transition(.opacity.combined(with: .scale(scale: 0.97)))
            }
          }
          .frame(maxWidth: .infinity, maxHeight: .infinity)
          .overlay(alignment: .top) {
            if graphHasData && !showTrustPreview {
              Text("This is your second brain.")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.white)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Color.black.opacity(0.35))
                .cornerRadius(8)
                .padding(.top, 18)
                .transition(.opacity)
            }
          }
          // Use .overlay so hints composite above the NSViewRepresentable SCNView
          .overlay(alignment: .bottom) {
            HStack(spacing: 20) {
              graphHintItem(icon: "arrow.triangle.2.circlepath", label: "Drag to rotate")
              graphHintItem(icon: "magnifyingglass", label: "Scroll to zoom")
              graphHintItem(icon: "hand.draw", label: "Two-finger to pan")
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(
              LinearGradient(
                colors: [Color.black.opacity(0), Color.black.opacity(0.5)],
                startPoint: .top,
                endPoint: .bottom
              )
            )
            .opacity(graphHasData && !showTrustPreview ? 1 : 0)
            .animation(.easeInOut(duration: 0.3), value: graphHasData)
            .animation(.easeInOut(duration: 0.3), value: showTrustPreview)
          }
          .onAppear {
            showTrustPreview = true
            // Handle case where graph already has data on appear
            if !graphViewModel.isEmpty && !graphHasData {
              handleGraphDataArrival()
            }
          }
          .onChange(of: graphViewModel.isEmpty) { _, isEmpty in
            if !isEmpty && !graphHasData {
              handleGraphDataArrival()
            }
          }
        }
      } else if currentStep == 1 {
        // Step 1: Floating Bar Demo
        OnboardingFloatingBarDemoView(
          appState: appState,
          chatProvider: chatProvider,
          onComplete: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 1, stepName: "FloatingBar")
            currentStep = 2
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 1, stepName: "FloatingBar_Skipped")
            currentStep = 2
          }
        )
      } else if currentStep == 2 {
        // Step 2: Verify Push-to-Talk Shortcut + Voice Input
        OnboardingVoiceShortcutStepView(
          appState: appState,
          chatProvider: chatProvider,
          onComplete: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 2, stepName: "VoiceShortcut")
            currentStep = 3
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 2, stepName: "VoiceShortcut_Skipped")
            currentStep = 3
          }
        )
      } else {
        // Step 3: Tasks
        OnboardingTasksStepView(
          onComplete: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 3, stepName: "Tasks")
            handleOnboardingComplete()
          },
          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 4, stepName: "Tasks_Skipped")
            handleOnboardingComplete()
          }
        )
      }
    }
  }

  private func graphHintItem(icon: String, label: String) -> some View {
    HStack(spacing: 4) {
      Image(systemName: icon)
        .font(.system(size: 11))
      Text(label)
        .font(.system(size: 11))
    }
    .foregroundColor(.white.opacity(0.5))
  }

  private func handleGraphDataArrival() {
    withAnimation(.easeIn(duration: 0.35)) {
      graphHasData = true
    }

    // Keep the trust panel visible briefly, then transition to the graph.
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.4) {
      withAnimation(.easeInOut(duration: 0.45)) {
        showTrustPreview = false
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
    ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
    appState.startTranscription()

    // Create welcome task
    Task {
      let welcomeDescription = "Run omi for two days to start receiving helpful advice"
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
}

private struct OnboardingTrustPreviewCard: View {
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
          .foregroundColor(OmiColors.purplePrimary.opacity(0.9))
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
              .stroke(OmiColors.purplePrimary.opacity(0.25), lineWidth: 1)
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
        .foregroundColor(OmiColors.purplePrimary)
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
                .foregroundColor(OmiColors.purpleSecondary)
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
          .foregroundColor(OmiColors.purplePrimary)

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
