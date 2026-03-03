import SwiftUI

// MARK: - Onboarding Floating Bar Demo View (Step 3)

struct OnboardingFloatingBarDemoView: View {
    let onContinue: () -> Void
    let onSkip: () -> Void

    @StateObject private var shortcutSettings = ShortcutSettings.shared
    @State private var barHovered = false

    var body: some View {
        VStack(spacing: 0) {
            Spacer()

            VStack(spacing: 28) {
                // Title
                Text("Your floating assistant")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(OmiColors.textPrimary)

                Text("A tiny bar that lives on your desktop — hover to expand")
                    .font(.system(size: 15))
                    .foregroundColor(OmiColors.textTertiary)
                    .multilineTextAlignment(.center)

                // Keyboard shortcut hint
                keyboardShortcutHint

                // Desktop frame with floating bar mockup
                desktopFrame
            }

            Spacer()

            // Bottom buttons
            VStack(spacing: 12) {
                Button(action: onContinue) {
                    Text("Get Started")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.white)
                        .frame(maxWidth: 220)
                        .padding(.vertical, 12)
                        .background(OmiColors.purplePrimary)
                        .cornerRadius(12)
                }
                .buttonStyle(.plain)

                Button(action: onSkip) {
                    Text("Skip")
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
            .padding(.bottom, 40)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Keyboard Shortcut Hint

    private var keyboardShortcutHint: some View {
        HStack(spacing: 6) {
            Text("Press")
                .font(.system(size: 13))
                .foregroundColor(OmiColors.textTertiary)

            keyCap("\u{2325}")  // ⌥ Option
            Text("Space")
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundColor(.white)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.white.opacity(0.1))
                .cornerRadius(5)
                .overlay(
                    RoundedRectangle(cornerRadius: 5)
                        .stroke(Color.white.opacity(0.15), lineWidth: 1)
                )

            Text("anywhere to open")
                .font(.system(size: 13))
                .foregroundColor(OmiColors.textTertiary)
        }
    }

    private func keyCap(_ key: String) -> some View {
        Text(key)
            .font(.system(size: 14, weight: .medium, design: .rounded))
            .foregroundColor(.white)
            .frame(width: 28, height: 28)
            .background(Color.white.opacity(0.1))
            .cornerRadius(6)
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(Color.white.opacity(0.15), lineWidth: 1)
            )
    }

    // MARK: - Desktop Frame with Floating Bar Mockup

    private var desktopFrame: some View {
        ZStack {
            // Dark desktop container
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(hex: 0x1A1A1A))
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(Color.white.opacity(0.06), lineWidth: 1)
                )

            // Fake desktop content (faint window outlines)
            VStack(spacing: 8) {
                // Menu bar
                HStack {
                    Circle()
                        .fill(Color.white.opacity(0.08))
                        .frame(width: 12, height: 12)
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.white.opacity(0.05))
                        .frame(width: 40, height: 8)
                    Spacer()
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.white.opacity(0.05))
                        .frame(width: 60, height: 8)
                }
                .padding(.horizontal, 12)
                .padding(.top, 8)

                Spacer()

                // Floating bar mockup at bottom center
                floatingBarMockup
                    .padding(.bottom, 16)
            }
        }
        .frame(width: 380, height: 240)
    }

    private var floatingBarMockup: some View {
        VStack(spacing: 0) {
            if barHovered {
                // Expanded state
                VStack(spacing: 2) {
                    HStack(spacing: 3) {
                        Text("Ask omi")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(.white)
                        ForEach(shortcutSettings.askOmiKey.hintKeys, id: \.self) { key in
                            Text(key)
                                .font(.system(size: 9))
                                .foregroundColor(.white)
                                .frame(width: 15, height: 15)
                                .background(Color.white.opacity(0.1))
                                .cornerRadius(3)
                        }
                    }

                    HStack(spacing: 3) {
                        Text("Push to talk")
                            .font(.system(size: 10))
                            .foregroundColor(.white.opacity(0.6))
                        Text(shortcutSettings.pttKey.symbol)
                            .font(.system(size: 8))
                            .foregroundColor(.white.opacity(0.6))
                            .frame(width: 13, height: 13)
                            .background(Color.white.opacity(0.08))
                            .cornerRadius(2)
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .frame(height: 44)
                .background(
                    RoundedRectangle(cornerRadius: 16)
                        .fill(Color.black.opacity(0.7))
                        .overlay(
                            RoundedRectangle(cornerRadius: 16)
                                .stroke(Color.white.opacity(0.1), lineWidth: 0.5)
                        )
                )
                .transition(.opacity)
            } else {
                // Collapsed pill
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.white.opacity(0.4))
                    .frame(width: 28, height: 4)
                    .padding(.vertical, 4)
                    .background(
                        RoundedRectangle(cornerRadius: 5)
                            .fill(Color.black.opacity(0.5))
                            .frame(width: 40, height: 12)
                    )
                    .transition(.opacity)
            }
        }
        .animation(.spring(response: 0.35, dampingFraction: 0.8), value: barHovered)
        .onHover { hovering in
            barHovered = hovering
        }
        .onAppear {
            // Auto-expand after a moment to demo the interaction
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
                withAnimation {
                    barHovered = true
                }
                // Collapse again after showing
                DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
                    withAnimation {
                        barHovered = false
                    }
                }
            }
        }
    }
}
