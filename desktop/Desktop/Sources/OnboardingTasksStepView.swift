import SwiftUI

/// Onboarding step explaining that omi auto-creates tasks.
struct OnboardingTasksStepView: View {
    var onComplete: () -> Void

    @State private var pulseAnimation = false

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Tasks")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)
                Spacer()
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 16)

            Divider()
                .background(OmiColors.backgroundTertiary)

            Spacer()

            VStack(spacing: 28) {
                // Icon with glow
                ZStack {
                    Circle()
                        .fill(OmiColors.purplePrimary.opacity(0.15))
                        .frame(width: 100, height: 100)
                        .blur(radius: 20)
                        .scaleEffect(pulseAnimation ? 1.2 : 1.0)
                        .animation(.easeInOut(duration: 2).repeatForever(autoreverses: true), value: pulseAnimation)

                    Image(systemName: "checklist")
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
                    Text("Auto-created Tasks")
                        .font(.system(size: 24, weight: .bold))
                        .foregroundColor(OmiColors.textPrimary)

                    Text("omi listens to your conversations and automatically\ncreates tasks, action items, and follow-ups for you.")
                        .font(.system(size: 14))
                        .foregroundColor(OmiColors.textSecondary)
                        .multilineTextAlignment(.center)
                        .lineSpacing(4)
                }
            }
            .padding(.horizontal, 40)

            Spacer()

            Button(action: onComplete) {
                Text("Take me to my tasks")
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
}
