import SwiftUI
import AppKit

/// Onboarding step: prompts user to press ⌘+Enter, then activates the real
/// floating bar at the top of the screen. Shows Continue after the AI responds.
struct OnboardingFloatingBarDemoView: View {
    @ObservedObject var appState: AppState
    @ObservedObject var chatProvider: ChatProvider
    var onComplete: () -> Void
    var onSkip: () -> Void
    var onForceComplete: (() -> Void)?

    @ObservedObject private var shortcutSettings = ShortcutSettings.shared
    @State private var barActivated = false
    @State private var showContinue = false

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

            // Content
            VStack(spacing: 28) {
                VStack(spacing: 12) {
                    if !barActivated {
                        Text("Omi sees your screen and gives you hyper-personalized responses")
                            .font(.system(size: 20, weight: .bold))
                            .foregroundColor(OmiColors.textPrimary)
                            .multilineTextAlignment(.center)
                            .frame(maxWidth: 560)

                        Text("Press this shortcut to open Ask Omi.")
                            .font(.system(size: 18, weight: .medium))
                            .foregroundColor(OmiColors.textSecondary)
                            .multilineTextAlignment(.center)
                    } else {
                        Text("Type in the Floating Bar 'Which computer should I buy?'")
                            .font(.system(size: 24, weight: .bold))
                            .foregroundColor(OmiColors.textPrimary)
                            .multilineTextAlignment(.center)
                            .lineSpacing(4)
                            .frame(maxWidth: 560)
                    }
                }

                if !barActivated {
                    VStack(spacing: 12) {
                        HStack(spacing: 6) {
                            ForEach(Array(shortcutSettings.askOmiShortcut.displayTokens.enumerated()), id: \.offset) { index, symbol in
                                if index > 0 {
                                    Text("+")
                                        .font(.system(size: 15, weight: .medium))
                                        .foregroundColor(OmiColors.textTertiary)
                                }
                                keyCap(symbol)
                            }
                        }

                        Text("Ask Omi opens at the top of your screen.")
                            .font(.system(size: 13))
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .padding(.top, 4)
                    .transition(.opacity)
                } else {
                    MacLineupPreview()
                        .frame(maxWidth: 980)
                        .transition(.opacity.combined(with: .move(edge: .bottom)))
                }

            }
            .padding(.top, 88)
            .padding(.horizontal, 40)

            Spacer()

            // Bottom button — only after AI response completes
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
            // Set up the real floating bar (creates the window if needed)
            FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
            // Use the same global shortcut flow as the normal app so onboarding
            // behaves like production when the user presses Cmd+Enter.
            GlobalShortcutManager.shared.registerShortcuts()
        }
        .onDisappear {
            // Close the AI conversation panel on the floating bar so the next step starts clean
            if FloatingControlBarManager.shared.barState?.showingAIConversation == true {
                FloatingControlBarManager.shared.toggleAIInput()
            }
        }
        .onChange(of: barActivated) { _, activated in
            if activated {
                Task { await waitForResponse() }
            }
        }
        .onReceive(Timer.publish(every: 0.25, on: .main, in: .common).autoconnect()) { _ in
            guard !barActivated,
                  FloatingControlBarManager.shared.barState?.showingAIConversation == true else { return }
            withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                barActivated = true
            }
        }
    }

    // MARK: - Response Observer

    /// Poll the floating bar state until the AI finishes responding.
    @MainActor
    private func waitForResponse() async {
        guard let barState = FloatingControlBarManager.shared.barState else { return }
        // Poll every 0.5s for up to 60s
        for _ in 0..<120 {
            try? await Task.sleep(nanoseconds: 500_000_000)
            if barState.showingAIResponse,
               let msg = barState.currentAIMessage,
               !msg.isStreaming {
                withAnimation(.easeInOut(duration: 0.3)) {
                    showContinue = true
                }
                return
            }
        }
        // Timeout — show Continue anyway
        withAnimation(.easeInOut(duration: 0.3)) {
            showContinue = true
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

private struct MacLineupPreview: View {
    private static let lineupImage: NSImage? = {
        guard let url = Bundle.resourceBundle.url(forResource: "onboarding_mac_lineup", withExtension: "png") else { return nil }
        return NSImage(contentsOf: url)
    }()

    var body: some View {
        Group {
            if let nsImage = Self.lineupImage {
                Image(nsImage: nsImage)
                    .resizable()
                    .interpolation(.high)
                    .scaledToFit()
                    .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
            } else {
                RoundedRectangle(cornerRadius: 24)
                    .fill(Color.white.opacity(0.06))
                    .frame(height: 280)
                    .overlay(
                        Text("Mac lineup image unavailable")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(OmiColors.textTertiary)
                    )
            }
        }
    }
}
