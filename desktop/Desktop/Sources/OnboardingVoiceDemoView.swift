import SwiftUI

/// Onboarding step: hold the voice shortcut, ask a question, and see the AI respond.
/// Comes after the shortcut-test step so the user has already confirmed the key works.
struct OnboardingVoiceDemoView: View {
    @ObservedObject var appState: AppState
    @ObservedObject var chatProvider: ChatProvider
    var onComplete: () -> Void
    var onSkip: () -> Void

    @ObservedObject private var pttManager = PushToTalkManager.shared
    @ObservedObject private var shortcutSettings = ShortcutSettings.shared

    @State private var observedShortcutPress = false
    @State private var waitingForResponse = false
    @State private var showContinue = false

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Ask omi a question with your voice")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)

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
                    Text("Hold and Ask")
                        .font(.system(size: 24, weight: .bold))
                        .foregroundColor(OmiColors.textPrimary)

                    Text("Try asking: What's on my screen?")
                        .font(.system(size: 18, weight: .medium))
                        .foregroundColor(OmiColors.textSecondary)
                        .multilineTextAlignment(.center)
                }

                if !observedShortcutPress {
                    VStack(spacing: 12) {
                        Text("Hold the shortcut, speak, then release")
                            .font(.system(size: 13))
                            .foregroundColor(OmiColors.textTertiary)

                        HStack(spacing: 6) {
                            keyCap(shortcutSettings.pttKey.symbol)
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
                        .foregroundColor(.white)
                        .frame(maxWidth: 280)
                        .padding(.vertical, 12)
                        .background(OmiColors.purplePrimary)
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
            if let barState = FloatingControlBarManager.shared.barState {
                PushToTalkManager.shared.setup(barState: barState)
            }
        }
        .onDisappear {
            if FloatingControlBarManager.shared.barState?.showingAIConversation == true {
                FloatingControlBarManager.shared.toggleAIInput()
            }
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
        // Poll every 0.5s for up to 60s
        for _ in 0..<120 {
            try? await Task.sleep(nanoseconds: 500_000_000)
            if barState.showingAIResponse,
               let msg = barState.currentAIMessage,
               !msg.isStreaming {
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
