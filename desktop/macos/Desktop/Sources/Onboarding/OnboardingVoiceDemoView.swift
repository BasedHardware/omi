import OmiTheme
import SwiftUI

/// Onboarding step: hold the voice shortcut, ask a question, and see the AI respond.
/// Comes after the shortcut-test step so the user has already confirmed the key works.
struct OnboardingVoiceDemoView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var chatProvider: ChatProvider
  var stepIndex: Int
  var totalSteps: Int
  var onComplete: () -> Void
  var onSkip: () -> Void
  var onForceComplete: (() -> Void)?

  @ObservedObject private var pttManager = PushToTalkManager.shared
  @ObservedObject private var shortcutSettings = ShortcutSettings.shared

  @State private var observedShortcutPress = false
  @State private var waitingForResponse = false
  @State private var showContinue = false
  @State private var previousTranscriptionMode: ShortcutSettings.PTTTranscriptionMode?
  @State private var outputReadiness: SystemAudioMuteController.OutputReadiness = .unavailable

  var body: some View {
    VStack(spacing: 0) {
      // Header
      HStack {
        OnboardingLogoMark(onForceComplete: onForceComplete)

        Spacer()

        Button(action: onSkip) {
          Text("Skip")
            .font(.system(size: 13))
            .foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
      }
      .padding(.horizontal, OmiSpacing.xxl)
      .padding(.vertical, OmiSpacing.lg)

      Divider()
        .background(OmiColors.backgroundTertiary)

      OnboardingProgressBar(stepIndex: stepIndex, totalSteps: totalSteps)
        .frame(maxWidth: .infinity, alignment: .center)
        .padding(.top, OmiSpacing.xl)

      Spacer()

      VStack(spacing: OmiSpacing.xxl) {
        VStack(spacing: OmiSpacing.md) {
          Text("Hold \(shortcutSettings.pttShortcut.displayLabel) and Ask")
            .font(.system(size: 24, weight: .bold))
            .foregroundColor(OmiColors.textPrimary)

          Text("Try asking: What's on my screen?")
            .font(.system(size: 18, weight: .medium))
            .foregroundColor(OmiColors.textSecondary)
            .multilineTextAlignment(.center)
        }

        if outputReadiness.shouldAskUserToTurnUpVolume {
          volumeWarning
            .transition(.opacity)
        } else if !observedShortcutPress {
          VStack(spacing: OmiSpacing.md) {
            Text("Hold the shortcut, speak, then release")
              .font(.system(size: 13))
              .foregroundColor(OmiColors.textTertiary)

            HStack(spacing: OmiSpacing.xs) {
              ForEach(Array(shortcutSettings.pttShortcut.displayTokens.enumerated()), id: \.offset) { _, token in
                keyCap(token)
              }
              Text("hold")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(OmiColors.textTertiary)
            }
          }
          .padding(.top, OmiSpacing.xxs)
          .transition(.opacity)
        } else if !showContinue {
          Text(waitingForResponse ? "Waiting for omi to respond..." : "Listening... release when done")
            .font(.system(size: 13))
            .foregroundColor(OmiColors.textTertiary)
            .padding(.top, OmiSpacing.xxs)
            .transition(.opacity)
        }
      }
      .padding(.horizontal, OmiSpacing.page)

      Spacer()

      HStack(spacing: OmiSpacing.md) {
        OnboardingBackButton()

        if showContinue {
          Button(action: onComplete) {
            Text("Continue")
              .font(.system(size: 15, weight: .semibold))
              .foregroundColor(.black)
              .frame(maxWidth: 280)
              .padding(.vertical, OmiSpacing.md)
              .background(Color.white)
              .cornerRadius(OmiChrome.smallControlRadius)
          }
          .buttonStyle(.plain)
          .keyboardShortcut(.defaultAction)
          .transition(.move(edge: .bottom).combined(with: .opacity))
        }
      }
      .padding(.bottom, OmiSpacing.section)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(OmiColors.backgroundPrimary)
    .onAppear {
      FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
      FloatingControlBarManager.shared.barState?.switchAIDraft(to: .onboardingFloating)
      resetFloatingBarConversation()
      refreshOutputReadiness()
      if let barState = FloatingControlBarManager.shared.barState {
        PushToTalkManager.shared.setup(barState: barState)
      }
      previousTranscriptionMode = shortcutSettings.pttTranscriptionMode
      shortcutSettings.pttTranscriptionMode = .live
      Task {
        await chatProvider.warmupBridge()
      }
    }
    .onDisappear {
      shortcutSettings.pttTranscriptionMode = previousTranscriptionMode ?? .batch
      resetFloatingBarConversation()
      PushToTalkManager.shared.cleanup()
    }
    .task {
      await pollOutputReadiness()
    }
    .onChange(of: pttManager.phase) { _, newPhase in
      refreshOutputReadiness()
      guard !outputReadiness.shouldAskUserToTurnUpVolume else { return }
      if newPhase != nil, newPhase?.isTerminal != true {
        observedShortcutPress = true
      }
      if OnboardingFlow.shouldUnlockVoiceShortcutContinue(
        observedShortcutPress: observedShortcutPress,
        voiceTurnPhase: newPhase
      ), !waitingForResponse {
        waitingForResponse = true
        Task { await waitForResponse() }
      }
    }
  }

  private var volumeWarning: some View {
    VStack(spacing: OmiSpacing.md) {
      Text(volumeWarningTitle)
        .font(.system(size: 15, weight: .semibold))
        .foregroundColor(OmiColors.textPrimary)
        .multilineTextAlignment(.center)

      Text("Turn up your Mac volume so you can hear Omi respond, then try push-to-talk.")
        .font(.system(size: 13))
        .foregroundColor(OmiColors.textTertiary)
        .multilineTextAlignment(.center)

      Button(action: refreshOutputReadiness) {
        Text("I turned it up")
          .font(.system(size: 13, weight: .semibold))
          .foregroundColor(.black)
          .padding(.horizontal, OmiSpacing.lg)
          .padding(.vertical, OmiSpacing.sm)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
              .fill(Color.white)
          )
      }
      .buttonStyle(.plain)
    }
    .padding(OmiSpacing.lg)
    .frame(maxWidth: 420)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
        .fill(OmiColors.backgroundSecondary)
    )
    .padding(.top, OmiSpacing.xxs)
  }

  private var volumeWarningTitle: String {
    switch outputReadiness {
    case .muted:
      return "Your Mac volume is muted"
    case .zeroVolume:
      return "Your Mac volume is at 0"
    case .audible, .unavailable:
      return ""
    }
  }

  @MainActor
  private func waitForResponse() async {
    guard let barState = FloatingControlBarManager.shared.barState else {
      showContinueNow()
      return
    }
    // Poll every 0.25s for up to 20s. Unlock as soon as the send cycle finishes,
    // even if the network or bridge failed, so onboarding does not get stuck here.
    for _ in 0..<80 {
      try? await Task.sleep(nanoseconds: 250_000_000)
      if let msg = barState.currentAIMessage(from: chatProvider),
        !msg.isStreaming,
        !msg.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      {
        showContinueNow()
        return
      }
      if !chatProvider.isSending,
        observedShortcutPress,
        chatProvider.errorMessage != nil || barState.currentAIMessage(from: chatProvider) != nil
      {
        showContinueNow()
        return
      }
    }
    // Timeout — show Continue anyway
    showContinueNow()
  }

  private func showContinueNow() {
    OmiMotion.withGated(.easeInOut(duration: 0.3)) {
      showContinue = true
    }
  }

  private func resetFloatingBarConversation() {
    guard let barState = FloatingControlBarManager.shared.barState else { return }
    barState.showingAIConversation = false
    barState.showingAIResponse = false
    barState.aiInputText = ""
    barState.clearViewport()
  }

  private func refreshOutputReadiness() {
    outputReadiness = SystemAudioMuteController.shared.defaultOutputReadiness()
  }

  @MainActor
  private func pollOutputReadiness() async {
    while !Task.isCancelled {
      try? await Task.sleep(nanoseconds: 1_000_000_000)
      refreshOutputReadiness()
    }
  }

  private func keyCap(_ label: String) -> some View {
    Text(label)
      .font(.system(size: 15, weight: .medium, design: .rounded))
      .foregroundColor(OmiColors.textPrimary)
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .fill(OmiColors.backgroundTertiary)
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
              .stroke(OmiColors.backgroundQuaternary.opacity(0.5), lineWidth: 1)
          )
          .shadow(color: .black.opacity(0.2), radius: 1, x: 0, y: 1)
      )
  }
}
