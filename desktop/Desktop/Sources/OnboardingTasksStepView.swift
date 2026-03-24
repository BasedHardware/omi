import SwiftUI

/// Onboarding step explaining that omi auto-creates tasks.
struct OnboardingTasksStepView: View {
    var onComplete: () -> Void
    var onSkip: (() -> Void)? = nil

    @State private var pulseAnimation = false
    @State private var showTasks = false

    private let mockTasks: [(String, String, Bool)] = [
        ("Task 1", "From today's meeting", false),
        ("Task 2", "Mentioned in Slack", false),
        ("Task 3", "Getting started", true),
    ]

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

                // Mock task cards
                if showTasks {
                    VStack(spacing: 8) {
                        ForEach(Array(mockTasks.enumerated()), id: \.offset) { index, task in
                            mockTaskRow(title: task.0, subtitle: task.1, checked: task.2)
                                .transition(.asymmetric(
                                    insertion: .move(edge: .bottom).combined(with: .opacity),
                                    removal: .opacity
                                ))
                        }
                    }
                    .frame(maxWidth: 420)
                }
            }
            .padding(.horizontal, 40)

            Spacer()

            VStack(spacing: 12) {
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

            }
            .padding(.bottom, 32)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(OmiColors.backgroundPrimary)
        .onAppear {
            // Stagger task card appearance
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                withAnimation(.spring(response: 0.5, dampingFraction: 0.8)) {
                    showTasks = true
                }
            }
        }
    }

    private func mockTaskRow(title: String, subtitle: String, checked: Bool) -> some View {
        HStack(spacing: 12) {
            Image(systemName: checked ? "checkmark.circle.fill" : "circle")
                .font(.system(size: 18))
                .foregroundColor(checked ? .green : OmiColors.textTertiary)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 13))
                    .foregroundColor(checked ? OmiColors.textTertiary : OmiColors.textPrimary)
                    .strikethrough(checked)
                    .lineLimit(1)

                Text(subtitle)
                    .font(.system(size: 11))
                    .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(OmiColors.backgroundSecondary)
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(OmiColors.backgroundTertiary.opacity(0.5), lineWidth: 1)
                )
        )
    }
}
