import SwiftUI
import AppKit

/// Onboarding step: prompts user to hold the PTT key (Option by default)
/// to ask a question using voice via the real floating bar.
struct OnboardingVoiceInputDemoView: View {
    @ObservedObject var appState: AppState
    @ObservedObject var chatProvider: ChatProvider
    var onComplete: () -> Void
    var onSkip: () -> Void

    @ObservedObject private var pttManager = PushToTalkManager.shared
    @State private var hasTried = false
    @State private var showContinue = false
    @State private var pulseAnimation = false

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Voice input")
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

            // Content
            VStack(spacing: 28) {
                // Icon with glow
                ZStack {
                    Circle()
                        .fill(OmiColors.purplePrimary.opacity(0.12))
                        .frame(width: 96, height: 96)
                        .blur(radius: 18)
                        .scaleEffect(pulseAnimation ? 1.15 : 1.0)
                        .animation(.easeInOut(duration: 2).repeatForever(autoreverses: true), value: pulseAnimation)

                    Image(systemName: "mic.fill")
                        .font(.system(size: 40))
                        .foregroundStyle(
                            LinearGradient(
                                colors: [OmiColors.purplePrimary, OmiColors.purpleSecondary],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                }
                .onAppear { pulseAnimation = true }

                VStack(spacing: 10) {
                    Text("Ask with Your Voice")
                        .font(.system(size: 24, weight: .bold))
                        .foregroundColor(OmiColors.textPrimary)

                    Text("Hold the Option key and speak your question.\nRelease to send it.")
                        .font(.system(size: 14))
                        .foregroundColor(OmiColors.textSecondary)
                        .multilineTextAlignment(.center)
                        .lineSpacing(4)
                }

                if !showContinue {
                    VStack(spacing: 16) {
                        VStack(spacing: 12) {
                            Text("Try it now — hold")
                                .font(.system(size: 13))
                                .foregroundColor(OmiColors.textTertiary)

                            keyCap("⌥")
                        }

                        Text("Try asking: \"What's the weather in my city?\"")
                            .font(.system(size: 13))
                            .foregroundColor(OmiColors.textTertiary)
                            .italic()
                    }
                    .padding(.top, 4)
                    .transition(.opacity)
                }
            }
            .padding(.horizontal, 40)

            Spacer()

            // Bottom button
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
            // Ensure floating bar is set up and visible for PTT
            FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
            if !FloatingControlBarManager.shared.isVisible {
                FloatingControlBarManager.shared.show()
            }

            // Set up push-to-talk
            if let barState = FloatingControlBarManager.shared.barState {
                PushToTalkManager.shared.setup(barState: barState)
            }
        }
        .onChange(of: pttManager.state) { _, newState in
            if newState != .idle {
                hasTried = true
            }
            if hasTried && newState == .idle {
                withAnimation(.easeInOut(duration: 0.3)) {
                    showContinue = true
                }
            }
        }
    }

    // MARK: - Key Cap

    private func keyCap(_ key: String) -> some View {
        Text(key)
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
