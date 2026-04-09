import SwiftUI

/// Onboarding step: hold the voice shortcut, ask a question, and see the AI respond.
/// Comes after the shortcut-test step so the user has already confirmed the key works.
struct OnboardingVoiceDemoView: View {
    @ObservedObject var appState: AppState
    @ObservedObject var chatProvider: ChatProvider
    var onComplete: () -> Void
    var onSkip: () -> Void
    var onForceComplete: (() -> Void)?

    @ObservedObject private var pttManager = PushToTalkManager.shared
    @ObservedObject private var shortcutSettings = ShortcutSettings.shared

    @State private var observedShortcutPress = false
    @State private var waitingForResponse = false
    @State private var showContinue = false
    @State private var previousTranscriptionMode: ShortcutSettings.PTTTranscriptionMode?
    @State private var voiceResponsesEnabled: Bool = ShortcutSettings.shared.floatingBarVoiceAnswersEnabled

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
            .padding(.horizontal, 24)
            .padding(.vertical, 16)

            Divider()
                .background(OmiColors.backgroundTertiary)

            Spacer()

            VStack(spacing: 24) {
                VStack(spacing: 12) {
                    Text("Hold \(shortcutSettings.pttShortcut.displayLabel) and Ask")
                        .font(.system(size: 24, weight: .bold))
                        .foregroundColor(OmiColors.textPrimary)

                    Text("Try asking: What's on my screen?")
                        .font(.system(size: 18, weight: .medium))
                        .foregroundColor(OmiColors.textSecondary)
                        .multilineTextAlignment(.center)
                }

                // Voice responses checkbox
                HStack(spacing: 8) {
                    Toggle("", isOn: $voiceResponsesEnabled)
                        .toggleStyle(.checkbox)
                        .onChange(of: voiceResponsesEnabled) { _, newValue in
                            ShortcutSettings.shared.floatingBarVoiceAnswersEnabled = newValue
                            SettingsSyncManager.shared.pushPartialUpdate(
                                AssistantSettingsResponse(
                                    floatingBar: FloatingBarSettingsResponse(voiceAnswersEnabled: newValue)
                                )
                            )
                        }
                    Text("Speak answers aloud for voice questions")
                        .font(.system(size: 14))
                        .foregroundColor(OmiColors.textSecondary)
                }
                .padding(.top, 4)

                if !observedShortcutPress {
                    VStack(spacing: 12) {
                        Text("Hold the shortcut, speak, then release")
                            .font(.system(size: 13))
                            .foregroundColor(OmiColors.textTertiary)

                        HStack(spacing: 6) {
                            ForEach(Array(shortcutSettings.pttShortcut.displayTokens.enumerated()), id: \.offset) { _, token in
                                keyCap(token)
                            }
                            Text("hold")
                                .font(.system(size: 13, weight: .medium))
                                .foregroundColor(OmiColors.textTertiary)
                        }
                    }
                    .padding(.top, 4)
                    .transition(.opacity)
                } else if !showContinue {
                    Text(waitingForResponse ? "Waiting for omi to respond..." : "Listening... release when done")
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textTertiary)
                        .padding(.top, 4)
                        .transition(.opacity)
                }
            }
            .padding(.horizontal, 40)

            Spacer()

            if showContinue {
                Button(action: onComplete) {
                    Text("Continue")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.black)
                        .frame(maxWidth: 280)
                        .padding(.vertical, 12)
                        .background(Color.white)
                        .cornerRadius(12)
                }
                .buttonStyle(.plain)
                .padding(.bottom, 32)
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(OmiColors.backgroundPrimary)
        .onAppear {
            FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
            resetFloatingBarConversation()
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
        .onChange(of: pttManager.state) { _, newState in
            if newState != .idle {
                observedShortcutPress = true
            }
            if OnboardingFlow.shouldUnlockVoiceShortcutContinue(
                observedShortcutPress: observedShortcutPress,
                pttState: newState
            ), !waitingForResponse {
                waitingForResponse = true
                Task { await waitForResponse() }
            }
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
            if let msg = barState.currentAIMessage,
               !msg.isStreaming,
               !msg.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                showContinueNow()
                return
            }
            if !chatProvider.isSending,
               observedShortcutPress,
               (chatProvider.errorMessage != nil || barState.currentAIMessage != nil) {
                showContinueNow()
                return
            }
        }
        // Timeout — show Continue anyway
        showContinueNow()
    }

    private func showContinueNow() {
        withAnimation(.easeInOut(duration: 0.3)) {
            showContinue = true
        }
    }

    private func resetFloatingBarConversation() {
        guard let barState = FloatingControlBarManager.shared.barState else { return }
        barState.showingAIConversation = false
        barState.showingAIResponse = false
        barState.aiInputText = ""
        barState.currentAIMessage = nil
        barState.chatHistory = []
        barState.isVoiceFollowUp = false
        barState.voiceFollowUpTranscript = ""
    }

    private func keyCap(_ label: String) -> some View {
        Text(label)
            .font(.system(size: 15, weight: .medium, design: .rounded))
            .foregroundColor(OmiColors.textPrimary)
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(OmiColors.backgroundTertiary)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(OmiColors.backgroundQuaternary.opacity(0.5), lineWidth: 1)
                    )
                    .shadow(color: .black.opacity(0.2), radius: 1, x: 0, y: 1)
            )
    }
}
