import SwiftUI

/// Onboarding step that shows what proactive notifications look like.
/// Uses a static example tip — no Gemini call needed.
struct OnboardingNotificationStepView: View {
    @ObservedObject var appState: AppState
    @ObservedObject var chatProvider: ChatProvider
    var onContinue: () -> Void
    var onSkip: () -> Void

    @State private var showNotification = false
    @State private var notificationSent = false
    @State private var pulseAnimation = false

    private let tipHeadline = "Tip"
    private let tipText = "I'll watch your screen and send you proactive tips like this"

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Notifications")
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
            VStack(spacing: 32) {
                // Icon with glow
                ZStack {
                    Circle()
                        .fill(OmiColors.purplePrimary.opacity(0.15))
                        .frame(width: 100, height: 100)
                        .blur(radius: 20)
                        .scaleEffect(pulseAnimation ? 1.2 : 1.0)
                        .animation(.easeInOut(duration: 2).repeatForever(autoreverses: true), value: pulseAnimation)

                    Image(systemName: "bell.badge.fill")
                        .font(.system(size: 44))
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
                    Text("Proactive Intelligence")
                        .font(.system(size: 24, weight: .bold))
                        .foregroundColor(OmiColors.textPrimary)

                    Text("omi watches your screen and catches things you'd miss —\nwrong recipients, stale data, hidden shortcuts.")
                        .font(.system(size: 14))
                        .foregroundColor(OmiColors.textSecondary)
                        .multilineTextAlignment(.center)
                        .lineSpacing(4)
                }

                // Static notification preview
                if showNotification {
                    notificationPreview
                        .transition(.asymmetric(
                            insertion: .move(edge: .top).combined(with: .opacity).combined(with: .scale(scale: 0.95)),
                            removal: .opacity
                        ))
                }
            }
            .padding(.horizontal, 40)

            Spacer()

            // Bottom: confirmation + continue
            if notificationSent {
                VStack(spacing: 12) {
                    HStack(spacing: 6) {
                        Image(systemName: "bell.badge.fill")
                            .foregroundColor(OmiColors.purplePrimary)
                            .font(.system(size: 12))
                        Text("Notification shown below Ask omi")
                            .font(.system(size: 12))
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Button(action: onContinue) {
                        Text("Continue")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundColor(.white)
                            .frame(maxWidth: 280)
                            .padding(.vertical, 12)
                            .background(OmiColors.purplePrimary)
                            .cornerRadius(12)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.bottom, 32)
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(OmiColors.backgroundPrimary)
        .onAppear {
            FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
            FloatingControlBarManager.shared.showTemporarily()

            // Show the notification preview after a brief delay
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
                withAnimation(.spring(response: 0.5, dampingFraction: 0.8)) {
                    showNotification = true
                }

                // Send a real macOS notification
                NotificationService.shared.sendNotification(
                    title: tipHeadline,
                    message: tipText,
                    assistantId: "onboarding"
                )

                // Show "notification sent" + continue after a beat
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                    withAnimation(.easeInOut(duration: 0.3)) {
                        notificationSent = true
                    }
                }
            }
        }
    }

    // MARK: - macOS Notification Preview

    private var notificationPreview: some View {
        HStack(spacing: 12) {
            // App icon
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(
                        LinearGradient(
                            colors: [OmiColors.purplePrimary, OmiColors.purpleAccent],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 36, height: 36)

                Text("omi")
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .foregroundColor(.white)
            }

            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text("omi")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.black)

                    Spacer()

                    Text("now")
                        .font(.system(size: 11))
                        .foregroundColor(.gray)
                }

                Text(tipHeadline)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.black.opacity(0.85))
                    .lineLimit(1)

                Text(tipText)
                    .font(.system(size: 12))
                    .foregroundColor(.black.opacity(0.7))
                    .lineLimit(2)
                    .lineSpacing(1)
            }
        }
        .padding(12)
        .frame(maxWidth: 380, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(.white)
                .shadow(color: .black.opacity(0.15), radius: 12, x: 0, y: 4)
                .shadow(color: .black.opacity(0.05), radius: 1, x: 0, y: 1)
        )
    }
}
