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
            .foregroundColor(Ink.secondary)
        }
        .buttonStyle(.plain)
      }
      .padding(.horizontal, OmiSpacing.xxl)
      .padding(.vertical, OmiSpacing.lg)

      GlassSeparator()

      OnboardingProgressBar(stepIndex: stepIndex, totalSteps: totalSteps)
        .frame(maxWidth: .infinity, alignment: .center)
        .padding(.top, OmiSpacing.xl)

      OnboardingContentWithPinnedActions {
        VStack(spacing: OmiSpacing.xxl) {
          VStack(spacing: OmiSpacing.md) {
            Text("Hold \(shortcutSettings.pttShortcut.displayLabel) and Ask")
              .inkStyle(InkType.stepHeadline, color: Ink.primary)
              .multilineTextAlignment(.center)
              .fixedSize(horizontal: false, vertical: true)

            Text("Try asking: What's on my screen?")
              .inkStyle(InkType.prose, color: Ink.secondary)
              .multilineTextAlignment(.center)
              .fixedSize(horizontal: false, vertical: true)
          }

          if outputReadiness.shouldAskUserToTurnUpVolume {
            volumeWarning
              .transition(.opacity)
          } else if !observedShortcutPress {
            VStack(spacing: OmiSpacing.md) {
              Text("Hold the shortcut, speak, then release")
                .inkStyle(InkType.statusLabel, color: Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)

              HStack(spacing: OmiSpacing.xs) {
                ForEach(Array(shortcutSettings.pttShortcut.displayTokens.enumerated()), id: \.offset) { _, token in
                  keyCap(token)
                }
                Text("hold")
                  .inkStyle(InkType.statusLabel, color: Ink.secondary)
              }
            }
            .padding(.top, OmiSpacing.xxs)
            .transition(.opacity)
          } else if !showContinue {
            Text(waitingForResponse ? "Waiting for omi to respond..." : "Listening... release when done")
              .inkStyle(InkType.statusLabel, color: Ink.secondary)
              .fixedSize(horizontal: false, vertical: true)
              .padding(.top, OmiSpacing.xxs)
              .transition(.opacity)
          }

        }
        .frame(maxWidth: 420)
      } actions: {
        HStack(spacing: OmiSpacing.md) {
          OnboardingBackButton()

          if showContinue {
            Button(action: onComplete) {
              Text("Continue")
            }
            .buttonStyle(InkButtonStyle(kind: .primary))
            .keyboardShortcut(.defaultAction)
            .transition(.move(edge: .bottom).combined(with: .opacity))
          }
        }
        .frame(maxWidth: 420)
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .onAppear {
      FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
      FloatingControlBarManager.shared.barState?.switchAIDraft(to: .onboardingFloating)
      resetFloatingBarConversation()
      refreshOutputReadiness()
      if let barState = FloatingControlBarManager.shared.barState {
        PushToTalkManager.shared.setup(barState: barState)
      }
      FloatingControlBarManager.shared.showForOnboardingDemo()
      // Force live transcription for the demo via a transient, never-persisted
      // override so a quit/crash mid-step can't corrupt the saved PTT mode.
      shortcutSettings.pttTranscriptionModeDemoOverride = .live
      Task {
        _ = await chatProvider.warmupBridge()
      }
    }
    .onDisappear {
      shortcutSettings.pttTranscriptionModeDemoOverride = nil
      resetFloatingBarConversation()
      PushToTalkManager.shared.cleanup()
      FloatingControlBarManager.shared.hideForOnboardingDemo()
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
        .inkStyle(InkType.rowCopy, color: PageGlass.warning)
        .multilineTextAlignment(.center)
        .fixedSize(horizontal: false, vertical: true)

      Text("Turn up your Mac volume so you can hear Omi respond, then try push-to-talk.")
        .inkStyle(InkType.statusLabel, color: Ink.secondary)
        .multilineTextAlignment(.center)
        .fixedSize(horizontal: false, vertical: true)

      Button(action: refreshOutputReadiness) {
        Text("I turned it up")
      }
      .buttonStyle(InkButtonStyle(kind: .primary))
    }
    .padding(OmiSpacing.lg)
    .frame(maxWidth: 420)
    .glassCard()
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

  /// A keycap on glass: a wash with a hairline outline and an `Ink.primary` glyph. No drop shadow —
  /// on a light panel a black shadow reads as dirt rather than as depth.
  private func keyCap(_ label: String) -> some View {
    Text(label)
      .font(.system(size: 15, weight: .medium, design: .rounded))
      .foregroundColor(Ink.primary)
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
          .fill(Ink.rowFill)
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
              .strokeBorder(Ink.hairline, lineWidth: 1)
          )
      )
  }
}
