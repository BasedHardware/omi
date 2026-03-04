import SwiftUI

/// Onboarding step that tells the user to try the floating bar via ⌘ Enter.
/// No embedded mockup — the user triggers the real floating bar themselves.
struct OnboardingFloatingBarDemoView: View {
    @ObservedObject var appState: AppState
    @ObservedObject var chatProvider: ChatProvider
    var onComplete: () -> Void
    var onSkip: () -> Void

    @State private var pulseAnimation = false

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

                // Keyboard shortcut hint
                VStack(spacing: 12) {
                    Text("Try it now")
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textTertiary)

                    HStack(spacing: 8) {
                        ForEach(ShortcutSettings.shared.askOmiKey.hintKeys, id: \.self) { key in
                            keyCap(key)
                        }
                    }
                }
                .padding(.top, 4)
            }
            .padding(.horizontal, 40)

            Spacer()

            // Continue button
            Button(action: onComplete) {
                Text("Start using omi")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(.white)
                    .frame(maxWidth: 280)
                    .padding(.vertical, 12)
                    .background(OmiColors.purplePrimary)
                    .cornerRadius(12)
            }
            .buttonStyle(.plain)
            .padding(.bottom, 32)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(OmiColors.backgroundPrimary)
    }

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
