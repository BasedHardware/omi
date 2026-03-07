import SwiftUI
import AppKit

/// Onboarding step: prompts user to press ⌘+Enter, then activates the real
/// floating bar at the top of the screen. Shows Continue after the AI responds.
struct OnboardingFloatingBarDemoView: View {
    @ObservedObject var appState: AppState
    @ObservedObject var chatProvider: ChatProvider
    var onComplete: () -> Void
    var onSkip: () -> Void

    @State private var barActivated = false
    @State private var showContinue = false
    @State private var pulseAnimation = false
    @State private var keyMonitor: Any?

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Ask omi anything")
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

                    Image(systemName: "rectangle.and.text.magnifyingglass")
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
                    Text("The Floating Bar")
                        .font(.system(size: 24, weight: .bold))
                        .foregroundColor(OmiColors.textPrimary)

                    Text("Ask anything and it responds using\neverything it knows about you.")
                        .font(.system(size: 14))
                        .foregroundColor(OmiColors.textSecondary)
                        .multilineTextAlignment(.center)
                        .lineSpacing(4)
                }

                if !barActivated {
                    // Keyboard shortcut hint
                    VStack(spacing: 12) {
                        Text("Try it now")
                            .font(.system(size: 13))
                            .foregroundColor(OmiColors.textTertiary)

                        HStack(spacing: 6) {
                            keyCap("⌘")
                            Text("+")
                                .font(.system(size: 15, weight: .medium))
                                .foregroundColor(OmiColors.textTertiary)
                            keyCap("Enter")
                        }
                    }
                    .padding(.top, 4)
                    .transition(.opacity)
                } else if !showContinue {
                    // Waiting for user to type and get a response
                    Text("Type a question in the floating bar above")
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textTertiary)
                        .padding(.top, 4)
                        .transition(.opacity)
                }
            }
            .padding(.horizontal, 40)

            Spacer()

            // Bottom button — only after AI response completes
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
            // Set up the real floating bar (creates the window if needed)
            FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
            // Unregister global shortcuts so we handle Cmd+Enter ourselves
            GlobalShortcutManager.shared.unregisterShortcuts()
            installKeyMonitor()
        }
        .onDisappear {
            removeKeyMonitor()
            // Close the AI conversation panel on the floating bar so the next step starts clean
            if FloatingControlBarManager.shared.barState?.showingAIConversation == true {
                FloatingControlBarManager.shared.toggleAIInput()
            }
            // Re-register global shortcuts for subsequent steps and normal use
            GlobalShortcutManager.shared.registerShortcuts()
        }
        .onChange(of: barActivated) { _, activated in
            if activated {
                Task { await waitForResponse() }
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

    // MARK: - Key Monitor

    private func installKeyMonitor() {
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            let mods = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
            if mods == .command && event.keyCode == 36 { // 36 = Return
                if !barActivated {
                    // Activate the real floating bar's AI input
                    FloatingControlBarManager.shared.openAIInput()
                    withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                        barActivated = true
                    }
                    return nil
                }
            }
            return event
        }
    }

    private func removeKeyMonitor() {
        if let monitor = keyMonitor {
            NSEvent.removeMonitor(monitor)
            keyMonitor = nil
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
